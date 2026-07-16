"""PlantIt Admin(Django admin) 연동 서비스.

기관별 최신 이메일 상품 목록과 PlantIt admin의 자산/유니버스 등록 상태를 비교하고,
미등록 상품을 admin에 등록(자산 신규 + 유니버스 추가)한다.

주의:
  - 유니버스 업데이트는 전체 asset 목록 교체 POST — 기존 목록을 먼저 읽어 보존하고 추가만 한다.
  - FUND 등록 시 단축코드(symbol)는 종목코드(isin) 전체와 반드시 일치 (예: KRZ50267150B).
    ETF는 isin[3:9] 축약형.
  - 우리은행은 선별 유니버스(U7/U8)라 자동 연동 금지 — 자산 존재 여부만 확인/등록.
"""

from __future__ import annotations

import html as html_mod
import logging
import re
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 기관 key(bank_import_service.INSTITUTIONS와 동일) → PlantIt 유니버스 ID (운영계)
INSTITUTION_UNIVERSES: dict[str, dict[str, int | None]] = {
    "woori":         {"etf": None, "fund": None},
    "bnk_busan":     {"etf": 11,   "fund": 12},
    "bnk_gyeongnam": {"etf": 13,   "fund": 14},
}
UNIVERSE_NAMES = {11: "BNK부산_EMP", 12: "BNK부산_FoF", 13: "BNK경남_EMP", 14: "BNK경남_FoF"}

_CSRF_RE = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')


class PlantitAdminError(Exception):
    pass


class PlantitAdminClient:
    """세션 로그인 기반 PlantIt admin 클라이언트 (요청 단위로 생성/폐기)."""

    def __init__(self) -> None:
        if not settings.plantit_admin_user or not settings.plantit_admin_password:
            raise PlantitAdminError("PLANTIT_ADMIN_USER/PASSWORD 미설정 (.env 확인)")
        self._base = settings.plantit_admin_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base, timeout=60.0, follow_redirects=True
        )

    async def __aenter__(self) -> "PlantitAdminClient":
        await self._login()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def _login(self) -> None:
        r = await self._client.get("/admin/login/")
        m = _CSRF_RE.search(r.text)
        if not m:
            raise PlantitAdminError("로그인 페이지 CSRF 토큰 파싱 실패")
        await self._client.post(
            "/admin/login/",
            data={
                "csrfmiddlewaretoken": m.group(1),
                "username": settings.plantit_admin_user,
                "password": settings.plantit_admin_password,
                "next": "/admin/",
            },
            headers={"Referer": f"{self._base}/admin/login/"},
        )
        if "sessionid" not in self._client.cookies:
            raise PlantitAdminError("PlantIt admin 로그인 실패 (계정/비밀번호 확인)")

    async def build_isin_map(self) -> dict[str, str]:
        """유니버스 add 페이지의 asset option 전체 → {isin: asset_id}."""
        r = await self._client.get("/admin/products/universe/add/")
        code_to_id: dict[str, str] = {}
        for opt in re.finditer(r'<option value="(\d+)"[^>]*>([^<]+)</option>', r.text):
            aid, aname = opt.group(1), opt.group(2).strip()
            m = re.search(r"\(([A-Z0-9]{8,})\)\s*$", aname)
            if m:
                code_to_id[m.group(1)] = aid
        if not code_to_id:
            raise PlantitAdminError("admin 자산 목록 파싱 실패 (권한/세션 확인)")
        return code_to_id

    async def get_asset_id(self, isin: str) -> str | None:
        """ISIN 검색으로 자산 ID 조회 (isin 맵 미포함 건 폴백)."""
        r = await self._client.get("/admin/products/asset/", params={"q": isin})
        m = re.search(r"/admin/products/asset/(\d+)/change/", r.text)
        return m.group(1) if m else None

    async def get_universe_assets(self, universe_id: int) -> set[str]:
        """유니버스 change 페이지에서 현재 등록된 asset ID 집합."""
        r = await self._client.get(f"/admin/products/universe/{universe_id}/change/")
        block = re.search(r'id="id_assets"[^>]*>(.*?)</select>', r.text, re.S)
        if not block:
            raise PlantitAdminError(f"Universe {universe_id} 자산 목록 파싱 실패")
        return set(re.findall(r'<option value="(\d+)"[^>]*selected', block.group(1)))

    async def register_asset(
        self, name: str, isin: str, asset_type: str
    ) -> tuple[bool, str]:
        """자산 신규 등록. 반환 (ok, asset_id 또는 오류메시지)."""
        add_path = "/admin/products/asset/add/"
        r = await self._client.get(add_path)
        m = _CSRF_RE.search(r.text)
        if not m:
            return False, "CSRF 토큰 파싱 실패"
        csrf = m.group(1)
        # FUND는 symbol = isin 전체, ETF는 isin[3:9] 축약형
        symbol = isin if asset_type == "FUND" else isin[3:9]
        data = [
            ("csrfmiddlewaretoken", csrf),
            ("name", name),
            ("isin", isin),
            ("symbol", symbol),
            ("market_type", "DOMESTIC"),
            ("asset_type", asset_type),
            ("is_managed", "on"),
            ("_save", "저장"),
        ]
        r2 = await self._client.post(
            add_path,
            data=data,
            headers={"Referer": f"{self._base}{add_path}", "X-CSRFToken": csrf},
        )
        final_url = str(r2.url)
        if "add" not in final_url and "/asset/" in final_url:
            m2 = re.search(r"/asset/(\d+)/change/", final_url)
            if m2:
                return True, m2.group(1)
            aid = await self.get_asset_id(isin)
            return (True, aid) if aid else (False, "등록 후 ID 조회 실패")
        errs = re.findall(r'class="errorlist[^>]*">(.*?)</ul>', r2.text, re.S)
        err = " | ".join(re.sub(r"<[^>]+>", "", e).strip() for e in errs)
        return False, err[:200] or f"status={r2.status_code}"

    async def update_universe(
        self, universe_id: int, asset_ids: set[str]
    ) -> tuple[bool, str]:
        """유니버스 자산 목록 전체 교체 POST (asset_ids = 최종 전체 집합)."""
        path = f"/admin/products/universe/{universe_id}/change/"
        r = await self._client.get(path)
        csrf_m = _CSRF_RE.search(r.text)
        name_m = re.search(r'<input[^>]*name="name"[^>]*value="([^"]*)"', r.text) or re.search(
            r'<input[^>]*value="([^"]*)"[^>]*name="name"', r.text
        )
        if not csrf_m:
            return False, "CSRF 토큰 파싱 실패"
        if not name_m or not name_m.group(1):
            return False, f"유니버스 이름 파싱 실패 (Universe {universe_id})"
        csrf = csrf_m.group(1)
        data = [("csrfmiddlewaretoken", csrf), ("name", html_mod.unescape(name_m.group(1)))]
        for aid in sorted(asset_ids, key=int):
            data.append(("assets", aid))
        data.append(("_save", "저장"))
        r2 = await self._client.post(
            path,
            data=data,
            headers={"Referer": f"{self._base}{path}", "X-CSRFToken": csrf},
        )
        errs = re.findall(r'class="errorlist[^>]*">(.*?)</ul>', r2.text, re.S)
        err = " | ".join(re.sub(r"<[^>]+>", "", e).strip() for e in errs)
        if not err and "/universe/" in str(r2.url):
            return True, str(r2.url)
        return False, err[:200] or str(r2.url)


