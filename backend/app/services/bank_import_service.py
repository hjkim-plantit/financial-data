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
import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ── 종목 마스터 분류 ───────────────────────────────────────────

# internal_category_id → 자산군 (허용값만)
_CAT_TO_ASSET: dict[int, str] = {
    1:  "주식",
    2:  "채권",
    4:  "대체투자-부동산",
    5:  "대체투자-인프라",
    6:  "대체투자-통화/외환",
    8:  "대체투자-원자재-금속",
    9:  "대체투자-원자재-에너지",
    10: "대체투자-원자재-농산물",
    11: "대체투자-원자재-기타",
}

# 펀드명 키워드 → 자산군 (DB 미매칭 시 폴백)
_ASSET_PATTERNS: list[tuple[str, str]] = [
    (r"채권|국채|회사채|국공채|bond|fixed.?income|mmf|money.?market|단기금융|머니마켓", "채권"),
    (r"부동산|리츠|reit", "대체투자-부동산"),
    (r"인프라|infrastructure", "대체투자-인프라"),
    (r"통화|외환|currency|forex", "대체투자-통화/외환"),
    (r"원유|wti|브렌트|brent|crude|천연가스|natural.?gas", "대체투자-원자재-에너지"),
    (r"금\b|은\b|gold|silver|귀금속|copper|구리|metal|platinum", "대체투자-원자재-금속"),
    (r"농산물|agri|grain|corn|wheat|soybean", "대체투자-원자재-농산물"),
    (r"원자재|commodity|commodities", "대체투자-원자재-기타"),
]

# 펀드명 키워드 → 지역 (우선순위 순)
_REGION_PATTERNS: list[tuple[str, str]] = [
    (r"미국|s&p|sp500|nasdaq|나스닥|다우|dow|russell|뉴욕|us\s", "선진국-미국"),
    (r"일본|japan|nikkei|니케이|topix", "선진국-일본"),
    (r"영국|uk\s|ftse|런던", "선진국-영국"),
    (r"독일|germany|dax|프랑크푸르트", "선진국-독일"),
    (r"프랑스|france|cac", "선진국-프랑스"),
    (r"스위스|switzerland|swiss", "선진국-스위스"),
    (r"싱가포르|singapore", "선진국-싱가포르"),
    (r"선진국|developed|eafe", "선진국-기타"),
    (r"중국|china|csi|후강퉁|선강퉁|홍콩|hang.?seng|항셍", "신흥국-중국"),
    (r"한국|korea|kospi|kosdaq|코스피|코스닥", "신흥국-한국"),
    (r"대만|taiwan", "신흥국-대만"),
    (r"인도|india|nifty", "신흥국-인도"),
    (r"베트남|vietnam|viet", "신흥국-베트남"),
    (r"남아공|south.?africa", "신흥국-남아공"),
    (r"신흥국|emerging|\bem\b", "신흥국-기타"),
    (r"글로벌|global|world|전세계|msci|all.?country", "글로벌"),
]

# 펀드명 키워드 → 섹터 (허용값만; 미매칭 시 해당없음)
_SECTOR_PATTERNS: list[tuple[str, str]] = [
    (r"헬스케어|바이오|제약|pharma|health|bio|의료|biotech", "헬스케어"),
    (r"반도체|semiconductor|소프트|software|정보기술|테크|tech|ai\b|인공지능|클라우드|cloud|인터넷|it\s", "정보기술"),
    (r"원유|wti|브렌트|천연가스|에너지|oil|gas|energy|petroleum", "에너지"),
    (r"금융|은행|보험|증권|bank|financ|insuran", "금융"),
    (r"부동산|리츠|reit", "부동산"),
    (r"소재|material|화학|chemical|steel|철강", "소재"),
    (r"산업재|industri|항공우주|방산|defense|aerospace", "산업재"),
    (r"필수소비재|consumer.?staple|식품|food|농식품", "필수소비재"),
    (r"임의소비재|consumer.?disc|유통|retail|여행|레저|엔터|entertainment", "임의소비재"),
    (r"통신|telecom|커뮤니케이션|communication|media|미디어", "통신서비스"),
    (r"유틸리티|util|전력|electric.?power", "유틸리티"),
]


def _classify_asset_class(name: str, category_id: Optional[int]) -> str:
    if category_id and category_id in _CAT_TO_ASSET:
        return _CAT_TO_ASSET[category_id]
    for pattern, value in _ASSET_PATTERNS:
        if re.search(pattern, name, re.I):
            return value
    return "주식"  # 기본값


def _classify_region(name: str, db_region: Optional[str]) -> str:
    for pattern, value in _REGION_PATTERNS:
        if re.search(pattern, name, re.I):
            return value
    if db_region == "글로벌":
        return "글로벌"
    if db_region == "해외":
        return "선진국-기타"
    return "신흥국-한국"  # 국내 기본값


