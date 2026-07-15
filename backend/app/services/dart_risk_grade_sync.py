"""DART(금융감독원 전자공시) 간이투자설명서 → ETF 실제 위험등급 동기화.

근사값을 쓰지 않고, 각 ETF 운용사가 법정 공시(간이투자설명서/투자설명서)에
명시한 실제 "투자 위험 등급"만 채운다. 데이터가 없으면 NULL로 둔다.

흐름:
  1. funds 테이블에서 product_type='etf'인 종목을 management_company별로 묶는다.
  2. 회사별로 DART list.json에서 최근 공시 목록을 가져와 "투자설명서"가 포함된
     report_nm만 남기고, [기재정정] 등 정정공시는 최신 1건으로 정리한다.
  3. 각 ETF의 fund_name과 report_nm을 정규화해 매칭한다.
  4. 매칭된 공시의 PDF를 뷰어 3단계로 내려받아 텍스트를 추출하고
     "투자 위험 등급" 뒤의 "N등급(라벨)" 패턴을 뽑는다.
  5. funds.risk_grade를 실제 값으로 업데이트한다.

DART 뷰어(dart.fss.or.kr)는 분당 100회 이상 호출 시 IP가 1시간 차단되므로,
뷰어 호출 사이에 최소 1초 간격을 둔다 (VIEWER_REQUEST_INTERVAL).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_OPENDART_BASE = "https://opendart.fss.or.kr/api"
_VIEWER_BASE = "https://dart.fss.or.kr"

VIEWER_REQUEST_INTERVAL = 1.0  # 초 — 이 값 밑으로 내리지 말 것 (분당 100회 제한)

# ── 운용사명 → DART corp_code ────────────────────────────────
# corpCode.xml에서 사전 조회한 값. 새 운용사가 생기면 여기에 추가.
CORP_CODE_MAP: dict[str, str] = {
    "삼성자산운용": "00260453",
    "삼성액티브자산운용": "01194731",
    "미래에셋자산운용": "00259776",
    "케이비자산운용": "00104500",
    "kb자산운용": "00104500",
    "한국투자신탁운용": "00324548",
    "한화자산운용": "00243395",
    "키움투자자산운용": "00120191",
    "신한자산운용": "00243553",
    "엔에이치아문디자산운용": "00453804",
    "하나자산운용": "00326272",
    "타임폴리오자산운용": "00787154",
    "우리자산운용": "00331478",
    "에셋플러스자산운용": "00336701",
    "비엔케이자산운용": "00686776",
    "bnk자산운용": "00686776",
    "흥국자산운용": "00330725",
    "브이아이자산운용": "00260514",
    "디비자산운용": "00241388",
    "아이비케이자산운용": "00516468",
    "교보악사자산운용": "00241412",
    "현대자산운용": "00695394",
    "마이다스에셋자산운용": "00267526",
    "대신자산운용": "00110918",
    "케이씨지아이자산운용": "00685935",
    "한국투자밸류자산운용": "00564030",
    "트러스톤자산운용": "00259794",
    "유리자산운용": "00324830",
    "아이엠에셋자산운용": "00631475",
    "더제이자산운용": "00883078",
}

# 운용사 전부가 공통으로 쓰는 규제 문안: "...위험도를 감안하여 N등급으로 분류하였습니다".
# "투자위험등급" 라벨과 실제 값이 같이 붙어있지 않은 문서(예: 신한자산운용)에서도
# 이 분류 문장은 항상 등장하므로, 라벨 앵커보다 이 패턴을 우선으로 삼는다.
_RISK_CLASSIFY_RE = re.compile(r"([1-6])\s*등급\s*으?\s*로\s*분류")

# 폴백: "투자위험등급" 라벨 뒤 일정 범위 안에서 "N등급(라벨)" 값을 찾는다.
_RISK_LABEL_RE = re.compile(r"투자\s*위험\s*등급")
_RISK_VALUE_RE = re.compile(r"([1-6])\s*등급\s*[\(\[]([^)\]]{2,10})[\)\]]")
_RISK_SEARCH_WINDOW = 800  # "투자위험등급" 라벨 뒤로 이 글자수 이내에서 실제 값을 찾는다

_STRIP_CHARS_RE = re.compile(r"[()\[\]\-·,.\s]")
_BRACKET_CONTENT_RE = re.compile(r"[\(\[][^)\]]*[\)\]]")


def _normalize(s: str) -> str:
    return _STRIP_CHARS_RE.sub("", s or "").lower()


def _core_name(s: str) -> str:
    """괄호/대괄호로 감싼 수식어(합성, 파생형 등)를 통째로 제거한 핵심 상품명.

    DART 공식 명칭은 '하나1QCD금리액티브...[채권혼합-파생형](합성)'처럼 수식어를
    상품유형 뒤로 재배치하는 경우가 많아, 원래 fund_name의 수식어를 그대로 붙여
    부분일치를 시도하면 실패한다. 수식어를 아예 제거하고 핵심 이름만 비교한다.
    """
    return _normalize(_BRACKET_CONTENT_RE.sub("", s or ""))


def normalize_company(name: str) -> str:
    """'삼성자산운용(주)', '신한자산운용 주식회사' → '삼성자산운용', '신한자산운용'."""
    n = (name or "").strip()
    n = n.replace("주식회사", "").replace("(주)", "")
    return _normalize(n)


@dataclass
class ProspectusFiling:
    rcept_no: str
    report_nm: str
    rcept_dt: str


class RateLimiter:
    """DART 뷰어 호출 간 최소 간격을 보장하는 간단한 스로틀러."""

    def __init__(self, interval: float = VIEWER_REQUEST_INTERVAL):
        self._interval = interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self._interval:
                await asyncio.sleep(self._interval - delta)
            self._last = time.monotonic()


_viewer_limiter = RateLimiter()


# ── DART API 호출 ────────────────────────────────────────────

async def fetch_company_filings(
    client: httpx.AsyncClient,
    corp_code: str,
    dart_api_key: str,
    years_back: int = 3,
) -> list[ProspectusFiling]:
    """회사의 최근 N년치 공시 중 '투자설명서'가 들어간 것만 반환 (정정 중복 제거, 최신순)."""
    end = date.today()
    begin = end - timedelta(days=365 * years_back)

    raw: list[dict] = []
    page = 1
    while True:
        resp = await client.get(
            f"{_OPENDART_BASE}/list.json",
            params={
                "crtfc_key": dart_api_key,
                "corp_code": corp_code,
                "bgn_de": begin.strftime("%Y%m%d"),
                "end_de": end.strftime("%Y%m%d"),
                "page_no": page,
                "page_count": 100,
            },
            timeout=30,
        )
        data = resp.json()
        status = data.get("status")
        if status == "013":  # 조회된 데이터가 없습니다
            break
        if status != "000":
            logger.warning("DART list.json 오류: corp_code=%s status=%s message=%s", corp_code, status, data.get("message"))
            break

        raw.extend(data.get("list", []))
        total_page = data.get("total_page", 1)
        if page >= total_page:
            break
        page += 1
        await asyncio.sleep(0.2)

    filings = [
        ProspectusFiling(r["rcept_no"], r["report_nm"], r["rcept_dt"])
        for r in raw
        if "투자설명서" in r.get("report_nm", "")
    ]
    return filings


def match_filings(fund_name: str, filings: list[ProspectusFiling]) -> list[ProspectusFiling]:
    """정규화한 fund_name이 report_nm에 부분일치하는 공시를 최신순으로 반환.

    [기재정정] 등 정정공시는 부분 재제출이라 표지(위험등급 페이지)가 빠진 경우가
    있으므로, 하나만 고르지 않고 후보 전체를 반환해 호출부에서 순서대로 시도한다.

    fund_name 전체를 그대로 부분일치 시켰을 때 못 찾으면, 괄호/대괄호 수식어를
    제거한 핵심 이름으로 다시 시도한다 — DART 공식 명칭은 '(합성)', '[파생형]' 같은
    수식어를 상품유형 뒤로 재배치해서 두는 경우가 많아, 원래 수식어 위치 그대로
    이어 붙이면 매칭에 실패하기 때문이다.
    """
    candidates = _match_by(_normalize(fund_name), filings)
    if candidates:
        return candidates
    core = _core_name(fund_name)
    if core and core != _normalize(fund_name):
        candidates = _match_by(core, filings)
    return candidates


def _match_by(target: str, filings: list[ProspectusFiling]) -> list[ProspectusFiling]:
    if not target:
        return []
    candidates = [f for f in filings if target in _normalize(f.report_nm)]
    candidates.sort(key=lambda f: f.rcept_dt, reverse=True)
    return candidates


async def download_prospectus_pdf(client: httpx.AsyncClient, rcept_no: str) -> bytes | None:
    """뷰어 3단계(main.do → download/main.do → file.do)로 PDF 원문을 받는다."""
    await _viewer_limiter.wait()
    main_url = f"{_VIEWER_BASE}/dsaf001/main.do?rcpNo={rcept_no}"
    r1 = await client.get(main_url, headers={"User-Agent": _UA, "Referer": _VIEWER_BASE}, timeout=20)
    m = re.search(r"dcmNo=(\d+)", r1.text)
    if not m:
        return None
    dcm_no = m.group(1)

    await _viewer_limiter.wait()
    step2_url = f"{_VIEWER_BASE}/pdf/download/main.do?rcp_no={rcept_no}&dcm_no={dcm_no}"
    r2 = await client.get(step2_url, headers={"User-Agent": _UA, "Referer": main_url}, timeout=20)
    m2 = re.search(r"file\.do\?[^\"'\s]+", r2.text)
    if not m2:
        return None
    file_url = f"{_VIEWER_BASE}/pdf/download/{m2.group(0)}"

    await _viewer_limiter.wait()
    r3 = await client.get(file_url, headers={"User-Agent": _UA, "Referer": step2_url}, timeout=30)
    if not r3.content.startswith(b"%PDF"):
        return None
    return r3.content


def extract_risk_grade(pdf_bytes: bytes) -> tuple[int, str] | None:
    """ETF 위험등급을 추출한다. 두 가지 방식을 순서대로 시도한다.

    1순위: "...위험도를 감안하여 N등급으로 분류하였습니다" 분류 문장 패턴.
           운용사 전부가 공통으로 쓰는 규제 문안이라 가장 신뢰도가 높고,
           "투자위험등급" 라벨이 근처에 아예 없는 문서(예: 신한자산운용)에서도 동작한다.
    2순위: "투자위험등급" 라벨을 찾고 그 뒤 일정 범위 안에서 "N등급(라벨)" 값을 찾는다
           (라벨과 값 사이 거리가 회사마다 달라 윈도우 탐색으로 처리).
    """
    from pypdf import PdfReader
    import io

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text_content = ""
    for p in reader.pages[:3]:  # 위험등급은 항상 표지(1~2p)에 있음
        text_content += (p.extract_text() or "") + "\n"

    classify = _RISK_CLASSIFY_RE.search(text_content)
    if classify:
        grade = int(classify.group(1))
        value = _RISK_VALUE_RE.search(text_content)
        label = value.group(2) if value and int(value.group(1)) == grade else ""
        return grade, label

    label_match = _RISK_LABEL_RE.search(text_content)
    if not label_match:
        return None

    window = text_content[label_match.end(): label_match.end() + _RISK_SEARCH_WINDOW]
    m = _RISK_VALUE_RE.search(window)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


# ── 메인 동기화 ───────────────────────────────────────────────

async def sync_dart_risk_grades(
    db: AsyncSession,
    dart_api_key: str,
    years_back: int = 3,
    limit: int | None = None,
    only_missing: bool = False,
) -> dict:
    """funds(product_type='etf')의 risk_grade를 DART 실제 공시 값으로 채운다.

    only_missing=True면 이미 risk_grade가 채워진 ETF는 건너뛴다 (매칭/추출 로직
    개선 후 남은 결측치만 다시 채울 때 사용 — 이미 성공한 건을 다시 호출해
    뷰어 rate limit을 낭비하지 않는다).
    """
    where = "product_type = 'etf'" + (" AND risk_grade IS NULL" if only_missing else "")
    rows = (
        await db.execute(
            text(f"SELECT fund_code, fund_name, management_company FROM funds WHERE {where}")
        )
    ).mappings().all()
    if limit:
        rows = rows[:limit]

    by_company: dict[str, list[dict]] = {}
    for r in rows:
        by_company.setdefault(r["management_company"], []).append(r)

    stats = {"total": len(rows), "matched": 0, "extracted": 0, "no_corp_code": 0, "no_filing": 0, "extract_failed": 0}

    async with httpx.AsyncClient() as client:
        for company, funds in by_company.items():
            corp_code = CORP_CODE_MAP.get(normalize_company(company))
            if not corp_code:
                stats["no_corp_code"] += len(funds)
                logger.warning("DART corp_code 미매핑: %s (%d개 ETF 스킵)", company, len(funds))
                continue

            try:
                filings = await fetch_company_filings(client, corp_code, dart_api_key, years_back)
            except Exception as exc:
                logger.error("DART list.json 조회 실패: %s error=%s", company, exc)
                continue

            logger.info("%s: 공시 %d건, ETF %d개", company, len(filings), len(funds))

            for fund in funds:
                candidates = match_filings(fund["fund_name"], filings)
                if not candidates:
                    stats["no_filing"] += 1
                    continue
                stats["matched"] += 1

                # 최신 공시부터 최대 3건까지 시도 — [기재정정] 부분 재제출본은
                # 표지(위험등급 페이지)가 빠져 있을 수 있어 실패 시 이전 공시로 폴백
                result = None
                for filing in candidates[:3]:
                    try:
                        pdf_bytes = await download_prospectus_pdf(client, filing.rcept_no)
                        if pdf_bytes is None:
                            continue
                        result = extract_risk_grade(pdf_bytes)
                    except Exception as exc:
                        logger.warning("추출 실패: fund_code=%s rcept_no=%s error=%s", fund["fund_code"], filing.rcept_no, exc)
                        continue
                    if result is not None:
                        break

                if result is None:
                    stats["extract_failed"] += 1
                    continue

                grade, label = result
                await db.execute(
                    text("UPDATE funds SET risk_grade = :g WHERE fund_code = :c"),
                    {"g": grade, "c": fund["fund_code"]},
                )
                stats["extracted"] += 1
                logger.info("위험등급 반영: %s (%s) → %d등급(%s)", fund["fund_code"], fund["fund_name"], grade, label)

    await db.commit()
    return stats
