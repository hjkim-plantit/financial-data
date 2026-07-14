"""우리은행 취급 펀드 중 DB에 없는 것을 KOFIA CSV에서 추가.

대상: KRZ→K55 변환은 됐지만 Morningstar에 없어 DB에 누락된 펀드
소스: kofia_fund_codes.csv (standardCd, koreanCdtNm, companyNm, startDt, fundNm)
"""
import asyncio, base64, sys, os
from datetime import date
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
os.chdir(str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(".env")

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.database import AsyncSessionLocal, init_db
from app.models.fund import Fund
from app.services.bank_import_service import (
    _get_gmail_service, _find_attachment, _parse_attachment,
    INSTITUTIONS, _load_krz_to_k55
)
from sqlalchemy import select
import re

# ── fundNm → internal_category_id 매핑 ──────────────────────────
_FND_TP_MAP: dict[str, int] = {
    "주식형":       1,
    "혼합주식형":   1,
    "채권형":       2,
    "혼합채권형":   2,
    "단기금융":     2,   # MMF
    "부동산":       4,
    "인프라":       5,
    "사회간접자본": 5,
    "귀금속":       8,
    "에너지":       9,
    "농산물":       10,
    "특별자산":     11,
    # 아래는 미분류(99)로 처리
    "재간접":       99,  # TDF 등 재간접
    "혼합자산":     99,
    "파생상품형":   99,
}

_REGION_PATTERNS: list[tuple[str, str]] = [
    (r"미국|S&P|SP500|나스닥|nasdaq|다우|dow|russell", "선진국-미국"),
    (r"일본|japan|nikkei", "선진국-일본"),
    (r"선진국|developed|eafe", "선진국-기타"),
    (r"중국|china|csi|홍콩|hang.?seng", "신흥국-중국"),
    (r"한국|korea|kospi|kosdaq|코스피|코스닥", "신흥국-한국"),
    (r"인도|india|nifty", "신흥국-인도"),
    (r"베트남|vietnam", "신흥국-베트남"),
    (r"신흥국|emerging|\bem\b", "신흥국-기타"),
    (r"글로벌|global|world|전세계|tdf|target.?date", "글로벌"),
]


def _region(name: str) -> str:
    for pattern, region in _REGION_PATTERNS:
        if re.search(pattern, name, re.I):
            return region
    return "국내"


def _parse_date(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return date.fromisoformat(s[:10])


async def main(dry_run: bool = False) -> None:
    await init_db()

    # ── 우리은행 이메일에서 K55 코드 수집 ───────────────────────
    krz_to_k55 = _load_krz_to_k55()
    service = _get_gmail_service()
    cfg = next(c for c in INSTITUTIONS if c.key == "woori")
    resp = service.users().messages().list(userId="me", q=cfg.query, maxResults=3).execute()
    msg = None
    for m in resp.get("messages", []):
        candidate = service.users().messages().get(userId="me", id=m["id"]).execute()
        hdrs = {h["name"]: h["value"] for h in candidate["payload"]["headers"]}
        if "우리자산운용" not in hdrs.get("Subject", ""):
            msg = candidate; break

    att = _find_attachment(msg["payload"].get("parts", []))
    fname, att_id = att
    att_resp = service.users().messages().attachments().get(
        userId="me", messageId=msg["id"], id=att_id
    ).execute()
    df = _parse_attachment(base64.urlsafe_b64decode(att_resp["data"]), fname)
    c = cfg.resolve(df)
    active_df = df.copy()
    if c["avail"]: active_df = active_df[active_df[c["avail"]].str.upper() == "Y"]
    if c["end"]: active_df = active_df[active_df[c["end"]].str.replace("-","") == "99991231"]
    krz_codes = [str(r).strip() for r in active_df[c["etf_code"] or c["fund_code"]].dropna() if str(r).startswith("KRZ")]
    woori_k55 = {krz_to_k55[k] for k in krz_codes if k in krz_to_k55}
    print(f"우리은행 K55 코드: {len(woori_k55)}개")

    # ── DB에 없는 것 필터 ────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Fund.fund_code).where(Fund.fund_code.in_(woori_k55))
        )
        existing = {r[0] for r in result.all()}

    missing = woori_k55 - existing
    print(f"DB에 없는 것: {len(missing)}개")

    if not missing:
        print("추가할 펀드 없음.")
        return

    # ── KOFIA CSV에서 정보 로드 ──────────────────────────────────
    kofia_df = pd.read_csv(
        r"C:\Users\김효진\2.FinancialData\kofia_fund_codes.csv",
        encoding="utf-8-sig", dtype=str
    )
    target = kofia_df[kofia_df["standardCd"].isin(missing)].copy()
    print(f"KOFIA CSV 매칭: {len(target)}개")

    # ── rows 변환 ────────────────────────────────────────────────
    rows = []
    no_date = []
    for _, row in target.iterrows():
        fnd_nm = str(row.get("fundNm") or "").strip()
        category_id = _FND_TP_MAP.get(fnd_nm, 99)

        try:
            inception = _parse_date(str(row["startDt"]))
        except Exception:
            no_date.append(row["standardCd"])
            continue

        rows.append({
            "fund_code":           row["standardCd"],
            "fund_name":           str(row["koreanCdtNm"]).strip(),
            "management_company":  str(row["companyNm"]).strip(),
            "kofia_fund_type":     fnd_nm or None,
            "internal_category_id": category_id,
            "investment_region":   _region(str(row["koreanCdtNm"])),
            "inception_date":      inception,
            "product_type":        "fund",
            "status":              "운용중",
        })

    print(f"\n추가 예정: {len(rows)}개")
    if no_date:
        print(f"설정일 파싱 실패 (건너뜀): {no_date}")

    # fundNm 분포
    from collections import Counter
    dist = Counter(r["kofia_fund_type"] for r in rows)
    print("펀드유형 분포:", dict(dist.most_common()))

    if dry_run:
        print("\n[DRY RUN] DB에 쓰지 않습니다.")
        print("샘플 (첫 5개):")
        for r in rows[:5]:
            print(f"  {r['fund_code']} | {r['fund_name'][:40]} | {r['management_company']} | {r['inception_date']} | cat={r['internal_category_id']}")
        return

    # ── DB INSERT (기존 펀드는 무시) ─────────────────────────────
    async with AsyncSessionLocal() as db:
        stmt = sqlite_insert(Fund).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["fund_code"])
        await db.execute(stmt)
        await db.commit()

    print(f"\n✓ {len(rows)}개 추가 완료")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