# ── 비교/적용 오케스트레이션 (다기관 통합, 세션 1회) ──────────

WOORI_NOTE = (
    "우리은행은 선별 유니버스(U7/U8) 운영 — 자산 등록 여부만 확인하며 유니버스는 변경하지 않습니다."
)


@dataclass
class SyncItem:
    raw_code: str      # KRZ/KR7 예탁원 코드 = admin ISIN
    fund_name: str
    product_type: str  # 'fund' | 'etf'


@dataclass
class InstitutionSummary:
    key: str
    total: int = 0
    registered: int = 0
    missing: int = 0


@dataclass
class MissingProduct:
    raw_code: str
    fund_name: str
    product_type: str
    asset_missing: bool = False
    # (기관 key, 유니버스 ID) — 이 상품을 추가해야 할 유니버스 목록
    universe_targets: list[tuple[str, int]] = field(default_factory=list)
    # 이 상품이 미등록 상태로 발견된 기관 key 목록 (구분자)
    institutions: list[str] = field(default_factory=list)


@dataclass
class CompareAllResult:
    admin_asset_total: int
    universe_counts: dict[int, int] = field(default_factory=dict)
    institutions: list[InstitutionSummary] = field(default_factory=list)
    universe_note: str | None = None
    missing: list[MissingProduct] = field(default_factory=list)


def _validate_keys(reqs: list[tuple[str, list[SyncItem]]]) -> None:
    for key, _ in reqs:
        if key not in INSTITUTION_UNIVERSES:
            raise PlantitAdminError(f"알 수 없는 기관 key: {key}")


def _needed_universes(reqs: list[tuple[str, list[SyncItem]]]) -> set[int]:
    return {
        uid
        for key, _ in reqs
        for uid in INSTITUTION_UNIVERSES[key].values()
        if uid is not None
    }


async def _resolve_asset_id(
    admin: PlantitAdminClient, isin: str,
    isin_map: dict[str, str], cache: dict[str, str | None],
) -> str | None:
    if isin in isin_map:
        return isin_map[isin]
    if isin not in cache:
        cache[isin] = await admin.get_asset_id(isin)
    return cache[isin]


