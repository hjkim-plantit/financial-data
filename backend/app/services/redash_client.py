"""Redash API를 통해 쿼리를 실행하고 결과를 반환하는 동기 클라이언트."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class RedashQueryError(Exception):
    pass


class RedashClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        poll_interval: float = 3.0,
        max_wait: float = 300.0,
    ):
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Key {api_key}"}
        self._poll_interval = poll_interval
        self._max_wait = max_wait

    def run_query(self, data_source_id: int, sql: str, max_age: int = 0) -> list[dict]:
        """쿼리를 실행하고 결과 row 목록을 반환한다.

        Args:
            data_source_id: Redash 데이터소스 ID
            sql: 실행할 SQL
            max_age: 캐시 유효 시간(초). 0이면 항상 새로 실행.

        Returns:
            결과 row dict 목록.
        """
        with httpx.Client(headers=self._headers, timeout=30) as client:
            result_id = self._submit(client, data_source_id, sql, max_age)
            rows = self._fetch_rows(client, result_id)
        logger.info("Redash 쿼리 완료: %d행", len(rows))
        return rows

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _submit(
        self, client: httpx.Client, data_source_id: int, sql: str, max_age: int
    ) -> int:
        """쿼리를 제출하고 query_result_id를 반환한다."""
        resp = client.post(
            f"{self._base}/api/query_results",
            json={"data_source_id": data_source_id, "query": sql, "max_age": max_age},
        )
        resp.raise_for_status()
        body = resp.json()

        # 즉시 결과 반환된 경우
        if "query_result" in body:
            return body["query_result"]["id"]

        job_id: str = body["job"]["id"]
        return self._poll_job(client, job_id)

    def _poll_job(self, client: httpx.Client, job_id: str) -> int:
        """job이 완료될 때까지 폴링하고 query_result_id를 반환한다."""
        deadline = time.monotonic() + self._max_wait
        while time.monotonic() < deadline:
            resp = client.get(f"{self._base}/api/jobs/{job_id}")
            resp.raise_for_status()
            job = resp.json()["job"]

            status = job["status"]
            if status == 3:  # 완료
                return job["result"]
            if status == 4:  # 오류
                raise RedashQueryError(f"쿼리 실행 오류: {job.get('error')}")

            logger.debug("Redash job 대기 중 (status=%d)...", status)
            time.sleep(self._poll_interval)

        raise RedashQueryError(f"쿼리 타임아웃: {self._max_wait}초 초과 (job={job_id})")

    def _fetch_rows(self, client: httpx.Client, result_id: int) -> list[dict]:
        """query_result_id로 결과 rows를 가져온다."""
        resp = client.get(
            f"{self._base}/api/query_results/{result_id}",
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["query_result"]["data"]["rows"]
