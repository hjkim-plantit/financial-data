"""3개 기관(우리은행, BNK부산은행, BNK경남은행) Gmail 첨부파일 파싱 서비스.

코드 체계:
  - KR7... (KSD ISIN) → ETF  ← DB의 KR7 ISIN과 직접 매칭
  - KRZ... (KSD)      → 펀드 (KRZ↔K55 매핑 없음 → 우리은행 펀드 미매칭)
  - K55... / KR5...   → 펀드 KOFIA 코드 ← DB의 K55 코드와 직접 매칭
"""

from __future__ import annotations

import base64
import io
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ── 기관별 설정 ────────────────────────────────────────────────

@dataclass
class InstitutionConfig:
    key: str
    name: str
    query: str
    # 펀드 매칭용 코드 컬럼 (K55/KR5 형식)
    fund_code_col: str
    # ETF 매칭용 코드 컬럼 (KR7 형식)
    etf_code_col: str
    name_col: str
    date_col: str
    avail_col: str
    start_col: str
    end_col: str
    risk_col: str       # 위험등급 컬럼


INSTITUTIONS: list[InstitutionConfig] = [
    InstitutionConfig(
        key="woori",
        name="우리은행",
        query="subject:우리은행 퇴직연금 상품목록 has:attachment",
        fund_code_col="예탁원펀드코드",   # KRZ (펀드) — K55 매핑 없어 미매칭
        etf_code_col="예탁원펀드코드",    # KR7 (ETF) — 동일 컬럼, prefix로 구분
        name_col="상품한글명",
        date_col="기준일자",
        avail_col="상품판매가능여부",
        start_col="취급시작일",
        end_col="취급종료일",
        risk_col="일임펀드위험구분코드",
    ),
    InstitutionConfig(
        key="bnk_busan",
        name="BNK부산은행",
        query="subject:BNK 부산은행 퇴직연금 상품목록 has:attachment",
        fund_code_col="rtpen_kofia_fund_cd",  # K55/KR5
        etf_code_col="rtpen_dpbd_fund_cd",    # KR7
        name_col="pdt_knm",
        date_col="crdt",
        avail_col="sell_psblyn",
        start_col="sell_strdt",
        end_col="sell_edt",
        risk_col="cmtg_fund_risk_dvcd",
    ),
    InstitutionConfig(
        key="bnk_gyeongnam",
        name="BNK경남은행",
        query="subject:BNK 경남은행 퇴직연금 상품목록 has:attachment",
        fund_code_col="퇴직연금상품통합관리번호",  # K55/KR5
        etf_code_col="예탁원펀드코드",             # KR7
        name_col="상품한글명",
        date_col="기준일자",
        avail_col="상품판매가능여부",
        start_col="취급시작일",
        end_col="취급종료일",
        risk_col="일임펀드위험구분코드",
    ),
]


# ── 모델 ───────────────────────────────────────────────────────

@dataclass
class FundItem:
    fund_code: str
    fund_name: str
    product_type: str       # 'fund' | 'etf' | 'unknown'
    available: bool
    risk_grade: Optional[int]
    start_date: Optional[str]
    end_date: Optional[str]
    matched: bool


@dataclass
class InstitutionResult:
    key: str
    name: str
    email_date: Optional[str]
    file_date: Optional[str]
    # 전체
    total: int
    # 펀드
    fund_total: int
    fund_matched: int
    # ETF
    etf_total: int
    etf_matched: int
    error: Optional[str]
    items: list[FundItem] = field(default_factory=list)

    @property
    def fund_unmatched(self) -> int:
        return self.fund_total - self.fund_matched

    @property
    def etf_unmatched(self) -> int:
        return self.etf_total - self.etf_matched

    @property
    def matched_count(self) -> int:
        return self.fund_matched + self.etf_matched

    @property
    def unmatched_count(self) -> int:
        return self.total - self.matched_count


# ── Gmail ──────────────────────────────────────────────────────