async def compare_institutions(
    reqs: list[tuple[str, list[SyncItem]]],
) -> CompareAllResult:
    """여러 기관의 이메일 상품 목록 vs admin 등록 상태 통합 비교 (읽기 전용).

    같은 상품이 여러 기관에서 미등록이면 하나의 MissingProduct로 묶고
    universe_targets/institutions로 어느 기관·유니버스에서 빠졌는지 구분한다.
    """
    _validate_keys(reqs)

    async with PlantitAdminClient() as admin:
        isin_map = await admin.build_isin_map()
        members: dict[int, set[str]] = {}
        for uid in sorted(_needed_universes(reqs)):
            members[uid] = await admin.get_universe_assets(uid)

        result = CompareAllResult(
            admin_asset_total=len(isin_map),
            universe_counts={uid: len(m) for uid, m in members.items()},
            universe_note=WOORI_NOTE if any(k == "woori" for k, _ in reqs) else None,
        )

        lookup_cache: dict[str, str | None] = {}
        missing_by_code: dict[str, MissingProduct] = {}

        for key, items in reqs:
            cfg = INSTITUTION_UNIVERSES[key]
            summary = InstitutionSummary(key=key, total=len(items))

            for item in items:
                aid = await _resolve_asset_id(admin, item.raw_code, isin_map, lookup_cache)
                uid = cfg["etf" if item.product_type == "etf" else "fund"]

                asset_missing = aid is None
                universe_missing = (
                    aid is not None and uid is not None and aid not in members[uid]
                )

                if not asset_missing and not universe_missing:
                    summary.registered += 1
                    continue

                summary.missing += 1
                mp = missing_by_code.setdefault(item.raw_code, MissingProduct(
                    raw_code=item.raw_code, fund_name=item.fund_name,
                    product_type=item.product_type,
                ))
                if asset_missing:
                    mp.asset_missing = True
                # 자산이 없어도 유니버스 대상이면 등록 후 추가해야 하므로 target에 포함
                if uid is not None and (key, uid) not in mp.universe_targets:
                    mp.universe_targets.append((key, uid))
                if key not in mp.institutions:
                    mp.institutions.append(key)

            result.institutions.append(summary)

        result.missing = list(missing_by_code.values())
        return result


@dataclass
class ApplyItemResult:
    raw_code: str
    fund_name: str
    ok: bool
    asset_created: bool = False
    universes_added: list[int] = field(default_factory=list)
    detail: str = ""


@dataclass
class ApplyUniverseResult:
    universe_id: int
    universe_name: str
    added: int
    ok: bool
    detail: str = ""


@dataclass
class ApplyAllResult:
    items: list[ApplyItemResult] = field(default_factory=list)
    universes: list[ApplyUniverseResult] = field(default_factory=list)


async def apply_institutions(
    reqs: list[tuple[str, list[SyncItem]]],
) -> ApplyAllResult:
    """미등록 상품을 admin에 등록: 자산 신규 등록(1회) + 해당하는 모든 유니버스에 추가.

    유니버스는 전체 목록 교체 POST — 기존 항목은 절대 수정·삭제하지 않고 추가만 한다.
    """
    _validate_keys(reqs)

    result = ApplyAllResult()

    async with PlantitAdminClient() as admin:
        isin_map = await admin.build_isin_map()
        members: dict[int, set[str]] = {}
        pending: dict[int, int] = {}
        for uid in sorted(_needed_universes(reqs)):
            members[uid] = await admin.get_universe_assets(uid)
            pending[uid] = 0

        lookup_cache: dict[str, str | None] = {}
        item_results: dict[str, ApplyItemResult] = {}   # raw_code → 결과 (기관 간 공유)
        resolved_ids: dict[str, str] = {}               # raw_code → asset_id

        for key, items in reqs:
            cfg = INSTITUTION_UNIVERSES[key]

            for item in items:
                ir = item_results.get(item.raw_code)
                if ir is None:
                    ir = ApplyItemResult(
                        raw_code=item.raw_code, fund_name=item.fund_name, ok=True
                    )
                    item_results[item.raw_code] = ir

                    aid = await _resolve_asset_id(
                        admin, item.raw_code, isin_map, lookup_cache
                    )
                    if not aid:
                        atype = "ETF" if item.product_type == "etf" else "FUND"
                        ok, res = await admin.register_asset(
                            item.fund_name, item.raw_code, atype
                        )
                        if not ok:
                            ir.ok = False
                            ir.detail = f"자산 등록 실패: {res}"
                            continue
                        aid = res
                        isin_map[item.raw_code] = aid
                        ir.asset_created = True
                    resolved_ids[item.raw_code] = aid

                if not ir.ok:
                    continue

                uid = cfg["etf" if item.product_type == "etf" else "fund"]
                aid = resolved_ids.get(item.raw_code)
                if uid is not None and aid and aid not in members[uid]:
                    members[uid].add(aid)
                    pending[uid] += 1
                    ir.universes_added.append(uid)

        # 변경된 유니버스만 전체 목록 교체
        for uid, count in pending.items():
            if count == 0:
                continue
            ok, detail = await admin.update_universe(uid, members[uid])
            result.universes.append(ApplyUniverseResult(
                universe_id=uid, universe_name=UNIVERSE_NAMES.get(uid, str(uid)),
                added=count, ok=ok, detail="" if ok else detail,
            ))
            if not ok:
                logger.error("Universe %d 업데이트 실패: %s", uid, detail)
                for ir in item_results.values():
                    if uid in ir.universes_added:
                        ir.universes_added.remove(uid)
                        ir.ok = False
                        ir.detail = (ir.detail + f" | 유니버스 {uid} 반영 실패").strip(" |")

        result.items = list(item_results.values())

    return result
