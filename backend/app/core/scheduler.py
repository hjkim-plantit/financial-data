"""APScheduler 설정 모듈.

등록된 스케줄 작업:
  - 매일 06:00 KST  : Morningstar 펀드 데이터 동기화 (판매중단 감지 포함)
  - 매주 일요일 06:30 : KOFIA API 한글명 업데이트
  - 매일 07:00 KST  : Gmail 첨부파일 임포트
"""

import logging
from datetime import date
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
scheduler = AsyncIOScheduler(timezone=_KST)


# ── 작업 1: Morningstar 펀드 동기화 ──────────────────────────

async def _run_morningstar_sync() -> None:
    from app.core.config import settings
    from app.database import AsyncSessionLocal
    from app.services.morningstar_sync import sync_morningstar_funds
    from app.services.redash_client import RedashClient

    logger.info("스케줄러: Morningstar 펀드 동기화 시작")
    try:
        redash = RedashClient(base_url=settings.redash_url, api_key=settings.redash_api_key)
        async with AsyncSessionLocal() as db:
            stats = await sync_morningstar_funds(db, redash)
        logger.info(
            "스케줄러: Morningstar 동기화 완료. upserted=%d delisted=%d no_category=%d",
            stats.get("upserted", 0),
            stats.get("delisted", 0),
            stats.get("no_category", 0),
        )
    except Exception as exc:
        logger.error("스케줄러: Morningstar 동기화 실패. error=%s", exc, exc_info=True)


# ── 작업 2: KOFIA 한글명 업데이트 ────────────────────────────

async def _run_kofia_name_update() -> None:
    from app.core.config import settings
    from app.database import AsyncSessionLocal
    from app.services.kofia_client import FscFundClient
    from sqlalchemy import text

    logger.info("스케줄러: KOFIA 한글명 업데이트 시작")
    try:
        async with FscFundClient(api_key=settings.fsc_api_key) as client:
            records = await client.fetch_all_funds()

        kofia_map = {r.aso_std_cd: r.fnd_nm for r in records if r.aso_std_cd and r.fnd_nm}

        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT fund_code FROM funds"))
            db_codes = [row[0] for row in result.fetchall()]

            matched = [(code, kofia_map[code]) for code in db_codes if code in kofia_map]

            BATCH = 500
            updated = 0
            for i in range(0, len(matched), BATCH):
                batch = matched[i:i + BATCH]
                cases = " ".join(f"WHEN :c{j} THEN :n{j}" for j in range(len(batch)))
                params = {}
                codes_in = []
                for j, (code, name) in enumerate(batch):
                    params[f"c{j}"] = code
                    params[f"n{j}"] = name
                    codes_in.append(f":c{j}")
                await db.execute(
                    text(f"UPDATE funds SET fund_name = CASE fund_code {cases} END WHERE fund_code IN ({', '.join(codes_in)})"),
                    params,
                )
                updated += len(batch)
            await db.commit()

        logger.info("스케줄러: KOFIA 한글명 업데이트 완료. updated=%d / total_db=%d", updated, len(db_codes))
    except Exception as exc:
        logger.error("스케줄러: KOFIA 한글명 업데이트 실패. error=%s", exc, exc_info=True)


# ── 작업 3: Gmail 임포트 ──────────────────────────────────────

async def _run_import_trigger() -> None:
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=120.0) as client:
            response = await client.post("/imports/trigger")
            response.raise_for_status()
            logger.info("스케줄러: 이메일 임포트 완료. status=%s", response.status_code)
    except Exception as exc:
        logger.error("스케줄러: 이메일 임포트 실패. error=%s", exc)


# ── 스케줄러 초기화 ───────────────────────────────────────────

def setup_scheduler() -> AsyncIOScheduler:
    scheduler.add_job(
        _run_morningstar_sync,
        trigger=CronTrigger(hour=6, minute=0, timezone=_KST),
        id="daily_morningstar_sync",
        name="매일 06:00 KST Morningstar 펀드 동기화",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        _run_kofia_name_update,
        trigger=CronTrigger(day_of_week="sun", hour=6, minute=30, timezone=_KST),
        id="weekly_kofia_name_update",
        name="매주 일요일 06:30 KST KOFIA 한글명 업데이트",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        _run_import_trigger,
        trigger=CronTrigger(hour=7, minute=0, timezone=_KST),
        id="daily_email_import",
        name="매일 07:00 KST Gmail 첨부파일 임포트",
        replace_existing=True,
        misfire_grace_time=300,
    )

    logger.info(
        "스케줄러 등록 완료: "
        "Morningstar동기화(매일 06:00) / KOFIA한글명(매주일 06:30) / Gmail임포트(매일 07:00)"
    )
    return scheduler