def _get_gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = os.getenv("GMAIL_TOKEN_PATH", "token.json")
    creds = Credentials.from_authorized_user_file(
        token_path,
        ["https://www.googleapis.com/auth/gmail.readonly"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def _find_attachment(parts: list) -> Optional[tuple[str, str]]:
    for part in parts:
        if part.get("parts"):
            r = _find_attachment(part["parts"])
            if r:
                return r
        fname = part.get("filename", "")
        att_id = part.get("body", {}).get("attachmentId", "")
        if fname and att_id and fname.lower().split(".")[-1] in ("csv", "xlsx", "xls"):
            return fname, att_id
    return None


def _parse_attachment(data: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(data)
    if filename.lower().endswith(".csv"):
        for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
            try:
                buf.seek(0)
                return pd.read_csv(buf, encoding=enc, dtype=str)
            except UnicodeDecodeError:
                pass
        raise ValueError("CSV 인코딩 감지 실패")
    return pd.read_excel(buf, dtype=str)


def _kst_date(date_str: str) -> str:
    """이메일 Date 헤더 → KST YYYY-MM-DD."""
    from email.utils import parsedate_to_datetime
    from datetime import timezone, timedelta
    try:
        dt = parsedate_to_datetime(date_str)
        kst = timezone(timedelta(hours=9))
        return dt.astimezone(kst).strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10]


# ── 메인 fetch ────────────────────────────────────────────────

def fetch_all(db_funds: set[str], db_etfs: set[str]) -> list[InstitutionResult]:
    """3개 기관 최신 첨부파일 파싱 + DB 크로스체크."""
    try:
        service = _get_gmail_service()
    except Exception as e:
        return [
            InstitutionResult(
                key=c.key, name=c.name,
                email_date=None, file_date=None,
                total=0, fund_total=0, fund_matched=0,
                etf_total=0, etf_matched=0,
                error=f"Gmail 인증 실패: {e}",
            )
            for c in INSTITUTIONS
        ]

    return [_fetch_one(service, cfg, db_funds, db_etfs) for cfg in INSTITUTIONS]


def _fetch_one(
    service,
    cfg: InstitutionConfig,
    db_funds: set[str],
    db_etfs: set[str],
) -> InstitutionResult:
    def err(msg: str) -> InstitutionResult:
        return InstitutionResult(
            key=cfg.key, name=cfg.name,
            email_date=None, file_date=None,
            total=0, fund_total=0, fund_matched=0,
            etf_total=0, etf_matched=0,
            error=msg,
        )

    try:
        resp = service.users().messages().list(userId="me", q=cfg.query, maxResults=1).execute()
        msgs = resp.get("messages", [])
        if not msgs:
            return err("최근 메일 없음")

        msg = service.users().messages().get(userId="me", id=msgs[0]["id"]).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        email_date = _kst_date(headers.get("Date", ""))

        att = _find_attachment(msg["payload"].get("parts", []))
        if not att:
            return err("첨부파일 없음")

        fname, att_id = att
        att_resp = service.users().messages().attachments().get(
            userId="me", messageId=msgs[0]["id"], id=att_id
        ).execute()
        df = _parse_attachment(base64.urlsafe_b64decode(att_resp["data"]), fname)
        file_date = str(df[cfg.date_col].iloc[0]).strip() if cfg.date_col in df.columns else None

        items: list[FundItem] = []
        for _, row in df.iterrows():
            etf_code = str(row.get(cfg.etf_code_col, "") or "").strip()
            fund_code = str(row.get(cfg.fund_code_col, "") or "").strip()
            name = str(row.get(cfg.name_col, "") or "").strip()
            avail = str(row.get(cfg.avail_col, "")).strip().upper() == "Y"
            risk_raw = str(row.get(cfg.risk_col, "") or "").strip()
            risk_grade = int(risk_raw) if risk_raw.isdigit() else None
            start = str(row.get(cfg.start_col, "") or "").strip() or None
            end_d = str(row.get(cfg.end_col, "") or "").strip() or None

            # ETF 여부: KSD 코드가 KR7로 시작
            is_etf = etf_code.startswith("KR7")

            if is_etf:
                code = etf_code
                product_type = "etf"
                matched = code in db_etfs
            else:
                # 펀드: KOFIA 코드 사용 (K55/KR5), 우리은행은 KRZ → 미매칭
                code = fund_code if fund_code and not fund_code.startswith("KR7") else etf_code
                product_type = "fund"
                matched = code in db_funds

            if not code or code == "nan":
                continue

            items.append(FundItem(
                fund_code=code, fund_name=name,
                product_type=product_type,
                available=avail, risk_grade=risk_grade,
                start_date=start, end_date=end_d,
                matched=matched,
            ))

        fund_items = [i for i in items if i.product_type == "fund"]
        etf_items  = [i for i in items if i.product_type == "etf"]

        return InstitutionResult(
            key=cfg.key, name=cfg.name,
            email_date=email_date, file_date=file_date,
            total=len(items),
            fund_total=len(fund_items),
            fund_matched=sum(1 for i in fund_items if i.matched),
            etf_total=len(etf_items),
            etf_matched=sum(1 for i in etf_items if i.matched),
            error=None,
            items=items,
        )

    except Exception as e:
        logger.error("기관 %s 로드 실패: %s", cfg.name, e, exc_info=True)
        return err(str(e))
