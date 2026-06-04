"""공공데이터포털 펀드상품기본정보 → DB 동기화 서비스.

API 필드 → DB 매핑:
  srtn_cd   → fund_code   (12자리 KR 표준코드)
  fnd_nm    → fund_name
  fnd_tp    → kofia_fund_type + internal_category_id (매핑 규칙 적용)
  ctg       → 보조 분류 (fnd_tp 매핑 실패 시 참조)
  펀드명 키워드 → investment_region
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine as _db_engine
from app.models.fund import Fund
from app.services.kofia_client import FscFundClient, KofiaFundRecord

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 1. 펀드유형(fnd_tp / ctg) → internal_category_id 매핑
# ------------------------------------------------------------------
# 실제 API 응답의 fndTp 값 확인 후 조정 필요.
# 현재 값은 금융위원회 공공데이터포털 문서 기준 추정값.

_FND_TP_MAP: dict[str, int] = {
    # ── 주식 (id=1) ──────────────────────────────
    "주식형":           1,
    "주식혼합형":       1,
    "혼합주식형":       1,
    # ── 채권 (id=2) ──────────────────────────────
    "채권형":           2,
    "채권혼합형":       2,
    "혼합채권형":       2,
    "단기금융":         2,   # MMF
    # ── 부동산 (id=4) ────────────────────────────
    "부동산":           4,
    # ── 인프라 (id=5) ────────────────────────────
    "인프라":           5,
    "사회간접자본":     5,
    # ── 통화/외환 (id=6) ─────────────────────────
    "통화":             6,
    # ── 원자재-금속 (id=8) ───────────────────────
    "귀금속":           8,
    # ── 원자재-에너지 (id=9) ─────────────────────
    "에너지":           9,
    # ── 원자재-농산물 (id=10) ────────────────────
    "농산물":           10,
    # ── 원자재-기타 / 특별자산 (id=11) ───────────
    "특별자산":         11,
    "원자재":           11,
}

# fnd_tp 매핑 실패 시 ctg(분류) 필드로 2차 시도 (같은 테이블 재사용)
_CTG_MAP = _FND_TP_MAP

# 최후 수단: 펀드명 키워드 매핑
_NAME_KEYWORD_MAP: list[tuple[str, int]] = [
    (r"(주식|equity|stock)", 1),
    (r"(채권|bond|fixed.?income)", 2),
    (r"(부동산|real.?estate|reit)", 4),
    (r"(인프라|infrastructure)", 5),
    (r"(통화|외환|currency|fx)", 6),
    (r"(금속|귀금속|gold|silver|metal)", 8),
    (r"(에너지|energy|원유|oil)", 9),
    (r"(농산물|grain|agri|corn|wheat)", 10),
]


def map_to_internal_category(record: KofiaFundRecord) -> Optional[int]:
    """fnd_tp → 펀드명 키워드 순서로 internal_category_id 결정.
    ctg 필드는 모든 레코드가 "자산운용"으로 동일하여 분류에 미사용.
    """
    cat = _FND_TP_MAP.get(record.fnd_tp)
    if cat:
        return cat

    name_lower = record.fnd_nm.lower()
    for pattern, cid in _NAME_KEYWORD_MAP:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return cid

    return None


# ------------------------------------------------------------------
# 2. 지역 추출 (펀드명 키워드 기반)
# ------------------------------------------------------------------
_REGION_PATTERNS: list[tuple[str, str]] = [
    (r"(미국|US|S&P|nasdaq|나스닥|다우|dow)", "선진국-미국"),
    (r"(일본|japan|nikkei|니케이)", "선진국-일본"),
    (r"(영국|uk|ftse)", "선진국-영국"),
    (r"(독일|germany|dax)", "선진국-독일"),
    (r"(프랑스|france|cac)", "선진국-프랑스"),
    (r"(스위스|switzerland|swiss)", "선진국-스위스"),
    (r"(싱가포르|singapore)", "선진국-싱가포르"),
    (r"(선진국|developed|EAFE)", "선진국-기타"),
    (r"(중국|china|csi|후강퉁|선강퉁|홍콩|hang.?seng)", "신흥국-중국"),
    (r"(한국|korea|kospi|kosdaq)", "신흥국-한국"),
    (r"(대만|taiwan)", "신흥국-대만"),
    (r"(인도|india)", "신흥국-인도"),
    (r"(베트남|vietnam)", "신흥국-베트남"),
    (r"(남아공|south.?africa)", "신흥국-남아공"),
    (r"(신흥국|emerging|\bEM\b)", "신흥국-기타"),
    (r"(글로벌|global|world|전세계)", "글로벌"),
]


def extract_region(fnd_nm: str) -> str:
    for pattern, region in _REGION_PATTERNS:
        if re.search(pattern, fnd_nm, re.IGNORECASE):
            return region
    return "국내"


# ------------------------------------------------------------------
# 3. DB upsert
# ------------------------------------------------------------------

async def sync_fsc_funds(
    db: AsyncSession,
    api_key: str,
    dry_run: bool = False,
) -> dict:
    """공공데이터포털에서 전체 공모펀드를 수집하여 funds 테이블에 upsert.

    Args:
        db: 비동기 DB 세션
        api_key: data.go.kr 에서 발급받은 서비스키
        dry_run: True 이면 DB에 쓰지 않고 통계만 반환

    Returns:
        {"total": N, "upserted": N, "skipped": N, "no_category": N}

    Note:
        management_company, inception_date, risk_grade 는 이 API에서 미제공.
        - management_company: 펀드명에서 운용사명 추출하거나 별도 소스 필요
        - risk_grade: finlife.fss.or.kr (금감원 금융상품한눈에) API 별도 연동 필요
        - inception_date: 미기재 시 DB 제약 위반으로 해당 펀드 건너뜀
    """
    async with FscFundClient(api_key=api_key) as client:
        raw_records = await client.fetch_all_funds()

    logger.info("FSC API 수집 완료: %d건", len(raw_records))

    # 제외 유형
    _SKIP_TYPES = {"변액보험", "파생상품"}

    # 온라인 클래스 필터: A-e 또는 C-e 클래스만 포함
    _CLASS_PATTERN = re.compile(
        r'(종류A-[eE]|ClassA-[eE]|Class A-[eE]'
        r'|종류C-[eE]|ClassC[eE]|Class C[eE])\b'
    )

    stats = {"total": len(raw_records), "upserted": 0, "skipped": 0, "no_category": 0}
    rows: list[dict] = []

    for rec in raw_records:
        if rec.fnd_tp in _SKIP_TYPES:
            stats["skipped"] += 1
            continue
        if not _CLASS_PATTERN.search(rec.fnd_nm):
            stats["skipped"] += 1
            continue

        category_id = map_to_internal_category(rec)
        if category_id is None:
            stats["no_category"] += 1
            logger.debug("분류 불가: %s %s (fnd_tp=%s, ctg=%s)",
                         rec.srtn_cd, rec.fnd_nm, rec.fnd_tp, rec.ctg)

        mgmt_co = _extract_mgmt_company(rec.fnd_nm)

        rows.append({
            "fund_code": rec.aso_std_cd,
            "fund_name": rec.fnd_nm,
            "management_company": mgmt_co,
            "kofia_fund_type": rec.fnd_tp or rec.ctg or None,
            "internal_category_id": category_id or 99,  # 99 = 미분류
            "investment_region": extract_region(rec.fnd_nm),
            # risk_grade / inception_date 는 별도 소스에서 보강
        })

    if not rows:
        return stats

    if dry_run:
        stats["upserted"] = len(rows)
        return stats

    # inception_date 가 NOT NULL 인데 이 API에서 미제공 → 임시로 '1900-01-01' 사용
    # 실제 운영 시 별도 소스에서 설정일 보강 후 업데이트 필요
    from datetime import date
    PLACEHOLDER_DATE = date(1900, 1, 1)
    for r in rows:
        r.setdefault("inception_date", PLACEHOLDER_DATE)

    stmt = sqlite_insert(Fund).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["fund_code"],
        set_={
            "fund_name":           stmt.excluded.fund_name,
            "management_company":  stmt.excluded.management_company,
            "kofia_fund_type":     stmt.excluded.kofia_fund_type,
            # 수동 편집 보호: 이미 분류된 펀드는 덮어쓰지 않으려면
            # 아래 두 줄을 주석 처리하고 수동으로 관리
            "internal_category_id": stmt.excluded.internal_category_id,
            "investment_region":    stmt.excluded.investment_region,
        },
    )
    await db.execute(stmt)
    await db.commit()

    stats["upserted"] = len(rows)
    return stats


# ------------------------------------------------------------------
# 헬퍼
# ------------------------------------------------------------------

# 주요 운용사명 — 펀드명 앞부분에 등장하는 패턴
_MGMT_CO_PREFIXES = [
    "삼성자산운용", "미래에셋자산운용", "KB자산운용", "신한자산운용",
    "한국투자신탁운용", "한화자산운용", "키움투자자산운용", "하나UBS자산운용",
    "NH-아문디자산운용", "교보악사자산운용", "흥국자산운용", "IBK자산운용",
    "이스트스프링자산운용", "피델리티자산운용", "블랙록자산운용",
    "AB자산운용", "슈로더자산운용", "JP모간자산운용", "프랭클린템플턴",
]


def _extract_mgmt_company(fnd_nm: str) -> str:
    for co in _MGMT_CO_PREFIXES:
        if fnd_nm.startswith(co):
            return co
    # 괄호 앞 첫 단어를 운용사명으로 추정
    parts = fnd_nm.split("(")[0].split()
    return parts[0] if parts else "미상"