def _classify_sector(name: str) -> str:
    for pattern, value in _SECTOR_PATTERNS:
        if re.search(pattern, name, re.I):
            return value
    return "해당없음"


# ── 기관별 설정 ────────────────────────────────────────────────

@dataclass
class InstitutionConfig:
    key: str
    name: str
    query: str
    # 각 필드마다 후보 컬럼명 목록 — 실제 파일에서 존재하는 첫 번째 사용
    fund_code_cols: list[str]   # K55/KR5 펀드 코드
    etf_code_cols: list[str]    # KR7 ETF 코드
    name_cols: list[str]
    date_cols: list[str]
    avail_cols: list[str]
    start_cols: list[str]
    end_cols: list[str]
    risk_cols: list[str]

    def resolve(self, df: "pd.DataFrame") -> dict[str, str | None]:
        """실제 DataFrame 컬럼과 매핑해 사용할 컬럼명 dict 반환."""
        cols = set(df.columns)

        def pick(candidates: list[str]) -> str | None:
            for c in candidates:
                if c in cols:
                    return c
            return None

        resolved = {
            "fund_code": pick(self.fund_code_cols),
            "etf_code":  pick(self.etf_code_cols),
            "name":      pick(self.name_cols),
            "date":      pick(self.date_cols),
            "avail":     pick(self.avail_cols),
            "start":     pick(self.start_cols),
            "end":       pick(self.end_cols),
            "risk":      pick(self.risk_cols),
        }

        missing = [k for k, v in resolved.items() if v is None and k not in ("fund_code", "start", "end", "risk")]
        if missing:
            logger.warning(
                "%s: 일부 컬럼 감지 실패 %s — 실제 컬럼: %s",
                self.name, missing, sorted(cols),
            )

        return resolved


