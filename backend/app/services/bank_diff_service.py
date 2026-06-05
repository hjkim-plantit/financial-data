"""전일 vs 당일 기관 이메일 첨부파일 비교 서비스."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from app.services.bank_import_service import (
    INSTITUTIONS, InstitutionConfig,
    _get_gmail_service, _find_attachment, _parse_attachment, _kst_date,
)

logger = logging.getLogger(__name__)


# ── 모델 ───────────────────────────────────────────────────────

@dataclass
class FieldChange:
    field: str
    label: str
    old: str
    new: str


@dataclass
class ProductChange:
    fund_code: str
    fund_name: str
    product_type: str           # fund | etf
    change_type: str            # added | removed | changed
    changes: list[FieldChange]  # changed 일 때만 채워짐


@dataclass
class InstitutionDiff:
    key: str
    name: str
    today_date: Optional[str]
    yesterday_date: Optional[str]
    added: list[ProductChange]
    removed: list[ProductChange]
    changed: list[ProductChange]
    error: Optional[str]

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)


# ── 비교 로직 ────────────────────────────────────────────────

# 변경 감지할 필드 (컬럼키: 화면레이블)
_WATCH_FIELDS = {
    "avail":  "판매가능여부",
    "risk":   "위험등급",
    "end":    "취급종료일",
    "start":  "취급시작일",
}


def _parse_email(service, msg_id: str, cfg: InstitutionConfig) -> Optional[pd.DataFrame]:
    """메일 ID → 첨부파일 파싱 → DataFrame 반환."""
    try:
        msg = service.users().messages().get(userId="me", id=msg_id).execute()
        att = _find_attachment(msg["payload"].get("parts", []))
        if not att:
            return None
        fname, att_id = att
        data = base64.urlsafe_b64decode(
            service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=att_id
            ).execute()["data"]
        )
        return _parse_attachment(data, fname)
    except Exception as e:
        logger.warning("메일 파싱 실패 %s: %s", msg_id, e)
        return None


def _df_to_map(df: pd.DataFrame, cfg: InstitutionConfig) -> dict[str, dict]:
    """DataFrame → {fund_code: {field_key: value, ...}} 딕셔너리."""
    c = cfg.resolve(df)
    result: dict[str, dict] = {}

    for _, row in df.iterrows():
        etf_code  = str(row.get(c["etf_code"],  "") or "").strip() if c["etf_code"]  else ""
        fund_code = str(row.get(c["fund_code"],  "") or "").strip() if c["fund_code"] else ""
        name      = str(row.get(c["name"],       "") or "").strip() if c["name"]      else ""

        is_etf = etf_code.startswith("KR7")
        if is_etf:
            code = etf_code
        elif etf_code.startswith("KRZ"):
            code = etf_code   # KRZ(예탁원) 우선
        elif fund_code:
            code = fund_code  # K55(KOFIA) 폴백
        else:
            code = etf_code
        if not code or code == "nan":
            continue

        result[code] = {
            "name":         name,
            "product_type": "etf" if is_etf else "fund",
            "avail":  str(row.get(c["avail"], "") or "").strip() if c["avail"]  else "",
            "risk":   str(row.get(c["risk"],  "") or "").strip() if c["risk"]   else "",
            "end":    str(row.get(c["end"],   "") or "").strip() if c["end"]    else "",
            "start":  str(row.get(c["start"], "") or "").strip() if c["start"]  else "",
        }
    return result


def _diff_maps(
    yesterday: dict[str, dict],
    today: dict[str, dict],
) -> tuple[list[ProductChange], list[ProductChange], list[ProductChange]]:
    """두 딕셔너리를 비교해 (added, removed, changed) 반환."""
    added, removed, changed = [], [], []

    all_codes = set(yesterday) | set(today)
    for code in sorted(all_codes):
        y = yesterday.get(code)
        t = today.get(code)

        if y is None:
            added.append(ProductChange(
                fund_code=code, fund_name=t["name"],
                product_type=t["product_type"],
                change_type="added", changes=[],
            ))
        elif t is None:
            removed.append(ProductChange(
                fund_code=code, fund_name=y["name"],
                product_type=y["product_type"],
                change_type="removed", changes=[],
            ))
        else:
            field_changes = []
            for key, label in _WATCH_FIELDS.items():
                old_val = y.get(key, "")
                new_val = t.get(key, "")
                if old_val != new_val:
                    field_changes.append(FieldChange(
                        field=key, label=label, old=old_val, new=new_val,
                    ))
            if field_changes:
                changed.append(ProductChange(
                    fund_code=code,
                    fund_name=t["name"],
                    product_type=t["product_type"],
                    change_type="changed",
                    changes=field_changes,
                ))

    return added, removed, changed


# ── 메인 ─────────────────────────────────────────────────────

def fetch_diff() -> list[InstitutionDiff]:
    """3개 기관의 최신 2개 이메일을 비교해 변경사항을 반환."""
    try:
        service = _get_gmail_service()
    except Exception as e:
        return [
            InstitutionDiff(
                key=c.key, name=c.name,
                today_date=None, yesterday_date=None,
                added=[], removed=[], changed=[],
                error=f"Gmail 인증 실패: {e}",
            )
            for c in INSTITUTIONS
        ]

    results = []
    for cfg in INSTITUTIONS:
        results.append(_diff_one(service, cfg))
    return results


def _diff_one(service, cfg: InstitutionConfig) -> InstitutionDiff:
    def err(msg: str) -> InstitutionDiff:
        return InstitutionDiff(
            key=cfg.key, name=cfg.name,
            today_date=None, yesterday_date=None,
            added=[], removed=[], changed=[],
            error=msg,
        )

    try:
        # 최근 10건 조회 후 날짜 기준으로 가장 최신 2개 날짜 선택
        resp = service.users().messages().list(
            userId="me", q=cfg.query, maxResults=10
        ).execute()
        msgs = resp.get("messages", [])

        if len(msgs) < 1:
            return err("메일 없음")

        # 날짜 추출
        def get_date(msg_id: str) -> str:
            m = service.users().messages().get(
                userId="me", id=msg_id, format="metadata",
                metadataHeaders=["Date"],
            ).execute()
            h = {x["name"]: x["value"] for x in m["payload"]["headers"]}
            return _kst_date(h.get("Date", ""))

        # 각 메일의 날짜와 ID를 매핑
        msg_dates = [(m["id"], get_date(m["id"])) for m in msgs]

        # 날짜 기준으로 그룹화 (최신순)
        seen_dates: list[str] = []
        date_to_msg: dict[str, str] = {}
        for msg_id, date in msg_dates:
            if date not in date_to_msg:
                date_to_msg[date] = msg_id
                seen_dates.append(date)

        if len(seen_dates) < 2:
            return err("비교할 전일 메일 없음 (당일 메일만 존재)")

        today_date     = seen_dates[0]
        yesterday_date = seen_dates[1]
        today_id     = date_to_msg[today_date]
        yesterday_id = date_to_msg[yesterday_date]

        # 파싱
        df_today     = _parse_email(service, today_id,     cfg)
        df_yesterday = _parse_email(service, yesterday_id, cfg)

        if df_today is None:
            return err("당일 첨부파일 파싱 실패")
        if df_yesterday is None:
            return err("전일 첨부파일 파싱 실패")

        today_map     = _df_to_map(df_today,     cfg)
        yesterday_map = _df_to_map(df_yesterday, cfg)

        if not today_map and not yesterday_map:
            return err("데이터 없음 (컬럼 감지 실패 가능성)")

        added, removed, changed = _diff_maps(yesterday_map, today_map)

        return InstitutionDiff(
            key=cfg.key, name=cfg.name,
            today_date=today_date, yesterday_date=yesterday_date,
            added=added, removed=removed, changed=changed,
            error=None,
        )

    except Exception as e:
        logger.error("%s diff 실패: %s", cfg.name, e, exc_info=True)
        return err(str(e))
