"""은행 첨부파일의 위험등급으로 ETF risk_grade를 업데이트.

은행 데이터의 KR7 코드 + 위험등급을 읽어 DB의 ETF에 적용.
ETF 1,266건 중 은행 등록된 ETF(~400건)는 공식 등급, 나머지는 자산군 근사값 유지.

사용법:
    python scripts/update_etf_risk_from_bank.py
"""

import asyncio
import base64
import io
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

import pandas as pd
from sqlalchemy import text
from app.database import AsyncSessionLocal, init_db
from app.services.bank_import_service import INSTITUTIONS, _get_gmail_service, _find_attachment, _parse_attachment


async def main() -> None:
    await init_db()

    service = _get_gmail_service()
    risk_map: dict[str, int] = {}   # KR7 code → risk_grade

    for cfg in INSTITUTIONS:
        resp = service.users().messages().list(userId="me", q=cfg.query, maxResults=1).execute()
        msgs = resp.get("messages", [])
        if not msgs:
            logger.info("%s: 메일 없음", cfg.name)
            continue

        msg = service.users().messages().get(userId="me", id=msgs[0]["id"]).execute()
        att = _find_attachment(msg["payload"].get("parts", []))
        if not att:
            continue

        fname, att_id = att
        att_resp = service.users().messages().attachments().get(
            userId="me", messageId=msgs[0]["id"], id=att_id
        ).execute()
        df = _parse_attachment(base64.urlsafe_b64decode(att_resp["data"]), fname)

        etf_col = cfg.etf_code_col
        risk_col = cfg.risk_col

        if etf_col not in df.columns or risk_col not in df.columns:
            continue

        etf_rows = df[df[etf_col].str.startswith("KR7", na=False)]
        for _, row in etf_rows.iterrows():
            code = str(row[etf_col]).strip()
            risk_raw = str(row.get(risk_col, "") or "").strip()
            if code and risk_raw.isdigit():
                risk_map[code] = int(risk_raw)

        logger.info("%s: ETF 위험등급 %d건 수집", cfg.name, len(etf_rows))

    if not risk_map:
        logger.warning("수집된 위험등급 없음")
        return

    # DB 업데이트
    async with AsyncSessionLocal() as db:
        updated = 0
        BATCH = 500
        items = list(risk_map.items())
        for i in range(0, len(items), BATCH):
            batch = items[i:i + BATCH]
            cases = " ".join(f"WHEN :c{j} THEN :r{j}" for j in range(len(batch)))
            params = {}
            codes_in = []
            for j, (code, grade) in enumerate(batch):
                params[f"c{j}"] = code
                params[f"r{j}"] = grade
                codes_in.append(f":c{j}")
            await db.execute(
                text(f"""
                    UPDATE funds
                    SET risk_grade = CASE fund_code {cases} END
                    WHERE fund_code IN ({", ".join(codes_in)})
                      AND product_type = 'etf'
                """),
                params,
            )
            updated += len(batch)
        await db.commit()

    logger.info("ETF 위험등급 업데이트 완료: %d건", updated)
    print(f"\n  은행 데이터 기반 ETF 위험등급: {len(risk_map)}건 업데이트")


if __name__ == "__main__":
    asyncio.run(main())
