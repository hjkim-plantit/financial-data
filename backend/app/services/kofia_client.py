"""공공데이터포털 금융위원회 펀드상품기본정보 API 클라이언트.

출처: https://www.data.go.kr/data/15094792/openapi.do
엔드포인트: https://apis.data.go.kr/1160100/service/GetFundProductInfoService/getStandardCodeInfo
응답 형식: XML (기본) 또는 JSON

사전 준비:
  - data.go.kr 회원가입 → 마이페이지 → 일반 인증키 발급 (무료, 즉시)
  - .env 에 FSC_API_KEY=발급받은키 추가
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 공공데이터포털 금융위원회 API 베이스
_FSC_BASE = "https://apis.data.go.kr"
_FUND_STANDARD_CODE_PATH = "/1160100/service/GetFundProductInfoService/getStandardCodeInfo"


@dataclass
class KofiaFundRecord:
    """공공데이터포털 펀드상품기본정보 API 응답 레코드.

    필드명은 API 응답의 XML 태그명을 그대로 따름.
    """
    aso_std_cd: str       # 연관표준코드 12자리 K5코드 (asoStdCd)
    srtn_cd: str          # 단축코드 (srtnCd)
    fnd_nm: str           # 펀드명
    fnd_tp: str           # 펀드유형 (예: "주식형", "채권형", "부동산")
    ctg: str              # 분류 (펀드유형 세분류)
    bas_dt: Optional[str] = None   # 기준일자 YYYYMMDD

    # getStandardCodeInfo 미제공 → 별도 소스 필요
    management_company: str = ""
    inception_date: Optional[str] = None
    risk_grade: Optional[int] = None


class FscFundClient:
    """공공데이터포털 금융위원회 펀드 API 클라이언트 (비동기).

    Examples:
        async with FscFundClient(api_key="...") as client:
            records = await client.fetch_all_funds()
    """

    def __init__(self, api_key: str, timeout: float = 30.0):
        self._api_key = api_key
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "FscFundClient":
        self._client = httpx.AsyncClient(
            base_url=_FSC_BASE,
            timeout=self._timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    async def fetch_fund_page(
        self,
        page_no: int = 1,
        num_of_rows: int = 1000,
        fnd_tp: str = "",       # 빈 문자열 = 전체. 예: "주식형", "채권형"
        like_fnd_nm: str = "",  # 펀드명 부분 검색
    ) -> tuple[list[KofiaFundRecord], int]:
        """펀드 표준코드 정보 한 페이지 조회.

        Returns:
            (records, totalCount) 튜플.
        """
        assert self._client

        params: dict = {
            "serviceKey": self._api_key,
            "resultType": "xml",
            "pageNo": page_no,
            "numOfRows": num_of_rows,
        }
        if fnd_tp:
            params["fndTp"] = fnd_tp
        if like_fnd_nm:
            params["likeFndNm"] = like_fnd_nm

        resp = await self._client.get(_FUND_STANDARD_CODE_PATH, params=params)
        resp.raise_for_status()
        _check_api_error(resp.text)

        return _parse_standard_code_xml(resp.text)

    async def fetch_all_funds(self, num_of_rows: int = 1000) -> list[KofiaFundRecord]:
        """전체 펀드 표준코드 목록 페이지네이션 수집."""
        assert self._client

        all_records: list[KofiaFundRecord] = []
        page = 1

        while True:
            try:
                records, total = await self.fetch_fund_page(
                    page_no=page, num_of_rows=num_of_rows
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    # 공공데이터포털 일부 API는 마지막 페이지 이후 404 반환
                    logger.info("FSC API: page=%d 404 응답 → 수집 종료", page)
                    break
                raise

            all_records.extend(records)
            logger.info(
                "FSC 펀드 수집: page=%d, 이번=%d건, 누적=%d/%d",
                page, len(records), len(all_records), total,
            )

            if not records or len(all_records) >= total:
                break
            page += 1

        return all_records


# ------------------------------------------------------------------
# XML 파싱
# ------------------------------------------------------------------

def _check_api_error(xml_text: str) -> None:
    """공공데이터포털 에러 응답 감지 후 예외 발생."""
    try:
        root = ET.fromstring(xml_text)
        result_code = _text(root, ".//resultCode")
        result_msg = _text(root, ".//resultMsg")
        if result_code and result_code != "00":
            raise ValueError(f"API 오류 [{result_code}]: {result_msg}")
    except ET.ParseError:
        pass   # XML이 아닌 경우(JSON 등) 무시


def _parse_standard_code_xml(xml_text: str) -> tuple[list[KofiaFundRecord], int]:
    """getStandardCodeInfo 응답 XML → (records, totalCount).

    표준 data.go.kr 응답 구조:
      <response>
        <header><resultCode>00</resultCode>…</header>
        <body>
          <items>
            <item>
              <basDt>20240601</basDt>
              <srtnCd>KR5290801CF7</srtnCd>
              <fndNm>…</fndNm>
              <ctg>…</ctg>
              <fndTp>주식형</fndTp>
            </item>
          </items>
          <totalCount>12345</totalCount>
        </body>
      </response>
    """
    root = ET.fromstring(xml_text)

    total_el = root.find(".//totalCount")
    total = int(total_el.text) if total_el is not None and total_el.text else 0

    records: list[KofiaFundRecord] = []
    for item in root.findall(".//item"):
        aso_std_cd = _text(item, "asoStdCd")
        srtn_cd = _text(item, "srtnCd")
        if not aso_std_cd:
            continue
        records.append(
            KofiaFundRecord(
                aso_std_cd=aso_std_cd,
                srtn_cd=srtn_cd,
                fnd_nm=_text(item, "fndNm"),
                fnd_tp=_text(item, "fndTp"),
                ctg=_text(item, "ctg"),
                bas_dt=_text(item, "basDt") or None,
            )
        )

    return records, total


def _text(el: ET.Element, path: str) -> str:
    child = el.find(path)
    return (child.text or "").strip() if child is not None else ""