INSTITUTIONS: list[InstitutionConfig] = [
    InstitutionConfig(
        key="woori",
        name="우리은행",
        query="subject:우리은행 퇴직연금 상품목록 has:attachment",
        fund_code_cols=["예탁원펀드코드", "rtpen_dpbd_fund_cd"],
        etf_code_cols= ["예탁원펀드코드", "rtpen_dpbd_fund_cd"],
        name_cols=     ["상품한글명", "pdt_knm"],
        date_cols=     ["기준일자", "crdt"],
        avail_cols=    ["상품판매가능여부", "sell_psblyn"],
        start_cols=    ["취급시작일", "sell_strdt"],
        end_cols=      ["취급종료일", "sell_edt"],
        risk_cols=     ["일임펀드위험구분코드", "cmtg_fund_risk_dvcd"],
    ),
    InstitutionConfig(
        key="bnk_busan",
        name="BNK부산은행",
        # [우리자산운용] 이메일 제외, 예탁원 코드 기준
        query='"BNK 부산은행 퇴직연금 상품목록" -"우리자산운용" has:attachment',
        fund_code_cols=["예탁원펀드코드", "rtpen_dpbd_fund_cd"],  # KRZ 기준
        etf_code_cols= ["예탁원펀드코드", "rtpen_dpbd_fund_cd"],
        name_cols=     ["상품한글명", "pdt_knm"],
        date_cols=     ["기준일자", "crdt"],
        avail_cols=    ["상품판매가능여부", "sell_psblyn"],
        start_cols=    ["취급시작일", "sell_strdt"],
        end_cols=      ["취급종료일", "sell_edt"],
        risk_cols=     ["일임펀드위험구분코드", "cmtg_fund_risk_dvcd"],
    ),
    InstitutionConfig(
        key="bnk_gyeongnam",
        name="BNK경남은행",
        # [우리자산운용] 이메일 제외, 예탁원 코드 기준
        query='"BNK 경남은행 퇴직연금 상품목록" -"우리자산운용" has:attachment',
        fund_code_cols=["예탁원펀드코드", "rtpen_dpbd_fund_cd"],  # KRZ 기준
        etf_code_cols= ["예탁원펀드코드", "rtpen_dpbd_fund_cd"],
        name_cols=     ["상품한글명", "pdt_knm"],
        date_cols=     ["기준일자", "crdt"],
        avail_cols=    ["상품판매가능여부", "sell_psblyn"],
        start_cols=    ["취급시작일", "sell_strdt"],
        end_cols=      ["취급종료일", "sell_edt"],
        risk_cols=     ["일임펀드위험구분코드", "cmtg_fund_risk_dvcd"],
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
    asset_class: str = ""   # 자산군
    region: str = ""        # 지역
    sector: str = ""        # 섹터


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


def _find_all_attachments(parts: list) -> list[tuple[str, str]]:
    """이메일 파트에서 모든 CSV/xlsx 첨부파일 목록 반환."""
    results = []
    for part in parts:
        if part.get("parts"):
            results.extend(_find_all_attachments(part["parts"]))
        fname  = part.get("filename", "")
        att_id = part.get("body", {}).get("attachmentId", "")
        if fname and att_id and fname.lower().rsplit(".", 1)[-1] in ("csv", "xlsx", "xls"):
            results.append((fname, att_id))
    return results


def _find_attachment(parts: list) -> Optional[tuple[str, str]]:
    """[우리자산운용] 없는 파일 우선 선택 — KRZ 코드 포함 은행 직발 파일 우선."""
    atts = _find_all_attachments(parts)
    if not atts:
        return None
    preferred = [a for a in atts if "우리자산운용" not in a[0]]
    return preferred[0] if preferred else atts[0]


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

def fetch_all(
    db_funds: set[str],
    db_etfs: set[str],
    db_meta: dict[str, dict],
) -> list[InstitutionResult]:
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

    return [_fetch_one(service, cfg, db_funds, db_etfs, db_meta) for cfg in INSTITUTIONS]


def _fetch_one(
    service,
    cfg: InstitutionConfig,
    db_funds: set[str],
    db_etfs: set[str],
    db_meta: dict[str, dict],
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
        # 최대 5건 조회 후 [우리자산운용] 이메일 프로그래밍 방식으로도 제외 (안전망)
        resp = service.users().messages().list(userId="me", q=cfg.query, maxResults=5).execute()
        msgs = resp.get("messages", [])
        if not msgs:
            return err("최근 메일 없음")

        msg = None
        headers: dict[str, str] = {}
        for m in msgs:
            candidate = service.users().messages().get(userId="me", id=m["id"]).execute()
            hdrs = {h["name"]: h["value"] for h in candidate["payload"]["headers"]}
            if "우리자산운용" in hdrs.get("Subject", ""):
                continue
            msg = candidate
            headers = hdrs
            break

        if msg is None:
            return err("유효한 이메일 없음 (우리자산운용 이메일만 존재)")

        email_date = _kst_date(headers.get("Date", ""))

        att = _find_attachment(msg["payload"].get("parts", []))
        if not att:
            return err("첨부파일 없음")

        fname, att_id = att
        att_resp = service.users().messages().attachments().get(
            userId="me", messageId=msg["id"], id=att_id
        ).execute()
        df = _parse_attachment(base64.urlsafe_b64decode(att_resp["data"]), fname)

        # 컬럼 자동 감지
        c = cfg.resolve(df)
        if c["etf_code"] is None and c["fund_code"] is None:
            return err(
                f"필수 코드 컬럼 없음 — 실제 컬럼: {sorted(df.columns.tolist())}"
            )

        file_date = str(df[c["date"]].iloc[0]).strip() if c["date"] else None

        items: list[FundItem] = []
        for _, row in df.iterrows():
            etf_code  = str(row.get(c["etf_code"],  "") or "").strip() if c["etf_code"]  else ""
            fund_code = str(row.get(c["fund_code"],  "") or "").strip() if c["fund_code"] else ""
            name      = str(row.get(c["name"],       "") or "").strip() if c["name"]      else ""
            avail     = str(row.get(c["avail"],      "")).strip().upper() == "Y" if c["avail"] else True
            risk_raw  = str(row.get(c["risk"],       "") or "").strip() if c["risk"]      else ""
            risk_grade = int(risk_raw) if risk_raw.isdigit() else None
            start     = (str(row.get(c["start"], "") or "").strip() or None) if c["start"] else None
            end_d     = (str(row.get(c["end"],   "") or "").strip() or None) if c["end"]   else None

            # 판매가능 Y + 취급종료일 99991231인 상품만 수집
            if not avail:
                continue
            if end_d and end_d.replace("-", "") != "99991231":
                continue

            # ETF 여부: KSD 코드가 KR7로 시작
            is_etf = etf_code.startswith("KR7")

            if is_etf:
                code = etf_code
                product_type = "etf"
                matched = code in db_etfs
            else:
                # KRZ(예탁원) 우선 → K55(KOFIA) 폴백
                if etf_code.startswith("KRZ"):
                    code = etf_code
                elif fund_code and not fund_code.startswith("KR7"):
                    code = fund_code
                else:
                    code = etf_code
                product_type = "fund"
                matched = code in db_funds

            if not code or code == "nan":
                continue

            meta = db_meta.get(code, {})
            items.append(FundItem(
                fund_code=code, fund_name=name,
                product_type=product_type,
                available=avail, risk_grade=risk_grade,
                start_date=start, end_date=end_d,
                matched=matched,
                asset_class=_classify_asset_class(name, meta.get("category_id")),
                region=_classify_region(name, meta.get("region")),
                sector=_classify_sector(name),
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
