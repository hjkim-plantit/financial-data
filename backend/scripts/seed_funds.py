#!/usr/bin/env python
"""
국내공모펀드 플랫폼 샘플 데이터 시드 스크립트

실행: python scripts/seed_funds.py [--crawl] [--sample]
  --crawl : 크롤링 시도 후 실패 시 샘플 데이터 사용 (기본값)
  --sample: 크롤링 없이 샘플 데이터만 사용
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import date

# ---------------------------------------------------------------------------
# 경로 설정: 스크립트 위치 기준 ../fund_platform.db
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "..", "fund_platform.db")

# ---------------------------------------------------------------------------
# KOFIA 분류 → 내부 분류 매핑
# ---------------------------------------------------------------------------
KOFIA_TO_INTERNAL = {
    "주식형": 1,
    "채권형": 2,
    "혼합주식형": 1,
    "혼합채권형": 2,
    "MMF": 2,
    "부동산": 4,
    "특별자산": 11,   # 기타로 기본 매핑
    "재간접": 1,
    "ETF주식": 1,
    "ETF채권": 2,
    "ETF부동산": 4,
    "ETF원자재": 11,
    "ETF통화": 6,
    "ETF인프라": 5,
}

# ---------------------------------------------------------------------------
# 샘플(fallback) 데이터
# ---------------------------------------------------------------------------
SAMPLE_FUNDS = [
    # (fund_code, fund_name, kofia_type, internal_category_id, management_company, inception_date)
    ("KR5223941C37", "삼성 코리아 주식 펀드 A",          "주식형",   1,  "삼성자산운용",         "2010-03-15"),
    ("KR5103342113", "미래에셋 가치주 펀드 C",            "주식형",   1,  "미래에셋자산운용",     "2008-06-20"),
    ("KR5103345678", "한국투자 배당주 펀드 A",            "주식형",   1,  "한국투자신탁운용",     "2015-01-10"),
    ("KR5103341234", "KB 스타 국내채권 펀드",             "채권형",   2,  "KB자산운용",           "2012-04-05"),
    ("KR5223942001", "신한 MMF 펀드 1호",                 "MMF",      2,  "신한자산운용",         "2005-09-01"),
    ("KR5223943101", "미래에셋 해외부동산 펀드",          "부동산",   4,  "미래에셋자산운용",     "2019-03-20"),
    ("KR5223943201", "삼성 글로벌인프라 특별자산",        "특별자산", 5,  "삼성자산운용",         "2018-07-15"),
    ("KR5223943301", "한화 달러인덱스 특별자산",          "특별자산", 6,  "한화자산운용",         "2020-11-01"),
    ("KR5223943401", "이스트스프링 금 특별자산",          "특별자산", 8,  "이스트스프링자산운용", "2017-05-10"),
    ("KR5223943501", "KB 에너지 특별자산",                "특별자산", 9,  "KB자산운용",           "2021-02-20"),
    ("KR5223943601", "신한 농산물 특별자산",              "특별자산", 10, "신한자산운용",         "2022-01-15"),
    ("KR5223943701", "삼성 글로벌 리츠 부동산",           "부동산",   4,  "삼성자산운용",         "2019-08-01"),
    ("KR5223943801", "한국투자 글로벌채권 혼합",          "혼합채권형", 2, "한국투자신탁운용",    "2016-03-10"),
    ("KR5223943901", "미래에셋 성장주 혼합 A",            "혼합주식형", 1, "미래에셋자산운용",    "2014-06-15"),
    ("KR5223944001", "KB 원자재 기타 특별자산",           "특별자산", 11, "KB자산운용",           "2020-05-01"),
]

SAMPLE_NAV = [
    # (fund_code, base_date, nav, aum(백만원))
    ("KR5223941C37", "2026-05-30", 1523.45,  285000),
    ("KR5103342113", "2026-05-30", 2841.20,  156000),
    ("KR5103345678", "2026-05-30", 1892.60,   98000),
    ("KR5103341234", "2026-05-30", 1102.35,  423000),
    ("KR5223942001", "2026-05-30", 1000.10, 1250000),
    ("KR5223943101", "2026-05-30",  987.40,   45000),
    ("KR5223943201", "2026-05-30", 1345.80,   32000),
    ("KR5223943301", "2026-05-30", 1678.90,   18000),
    ("KR5223943401", "2026-05-30", 2156.30,   28000),
    ("KR5223943501", "2026-05-30", 1432.10,   15000),
    ("KR5223943601", "2026-05-30", 1089.75,   12000),
    ("KR5223943701", "2026-05-30", 1234.56,   38000),
    ("KR5223943801", "2026-05-30", 1567.89,   65000),
    ("KR5223943901", "2026-05-30", 3421.50,   89000),
    ("KR5223944001", "2026-05-30", 1123.40,    9500),
]

SAMPLE_RETURNS = [
    # (fund_code, base_date, return_1m, return_3m, return_6m, return_ytd, return_1y, return_3y)
    ("KR5223941C37", "2026-05-30",  2.34,  5.67,  8.91, 12.45, 18.72, 42.31),
    ("KR5103342113", "2026-05-30",  1.89,  4.23,  7.56, 10.12, 15.43, 38.91),
    ("KR5103345678", "2026-05-30",  3.12,  6.78, 10.23, 14.56, 22.31, 51.23),
    ("KR5103341234", "2026-05-30",  0.45,  1.23,  2.34,  3.12,  4.89, 13.45),
    ("KR5223942001", "2026-05-30",  0.28,  0.82,  1.65,  2.15,  3.45,  9.87),
    ("KR5223943101", "2026-05-30", -0.89,  2.34,  4.56,  6.78, 12.34, 28.91),
    ("KR5223943201", "2026-05-30",  1.23,  3.45,  5.67,  7.89, 14.56, 35.67),
    ("KR5223943301", "2026-05-30",  0.67,  1.89,  3.21,  4.56,  8.91, 21.34),
    ("KR5223943401", "2026-05-30",  3.45,  8.91, 15.67, 22.34, 35.67, 78.91),
    ("KR5223943501", "2026-05-30", -1.23,  2.34,  5.67,  8.91, 18.34, 42.56),
    ("KR5223943601", "2026-05-30",  0.89,  2.45,  4.12,  5.67, 10.23, 24.56),
    ("KR5223943701", "2026-05-30",  1.56,  4.23,  7.89, 11.23, 19.45, 45.67),
    ("KR5223943801", "2026-05-30",  0.34,  1.12,  2.23,  3.45,  6.78, 18.91),
    ("KR5223943901", "2026-05-30",  4.56, 10.23, 16.78, 23.45, 38.91, 87.23),
    ("KR5223944001", "2026-05-30",  2.12,  5.45,  9.78, 13.45, 24.56, 58.91),
]

# ---------------------------------------------------------------------------
# 크롤링 함수
# ---------------------------------------------------------------------------

def _get_requests():
    """requests 임포트 (없으면 None 반환)."""
    try:
        import requests
        return requests
    except ImportError:
        print("[WARN] requests 라이브러리가 없습니다. 크롤링을 건너뜁니다.")
        return None


def crawl_naver_fund(requests_mod, max_pages: int = 3):
    """
    네이버 금융 펀드 목록 페이지에서 펀드 데이터를 수집합니다.

    네이버 금융 펀드 목록(fundList.naver)은 서버사이드 렌더링 HTML 테이블로
    제공됩니다. 주요 구조:
      <table class="type_1">
        <tr>
          <td class="fund_name"><a href="/fund/fundDetail.naver?fundCd=...">펀드명</a></td>
          <td>운용사</td>
          <td>유형</td>
          <td>기준가</td>
          <td>순자산(억)</td>
          <td>수익률(1개월)</td>
          <td>수익률(3개월)</td>
          <td>수익률(6개월)</td>
          <td>수익률(1년)</td>
        </tr>
      </table>

    href 에서 fundCd 쿼리파라미터로 펀드코드를 추출합니다.
    """
    try:
        from html.parser import HTMLParser
        import re
        import urllib.parse
    except ImportError:
        return None

    base_url = "https://finance.naver.com/fund/fundList.naver"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://finance.naver.com/fund/",
    }

    class NaverFundParser(HTMLParser):
        """네이버 금융 펀드 목록 HTML 파서."""

        def __init__(self):
            super().__init__()
            self.funds = []
            self._in_table = False
            self._in_tr = False
            self._cells = []
            self._current_cell = None
            self._current_href = None
            self._current_data = ""
            self._depth_table = 0
            self._depth_tr = 0
            self._skip_header = False

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if tag == "table":
                cls = attrs_dict.get("class", "")
                if "type_1" in cls:
                    self._in_table = True
                    self._depth_table += 1
            if self._in_table and tag == "tr":
                self._in_tr = True
                self._cells = []
                self._current_href = None
            if self._in_tr and tag in ("td", "th"):
                self._current_cell = tag
                self._current_data = ""
            if self._in_tr and tag == "a":
                href = attrs_dict.get("href", "")
                if "fundCd=" in href:
                    self._current_href = href

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self._in_tr and self._current_cell:
                self._cells.append({
                    "tag": self._current_cell,
                    "text": self._current_data.strip(),
                    "href": self._current_href,
                })
                self._current_cell = None
                self._current_href = None
                self._current_data = ""
            if tag == "tr" and self._in_tr:
                self._in_tr = False
                self._process_row()
            if tag == "table" and self._in_table:
                self._depth_table -= 1
                if self._depth_table <= 0:
                    self._in_table = False

        def handle_data(self, data):
            if self._current_cell:
                self._current_data += data

        def _process_row(self):
            """행 데이터를 파싱하여 펀드 정보 추출."""
            cells = self._cells
            # 헤더 행 또는 데이터 부족한 행 건너뜀
            if len(cells) < 5:
                return
            if any(c["tag"] == "th" for c in cells):
                return

            # 첫 번째 td: 펀드명 + href
            fund_cell = cells[0]
            fund_name = fund_cell["text"]
            href = fund_cell.get("href") or ""

            # fundCd 추출
            fund_code = None
            if "fundCd=" in href:
                parsed = urllib.parse.urlparse(href)
                qs = urllib.parse.parse_qs(parsed.query)
                codes = qs.get("fundCd", [])
                if codes:
                    fund_code = codes[0]

            if not fund_code or not fund_name:
                return

            # 두 번째 td: 운용사
            mgmt = cells[1]["text"] if len(cells) > 1 else ""

            # 세 번째 td: 유형
            fund_type_raw = cells[2]["text"] if len(cells) > 2 else ""

            # 기준가 (네 번째 td)
            nav_str = cells[3]["text"] if len(cells) > 3 else ""
            try:
                nav_val = float(nav_str.replace(",", ""))
            except ValueError:
                nav_val = None

            # 순자산(억) (다섯 번째 td)
            aum_str = cells[4]["text"] if len(cells) > 4 else ""
            try:
                # 억원 단위 → 백만원으로 변환 (*100)
                aum_val = int(float(aum_str.replace(",", "")) * 100)
            except ValueError:
                aum_val = None

            # 수익률 (인덱스 5~8: 1개월, 3개월, 6개월, 1년)
            def _ret(idx):
                if len(cells) > idx:
                    try:
                        return float(cells[idx]["text"].replace(",", "").replace("%", ""))
                    except ValueError:
                        return None
                return None

            ret_1m = _ret(5)
            ret_3m = _ret(6)
            ret_6m = _ret(7)
            ret_1y = _ret(8)

            # KOFIA 유형 정규화 (네이버는 "주식형", "채권형" 등 사용)
            fund_type = fund_type_raw.strip()

            self.funds.append({
                "fund_code": fund_code,
                "fund_name": fund_name,
                "kofia_type": fund_type,
                "management_company": mgmt,
                "nav": nav_val,
                "aum": aum_val,
                "return_1m": ret_1m,
                "return_3m": ret_3m,
                "return_6m": ret_6m,
                "return_1y": ret_1y,
            })

    all_funds = []
    print(f"[네이버 금융] 펀드 목록 크롤링 시작 (최대 {max_pages}페이지)...")

    for page in range(1, max_pages + 1):
        try:
            params = {"order": "1", "fundType": "ALL", "page": str(page)}
            resp = requests_mod.get(base_url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            resp.encoding = "euc-kr"

            parser = NaverFundParser()
            parser.feed(resp.text)

            page_funds = parser.funds
            if not page_funds:
                print(f"  [네이버 금융] 페이지 {page}: 데이터 없음, 중단")
                break

            print(f"  [네이버 금융] 페이지 {page}: {len(page_funds)}건 수집")
            all_funds.extend(page_funds)

        except Exception as exc:
            print(f"  [네이버 금융] 페이지 {page} 오류: {exc}")
            break

    if all_funds:
        print(f"[네이버 금융] 총 {len(all_funds)}건 수집 완료")
    else:
        print("[네이버 금융] 수집 실패")

    return all_funds if all_funds else None


def crawl_krx_etf(requests_mod):
    """
    KRX 데이터포털에서 ETF 목록을 수집합니다.

    POST /comm/bldAttendant/getJsonData.cmd
    응답 JSON 구조:
      {
        "output": [
          {
            "ISU_SRT_CD": "069500",       // 단축코드
            "ISU_CD": "KR7069500007",     // ISIN 코드 (12자리)
            "ISU_NM": "KODEX 200",        // ETF명
            "MKT_NM": "유가증권",
            "SECT_TP_NM": "국내 주식",    // 유형
            "NAV": "38541.62",            // 기준가
            "MKTCAP": "12345678",         // 시가총액(백만원)
            "RETURN_1M": "1.23",
            "RETURN_3M": "3.45",
            "RETURN_6M": "5.67",
            "RETURN_1Y": "10.23",
          },
          ...
        ]
      }

    SECT_TP_NM → KOFIA 유형 매핑:
      "국내 주식" / "해외 주식"  → ETF주식
      "국내 채권" / "해외 채권"  → ETF채권
      "부동산"                   → ETF부동산
      "원자재"                   → ETF원자재
      "통화"                     → ETF통화
      "인프라"                   → ETF인프라
    """
    url = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdimain.cmd",
        "Origin": "https://data.krx.co.kr",
    }
    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT04301",
        "locale": "ko_KR",
        "tboxisuSrtCd_finder_tuco0_1": "",
        "isuSrtCd": "",
        "codeNmCombined": "1",
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }

    # SECT_TP_NM → KOFIA 유형 매핑
    SECT_TO_KOFIA = {
        "국내 주식": "ETF주식",
        "해외 주식": "ETF주식",
        "국내주식": "ETF주식",
        "해외주식": "ETF주식",
        "주식": "ETF주식",
        "국내 채권": "ETF채권",
        "해외 채권": "ETF채권",
        "국내채권": "ETF채권",
        "해외채권": "ETF채권",
        "채권": "ETF채권",
        "부동산": "ETF부동산",
        "원자재": "ETF원자재",
        "통화": "ETF통화",
        "인프라": "ETF인프라",
        "혼합": "ETF주식",
        "기타": "ETF주식",
    }

    print("[KRX] ETF 목록 크롤링 시작...")
    try:
        resp = requests_mod.post(url, headers=headers, data=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        output = data.get("output") or data.get("OutBlock_1") or []
        if not output:
            print("[KRX] 응답에 데이터 없음")
            return None

        etfs = []
        today_str = date.today().isoformat()

        for item in output:
            # ISIN 코드 우선, 없으면 단축코드 앞에 KR 접두어
            isin = (
                item.get("ISU_CD")
                or item.get("ISIN")
                or item.get("isuCd")
                or ""
            ).strip()
            short_cd = (
                item.get("ISU_SRT_CD")
                or item.get("isuSrtCd")
                or ""
            ).strip()

            # fund_code: ISIN 12자리 우선, 없으면 단축코드
            fund_code = isin if len(isin) == 12 else short_cd
            if not fund_code:
                continue

            fund_name = (
                item.get("ISU_NM")
                or item.get("ISU_ABBRV")
                or item.get("isuNm")
                or ""
            ).strip()
            if not fund_name:
                continue

            sect = (item.get("SECT_TP_NM") or item.get("sectTpNm") or "").strip()
            # 부분 매칭으로 KOFIA 유형 결정
            kofia_type = "ETF주식"  # 기본값
            for key, val in SECT_TO_KOFIA.items():
                if key in sect:
                    kofia_type = val
                    break

            def _f(field_candidates):
                for f in field_candidates:
                    v = item.get(f)
                    if v not in (None, "", "-", "N/A"):
                        try:
                            return float(str(v).replace(",", ""))
                        except ValueError:
                            pass
                return None

            nav_val = _f(["NAV", "nav", "NAV_PRC"])
            # 시가총액: KRX는 백만원 단위로 제공
            mktcap_raw = _f(["MKTCAP", "mktcap", "MKTCAP_AMT"])
            aum_val = int(mktcap_raw) if mktcap_raw is not None else None

            ret_1m = _f(["RETURN_1M", "return1m", "FLUC_RT_1M"])
            ret_3m = _f(["RETURN_3M", "return3m", "FLUC_RT_3M"])
            ret_6m = _f(["RETURN_6M", "return6m", "FLUC_RT_6M"])
            ret_1y = _f(["RETURN_1Y", "return1y", "FLUC_RT_1Y"])

            etfs.append({
                "fund_code": fund_code[:12],  # funds.fund_code VARCHAR(12)
                "fund_name": fund_name,
                "kofia_type": kofia_type,
                "management_company": (
                    item.get("MGR_NM")
                    or item.get("mgrNm")
                    or item.get("MGMT_CO")
                    or "미확인"
                ).strip(),
                "nav": nav_val,
                "aum": aum_val,
                "return_1m": ret_1m,
                "return_3m": ret_3m,
                "return_6m": ret_6m,
                "return_1y": ret_1y,
            })

        print(f"[KRX] 총 {len(etfs)}건 수집 완료")
        return etfs if etfs else None

    except Exception as exc:
        print(f"[KRX] 크롤링 오류: {exc}")
        return None


# ---------------------------------------------------------------------------
# DB 삽입 함수
# ---------------------------------------------------------------------------

def get_connection():
    """SQLite 연결 반환."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def insert_funds_from_crawl(conn, crawled_funds, today_str: str):
    """
    크롤링 데이터(네이버/KRX 공통 dict 리스트)를 DB에 삽입합니다.
    각 dict 키: fund_code, fund_name, kofia_type, management_company,
                nav, aum, return_1m, return_3m, return_6m, return_1y
    """
    cur = conn.cursor()
    fund_count = nav_count = ret_count = 0
    skipped = 0

    for item in crawled_funds:
        fund_code = item.get("fund_code", "").strip()
        fund_name = item.get("fund_name", "").strip()
        kofia_type = item.get("kofia_type", "").strip()
        mgmt = item.get("management_company", "미확인").strip() or "미확인"

        if not fund_code or not fund_name:
            skipped += 1
            continue

        # 내부 분류 결정
        internal_cat_id = KOFIA_TO_INTERNAL.get(kofia_type, 1)

        # 펀드 기본 정보 upsert
        cur.execute(
            """
            INSERT OR REPLACE INTO funds
              (fund_code, fund_name, kofia_fund_type, internal_category_id,
               management_company, inception_date, investment_region, base_currency, status)
            VALUES (?, ?, ?, ?, ?, ?, '국내', 'KRW', '운용중')
            """,
            (fund_code, fund_name, kofia_type, internal_cat_id, mgmt, "2000-01-01"),
        )
        fund_count += 1

        # NAV 삽입 (있을 때만) — (fund_code, base_date) 중복 시 UPDATE
        nav_val = item.get("nav")
        aum_val = item.get("aum")
        if nav_val is not None:
            cur.execute(
                "SELECT id FROM fund_nav WHERE fund_code=? AND base_date=?",
                (fund_code, today_str),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE fund_nav SET nav=?, aum=? WHERE id=?",
                    (nav_val, aum_val, existing[0]),
                )
            else:
                cur.execute(
                    "INSERT INTO fund_nav (fund_code, base_date, nav, aum) VALUES (?, ?, ?, ?)",
                    (fund_code, today_str, nav_val, aum_val),
                )
            nav_count += 1

        # 수익률 삽입 (있을 때만) — (fund_code, base_date) 중복 시 UPDATE
        ret_1m = item.get("return_1m")
        ret_3m = item.get("return_3m")
        ret_6m = item.get("return_6m")
        ret_1y = item.get("return_1y")
        if any(v is not None for v in [ret_1m, ret_3m, ret_6m, ret_1y]):
            cur.execute(
                "SELECT id FROM fund_returns WHERE fund_code=? AND base_date=?",
                (fund_code, today_str),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """UPDATE fund_returns
                       SET return_1m=?, return_3m=?, return_6m=?, return_1y=?
                       WHERE id=?""",
                    (ret_1m, ret_3m, ret_6m, ret_1y, existing[0]),
                )
            else:
                cur.execute(
                    """INSERT INTO fund_returns
                         (fund_code, base_date, return_1m, return_3m, return_6m, return_1y)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (fund_code, today_str, ret_1m, ret_3m, ret_6m, ret_1y),
                )
            ret_count += 1

    conn.commit()
    print(f"  -> 펀드 {fund_count}건 삽입/갱신, NAV {nav_count}건, 수익률 {ret_count}건 삽입 (건너뜀: {skipped}건)")


def insert_sample_funds(conn):
    """샘플 펀드 기본 정보를 DB에 삽입합니다."""
    cur = conn.cursor()
    count = 0
    for row in SAMPLE_FUNDS:
        fund_code, fund_name, kofia_type, internal_cat_id, mgmt, inception = row
        cur.execute(
            """
            INSERT OR REPLACE INTO funds
              (fund_code, fund_name, kofia_fund_type, internal_category_id,
               management_company, inception_date, investment_region, base_currency, status)
            VALUES (?, ?, ?, ?, ?, ?, '국내', 'KRW', '운용중')
            """,
            (fund_code, fund_name, kofia_type, internal_cat_id, mgmt, inception),
        )
        count += 1
    conn.commit()
    print(f"  -> 펀드 기본정보 {count}건 삽입/갱신 완료")


def insert_sample_nav(conn):
    """샘플 NAV 데이터를 DB에 삽입합니다."""
    cur = conn.cursor()
    count = 0
    for fund_code, base_date, nav, aum in SAMPLE_NAV:
        # aum: 백만원 단위 (BigInteger 컬럼에는 원 단위로 저장)
        aum_won = aum * 1_000_000
        cur.execute(
            "SELECT id FROM fund_nav WHERE fund_code=? AND base_date=?",
            (fund_code, base_date),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE fund_nav SET nav=?, aum=? WHERE id=?",
                (nav, aum_won, existing[0]),
            )
        else:
            cur.execute(
                "INSERT INTO fund_nav (fund_code, base_date, nav, aum) VALUES (?, ?, ?, ?)",
                (fund_code, base_date, nav, aum_won),
            )
        count += 1
    conn.commit()
    print(f"  -> NAV {count}건 삽입/갱신 완료")


def insert_sample_returns(conn):
    """샘플 수익률 데이터를 DB에 삽입합니다."""
    cur = conn.cursor()
    count = 0
    for row in SAMPLE_RETURNS:
        fund_code, base_date, r1m, r3m, r6m, ryt, r1y, r3y = row
        cur.execute(
            """
            INSERT OR REPLACE INTO fund_returns
              (fund_code, base_date, return_1m, return_3m, return_6m,
               return_ytd, return_1y, return_3y)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fund_code, base_date, r1m, r3m, r6m, ryt, r1y, r3y),
        )
        count += 1
    conn.commit()
    print(f"  -> 수익률 {count}건 삽입/갱신 완료")


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="국내공모펀드 플랫폼 샘플 데이터 시드 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  python scripts/seed_funds.py          # 크롤링 시도 후 실패시 샘플 사용\n"
            "  python scripts/seed_funds.py --crawl  # 동일\n"
            "  python scripts/seed_funds.py --sample # 샘플 데이터만 사용\n"
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--crawl",
        action="store_true",
        default=False,
        help="크롤링 시도 후 실패 시 샘플 데이터 사용 (기본값)",
    )
    group.add_argument(
        "--sample",
        action="store_true",
        default=False,
        help="크롤링 없이 샘플 데이터만 사용",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # scripts/ 폴더가 없으면 생성 (이 스크립트 자체가 여기 있어야 하지만 방어 처리)
    os.makedirs(SCRIPT_DIR, exist_ok=True)

    # DB 연결 확인
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB 파일을 찾을 수 없습니다: {DB_PATH}")
        print("  먼저 백엔드 서버를 한 번 실행하여 DB를 초기화하세요.")
        sys.exit(1)

    print(f"[INFO] DB 경로: {os.path.abspath(DB_PATH)}")
    conn = get_connection()

    # internal_categories 확인
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM internal_categories")
    cat_count = cur.fetchone()[0]
    print(f"[INFO] internal_categories: {cat_count}건 확인됨")

    # --sample 이면 크롤링 없이 샘플만
    use_sample_only = args.sample
    # --crawl 또는 기본(둘 다 False) → 크롤링 시도
    try_crawl = not use_sample_only

    today_str = date.today().isoformat()
    crawl_success = False

    if try_crawl:
        requests_mod = _get_requests()
        if requests_mod is None:
            print("[WARN] requests 없음 → 샘플 데이터로 전환")
        else:
            # 1순위: 네이버 금융
            print("\n[STEP 1] 네이버 금융 펀드 데이터 크롤링...")
            naver_funds = crawl_naver_fund(requests_mod, max_pages=3)
            if naver_funds:
                print(f"[STEP 1] 네이버 금융 데이터 {len(naver_funds)}건 → DB 삽입 중...")
                insert_funds_from_crawl(conn, naver_funds, today_str)
                crawl_success = True
            else:
                print("[STEP 1] 네이버 금융 크롤링 실패 또는 데이터 없음")

            # 2순위: KRX ETF (네이버 성공 여부와 무관하게 추가 시도)
            print("\n[STEP 2] KRX ETF 데이터 크롤링...")
            krx_etfs = crawl_krx_etf(requests_mod)
            if krx_etfs:
                print(f"[STEP 2] KRX ETF 데이터 {len(krx_etfs)}건 → DB 삽입 중...")
                insert_funds_from_crawl(conn, krx_etfs, today_str)
                crawl_success = True
            else:
                print("[STEP 2] KRX ETF 크롤링 실패 또는 데이터 없음")

    # 크롤링 실패 또는 샘플 전용 모드
    if not crawl_success:
        if try_crawl:
            print("\n[FALLBACK] 크롤링 실패 → 샘플 데이터 삽입으로 전환합니다.")
        else:
            print("\n[SAMPLE] 샘플 데이터 삽입 모드")

        print("\n[STEP A] 샘플 펀드 기본정보 삽입...")
        insert_sample_funds(conn)

        print("\n[STEP B] 샘플 NAV 데이터 삽입...")
        insert_sample_nav(conn)

        print("\n[STEP C] 샘플 수익률 데이터 삽입...")
        insert_sample_returns(conn)

    # 최종 현황 출력
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM funds")
    total_funds = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM fund_nav")
    total_nav = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM fund_returns")
    total_returns = cur.fetchone()[0]

    print("\n" + "=" * 50)
    print("[완료] DB 현황")
    print(f"  funds        : {total_funds}건")
    print(f"  fund_nav     : {total_nav}건")
    print(f"  fund_returns : {total_returns}건")
    print("=" * 50)

    conn.close()


if __name__ == "__main__":
    main()
