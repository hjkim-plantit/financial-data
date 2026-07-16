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


# ── 비교/적용 오케스트레이션 ──────────────────────────────────

@dataclass
class SyncItem:
    raw_code: str      # KRZ/KR7 예탁원 코드 = admin ISIN
    fund_name: str
    product_type: str  # 'fund' | 'etf'


@dataclass
class CompareItemResult:
    raw_code: str
    fund_name: str
    product_type: str
    status: str                 # asset_missing | universe_missing | registered
    universe_id: int | None = None


@dataclass
class CompareResult:
    key: str
    universe_note: str | None
    admin_asset_total: int
    universe_counts: dict[int, int] = field(default_factory=dict)
    registered: int = 0
    missing: list[CompareItemResult] = field(default_factory=list)


async def compare_institution(key: str, items: list[SyncItem]) -> CompareResult:
    """이메일 상품 목록 vs admin 등록 상태 비교 (읽기 전용)."""
    cfg = INSTITUTION_UNIVERSES.get(key)
    if cfg is None:
        raise PlantitAdminError(f"알 수 없는 기관 key: {key}")

    note = (
        "우리은행은 선별 유니버스(U7/U8) 운영 — 자산 등록 여부만 확인하며 유니버스는 변경하지 않습니다."
        if key == "woori" else None
    )

    async with PlantitAdminClient() as admin:
        isin_map = await admin.build_isin_map()
        members: dict[int, set[str]] = {}
        for uid in cfg.values():
            if uid is not None:
                members[uid] = await admin.get_universe_assets(uid)

        result = CompareResult(
            key=key,
            universe_note=note,
            admin_asset_total=len(isin_map),
            universe_counts={uid: len(m) for uid, m in members.items()},
        )

        for item in items:
            aid = isin_map.get(item.raw_code)
            if not aid:
                aid = await admin.get_asset_id(item.raw_code)
            uid = cfg["etf" if item.product_type == "etf" else "fund"]
            if not aid:
                result.missing.append(CompareItemResult(
                    raw_code=item.raw_code, fund_name=item.fund_name,
                    product_type=item.product_type, status="asset_missing",
                    universe_id=uid,
                ))
            elif uid is not None and aid not in members[uid]:
                result.missing.append(CompareItemResult(
                    raw_code=item.raw_code, fund_name=item.fund_name,
                    product_type=item.product_type, status="universe_missing",
                    universe_id=uid,
                ))
            else:
                result.registered += 1

        return result


@dataclass
class ApplyItemResult:
    raw_code: str
    fund_name: str
    ok: bool
    action: str    # asset_created | universe_added | asset_created+universe_added | already_registered | failed
    detail: str = ""


@dataclass
class ApplyUniverseResult:
    universe_id: int
    universe_name: str
    added: int
    ok: bool
    detail: str = ""


@dataclass
class ApplyResult:
    key: str
    items: list[ApplyItemResult] = field(default_factory=list)
    universes: list[ApplyUniverseResult] = field(default_factory=list)


async def apply_institution(key: str, items: list[SyncItem]) -> ApplyResult:
    """미등록 상품을 admin에 등록: 자산 신규 등록 + 유니버스 추가(전체목록 교체 POST).

    기존 자산/유니버스 항목은 절대 수정·삭제하지 않고 추가만 한다.
    """
    cfg = INSTITUTION_UNIVERSES.get(key)
    if cfg is None:
        raise PlantitAdminError(f"알 수 없는 기관 key: {key}")

    result = ApplyResult(key=key)

    async with PlantitAdminClient() as admin:
        isin_map = await admin.build_isin_map()
        members: dict[int, set[str]] = {}
        pending: dict[int, int] = {}  # universe_id → 추가 건수
        for uid in cfg.values():
            if uid is not None:
                members[uid] = await admin.get_universe_assets(uid)
                pending[uid] = 0

        for item in items:
            atype = "ETF" if item.product_type == "etf" else "FUND"
            actions: list[str] = []

            aid = isin_map.get(item.raw_code)
            if not aid:
                aid = await admin.get_asset_id(item.raw_code)
            if not aid:
                ok, res = await admin.register_asset(item.fund_name, item.raw_code, atype)
                if not ok:
                    result.items.append(ApplyItemResult(
                        raw_code=item.raw_code, fund_name=item.fund_name,
                        ok=False, action="failed", detail=f"자산 등록 실패: {res}",
                    ))
                    continue
                aid = res
                isin_map[item.raw_code] = aid
                actions.append("asset_created")

            uid = cfg["etf" if item.product_type == "etf" else "fund"]
            if uid is not None and aid not in members[uid]:
                members[uid].add(aid)
                pending[uid] += 1
                actions.append("universe_added")

            result.items.append(ApplyItemResult(
                raw_code=item.raw_code, fund_name=item.fund_name,
                ok=True, action="+".join(actions) or "already_registered",
            ))

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
                # 유니버스 반영 실패 → 해당 유니버스에 추가하려던 항목 상태 보정
                for it in result.items:
                    if it.ok and "universe_added" in it.action:
                        target_uid = cfg["etf" if it.raw_code.startswith("KR7") else "fund"]
                        if target_uid == uid:
                            it.ok = False
                            it.detail = f"유니버스 {uid} 반영 실패: {detail}"

    return result
