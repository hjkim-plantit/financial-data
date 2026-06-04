# 국내공모펀드 플랫폼 — 작업 현황

## 목표
국내 공모펀드 데이터를 수집·분류하여 검색·비교할 수 있는 내부 플랫폼 구축.

---

## 완료된 것

### 백엔드 (FastAPI + SQLite → PostgreSQL 예정)
| 파일 | 내용 |
|------|------|
| `app/models/fund.py` | Fund ORM 모델 |
| `app/models/category.py` | InternalCategory 계층형 모델 |
| `app/models/import_data.py` | EmailImport / ImportItem 모델 |
| `app/routers/funds.py` | 펀드 CRUD, 미분류 관리, 일괄 분류 API |
| `app/routers/categories.py` | 분류 트리 API |
| `app/routers/imports.py` | Gmail 첨부파일 임포트 API |
| `app/routers/uploads.py` | 파일 업로드 API |
| `app/services/kofia_client.py` | 금융위원회 공공데이터포털 API 클라이언트 |
| `app/services/kofia_sync.py` | KOFIA → DB upsert 서비스 |
| `app/services/matching_service.py` | 펀드 코드 매칭 서비스 |
| `app/services/gmail_service.py` | Gmail OAuth 첨부파일 수집 |
| `scripts/fetch_kofia_funds.py` | KOFIA 동기화 CLI |

### 분류 체계 (확정)
```
주식 (id=1)
채권 (id=2)
대체투자 (id=3, 중간노드)
  ├─ 부동산 (id=4)
  ├─ 인프라 (id=5)
  ├─ 통화/외환 (id=6)
  └─ 원자재 (id=7, 중간노드)
       ├─ 금속 (id=8)
       ├─ 에너지 (id=9)
       ├─ 농산물 (id=10)
       └─ 기타 (id=11)
```

### 1.metabase/morningstar_fund_classification.sql
Redash에서 실행 가능한 Morningstar 분류 쿼리. 테이블: `iceberg.morningstar_fund.operation`  
컬럼: `krcode`(펀드코드), `fundname`, `investmentrisklevelkr`(위험등급 1~5), `globalcategoryname`, `broadcategorygroup`, `categoryname`

---

## 막힌 것 — 데이터 로딩

### 문제
KOFIA 공공데이터포털 API(`getStandardCodeInfo`)로 수집 시도했으나 실패.

**원인:**
1. API가 `inception_date`, `risk_grade`, `management_company`를 제공하지 않음 → DB NOT NULL 제약 충돌
2. `fnd_tp = "재간접"` 유형 펀드는 내부 분류 매핑 불가 (→ `unmapped_funds_preview.csv` 생성됨)

---

## 다음 작업 — Trino 직접 연결

### 방식
KOFIA API 대신 **Trino → `iceberg.morningstar_fund.operation`** 에 직접 쿼리해서 펀드 기본 데이터 + 분류 + 위험등급을 한 번에 수집.  
(Redash가 이 데이터소스에 연결되어 있음: `data_source_id=25, TRINO_iceberg_morningstar_fund`)

### 구현 계획
1. `requirements.txt`에 `trino` 패키지 추가
2. `app/services/trino_client.py` 생성 — Trino 연결 + `morningstar_fund.operation` 쿼리
3. `app/services/morningstar_sync.py` 생성 — Morningstar 데이터 → funds 테이블 upsert
4. `scripts/fetch_morningstar_funds.py` CLI 스크립트 생성
5. `app/core/config.py`에 Trino 연결 설정 추가

### 필요한 정보 (미확인)
- [ ] Trino 서버 host / port
- [ ] Trino 인증 방식 (user/password or token)
- [ ] `.env`에 추가할 환경변수명 확정

### 참고 쿼리 (`1.metabase/morningstar_fund_classification.sql`)
```sql
SELECT
    krcode,
    fundname,
    investmentrisklevelkr AS risk_level,
    -- asset_class, region, sector CASE 로직 포함
    ...
FROM iceberg.morningstar_fund.operation
WHERE pit = (SELECT MAX(pit) FROM iceberg.morningstar_fund.operation)
```

---

## 환경
- DB: SQLite (`backend/fund_platform.db`) — 개발용, 운영은 PostgreSQL 예정
- 쿼리 도구: Redash (`redash.quantit.io`)
- 데이터 소스: Trino + Iceberg (`iceberg.morningstar_fund`)
