# 국내공모펀드 플랫폼 — 작업 현황

_최종 업데이트: 2026-06-08_

---

## 아키텍처

```
Vercel (프론트엔드)
  └─→ ngrok (shock-shifty-carefully.ngrok-free.dev)
        └─→ uvicorn :8000 (로컬 FastAPI, 내 PC에서 실행)
              └─→ fund_platform.db (SQLite 파일, 내 PC에 로컬 저장)

데이터 수집
  GitHub Actions → Redash (TRINO) → Morningstar / FnGuide → DB
```

> SQLite는 별도 서버 없이 PC에 파일(`fund_platform.db`)로 저장되는 로컬 DB.  
> uvicorn은 `--reload` 없이 실행 중. 코드 변경 시 수동 재시작 필요.

---

## 구현 완료 기능

### 펀드 조회 (`/`)
- 펀드명 검색, 자산군 필터, 종류(펀드/ETF), 상태, 위험등급 필터
- 위험등급 1~6등급 pill 버튼 (색상 코딩)
- 펀드명 한글 표시 (KOFIA 매핑 적용, 21,443건)
- 페이지네이션 (20건/페이지)

### 은행 이메일 임포트 (`/bank-imports`)
- 이메일 자동 파싱 → 기관 포트폴리오 diff 계산
- 경남은행 KRZ/K55 코드 혼용 처리
- 우리자산운용 제외, 예탁원 코드 기준, 판매조건 필터 (BNK 정책 적용)

### 업로드 검토 (`/imports`, `/imports/:id`)
- CSV/Excel 업로드 → 펀드코드 매칭 → 수동 분류 확인

---

## 데이터 동기화

| 워크플로우 | 주기 | 스크립트 | 비고 |
|---|---|---|---|
| `daily_sync.yml` | 매일 06:00 KST | `fetch_morningstar_funds.py` → `sync_etf.py` | Redash TRINO 조회 |
| `weekly_kofia.yml` | 매주 일 06:30 KST | `update_fund_names_kr.py` | KOFIA API → 한글명 업데이트 |

### 데이터 소스별 역할
| 소스 | 제공 데이터 | 한계 |
|---|---|---|
| Morningstar (Redash DS=7) | 펀드 기본정보, 수익률, `investmentrisklevelkr` | ETF 위험등급 ~271개만 커버 |
| FnGuide (Redash DS=23) | ETF 기본정보, 자산군 대/중분류 | 위험등급 컬럼 없음 |
| KOFIA API | 한글 펀드명 (`koreanCdtNm`) | — |

---

## ETF 자산군 분류 매핑

`idx_comm_id_l` (대분류) + `idx_comm_id_m` (중분류) → `internal_category_id`

```python
# 중분류 우선 매핑 (tuple key)
("원자재", "금속")   → 8  commodity_metal
("원자재", "에너지") → 9  commodity_energy
("원자재", "농산물") → 10 commodity_agri
("통화",   "미국달러"/일본엔/유로) → 6  alt_fx

# 대분류 fallback
주식→1, 채권→2, 부동산→4, 인프라→5, 통화→6, 원자재→11, 혼합자산/기타→99
```

---

## 위험등급 현황 및 한계

| 상품 | 소스 | 커버리지 | 비고 |
|---|---|---|---|
| 공모펀드 | Morningstar `investmentrisklevelkr` | 대부분 | 실제 등록 등급 |
| ETF | Morningstar `investmentrisklevelkr` | ~271개 | 나머지는 자산군 근사값 |
| ETF (근사값) | FnGuide 자산군 기반 추정 | 전체 | 주식→2, 채권→4, 부동산/인프라→3, 원자재→2 |

> **주의**: ETF 위험등급 데이터는 FnGuide·KRX 어디에도 없음. Morningstar 커버 외 종목은 근사값이므로 실제 KISC 등록 등급과 다를 수 있음. 이름 기반 분류는 사용하지 않음.

---

## 내부 분류 체계 (internal_categories)

```
주식 (1)
채권 (2)
대체투자 (3)
  ├─ 부동산 (4)
  ├─ 인프라 (5)
  ├─ 통화/외환 (6)
  └─ 원자재 (7)
       ├─ 금속 (8)
       ├─ 에너지 (9)
       ├─ 농산물 (10)
       └─ 기타 (11)
미분류 (99)
```

펀드는 leaf 노드(1,2,4,5,6,8,9,10,11)에만 배정. 미분류=99.

---

## 미해결 / 향후 과제

- [ ] ETF 위험등급 정확한 소스 확보 (업로드된 Excel 파일 기반 매핑 — 작업 미완료)
  - `ETF 필터 검색-20260608 (1).xlsx` 업로드됨, 아직 DB 반영 안 됨
- [ ] 수익률/기준가 데이터 UI 표시 (fund_nav, fund_returns 테이블 활용)
- [ ] 펀드 상세 페이지
- [ ] data_model.md의 "다음 단계" 중 펀드 비교 화면

---

## 활성 파일 구조

```
backend/
  app/
    routers/    bank_imports.py, categories.py, funds.py, imports.py, uploads.py
    models/     category.py, fund.py, import_data.py
    services/   bank_import_service.py, etf_sync.py, redash_client.py
  scripts/
    fetch_morningstar_funds.py   # Daily Step 1
    sync_etf.py                  # Daily Step 2
    update_fund_names_kr.py      # Weekly
    run_daily_sync.ps1           # 로컬 수동 실행
    run_weekly_kofia.ps1         # 로컬 수동 실행

frontend/src/pages/
  FundListPage.tsx
  BankImportsPage.tsx
  ImportReviewPage.tsx
  ImportDetailPage.tsx
```
