# 국내공모펀드 플랫폼 — 데이터 모델 v2

## 분류 체계 (핵심)

```
주식                                  ← leaf, 펀드 직접 배정
채권                                  ← leaf
대체투자                               ← 중간 노드 (검색 필터용)
  ├─ 부동산                           ← leaf
  ├─ 인프라                           ← leaf
  ├─ 통화/외환                        ← leaf
  └─ 원자재                           ← 중간 노드
       ├─ 금속                        ← leaf
       ├─ 에너지                      ← leaf
       ├─ 농산물                      ← leaf
       └─ 기타                        ← leaf
```

- **leaf 노드만** `funds.internal_category_id`에 배정 가능 (`is_leaf = TRUE` 제약)
- 중간 노드(대체투자, 원자재)는 UI 검색 필터에서 "하위 전체" 선택 시 사용
- KOFIA 공식 분류는 `funds.kofia_fund_type`에 별도 보관

### 내부 분류 코드표

| id | code | 화면 표시명 | 레벨 | leaf |
|---|---|---|---|---|
| 1 | equity | 주식 | 1 | ✓ |
| 2 | bond | 채권 | 1 | ✓ |
| 3 | alternative | 대체투자 | 1 | - |
| 4 | alt_realestate | 부동산 | 2 | ✓ |
| 5 | alt_infra | 인프라 | 2 | ✓ |
| 6 | alt_fx | 통화/외환 | 2 | ✓ |
| 7 | alt_commodity | 원자재 | 2 | - |
| 8 | commodity_metal | 금속 | 3 | ✓ |
| 9 | commodity_energy | 에너지 | 3 | ✓ |
| 10 | commodity_agri | 농산물 | 3 | ✓ |
| 11 | commodity_other | 기타 | 3 | ✓ |

---

## 전체 테이블 구조

| 테이블 | 설명 | 업데이트 주기 |
|---|---|---|
| `internal_categories` | 내부 분류 마스터 (계층형) | 변경 시 |
| `funds` | 펀드 기본정보 | 신규/변경 시 |
| `fund_nav` | 기준가·설정원본 이력 | 매일 |
| `fund_returns` | 기간별 수익률 | 매일 or 주간 |
| `fund_fees` | 보수·수수료 이력 | 변경 시 |
| `fund_risk_metrics` | 위험지표 | 월간 |
| `benchmarks` / `benchmark_index` | 벤치마크 지수 | 매일 |
| `fund_asset_allocation` | 자산배분 비중 | 월말 |
| `fund_holdings` | 주요 보유종목 | 월말 |
| `data_uploads` | 업로드 이력 | 업로드 시 |
| `users` | 사용자 계정 | 가입/변경 시 |

---

## 핵심 조회 쿼리

### 펀드 검색 — 특정 내부 분류 필터링

```sql
-- "대체투자-원자재" 하위 전체 조회 (중간 노드 포함 검색)
SELECT f.*
FROM funds f
JOIN internal_categories c ON f.internal_category_id = c.id
WHERE c.id = 7                    -- alt_commodity (원자재)
   OR c.parent_id = 7;            -- 원자재 직계 하위

-- "대체투자" 전체 조회 (재귀 없이 처리)
SELECT f.*
FROM funds f
JOIN internal_categories c  ON f.internal_category_id = c.id
LEFT JOIN internal_categories p ON c.parent_id = p.id
WHERE c.id = 3 OR c.parent_id = 3 OR p.parent_id = 3;
```

### 펀드 목록 + 최신 수익률 (검색 결과 카드용)

```sql
SELECT
    f.fund_code, f.fund_name, f.management_company, f.risk_grade,
    cat.full_path AS category,           -- '대체투자-원자재-금속'
    r.return_1m, r.return_3m, r.return_1y,
    n.nav, n.aum
FROM funds f
JOIN v_category_fullpath cat ON f.internal_category_id = cat.id
LEFT JOIN LATERAL (
    SELECT * FROM fund_returns
    WHERE fund_code = f.fund_code ORDER BY base_date DESC LIMIT 1
) r ON true
LEFT JOIN LATERAL (
    SELECT * FROM fund_nav
    WHERE fund_code = f.fund_code ORDER BY base_date DESC LIMIT 1
) n ON true
WHERE f.status = '운용중';
```

### 펀드 비교 (2~5개 나란히)

```sql
SELECT
    f.fund_code, f.fund_name,
    cat.full_path AS category,
    r.return_1m, r.return_3m, r.return_6m, r.return_1y, r.return_3y,
    m.sharpe_ratio, m.max_drawdown, m.std_deviation,
    fee.total_expense_ratio
FROM funds f
JOIN v_category_fullpath cat ON f.internal_category_id = cat.id
LEFT JOIN LATERAL (SELECT * FROM fund_returns WHERE fund_code = f.fund_code ORDER BY base_date DESC LIMIT 1) r ON true
LEFT JOIN LATERAL (SELECT * FROM fund_risk_metrics WHERE fund_code = f.fund_code AND period = '1y' ORDER BY base_date DESC LIMIT 1) m ON true
LEFT JOIN LATERAL (SELECT * FROM fund_fees WHERE fund_code = f.fund_code ORDER BY effective_date DESC LIMIT 1) fee ON true
WHERE f.fund_code = ANY(ARRAY['KR5223941C37','KR5223941C38']);
```

---

## 설계 결정 사항

### 분류 이중 관리
- `kofia_fund_type`: KOFIA 원천 데이터의 공식 분류 — 변경하지 않고 그대로 보관
- `internal_category_id`: 플랫폼 자체 분류 — UI 필터/검색의 기준

### is_leaf 제약
- 펀드는 반드시 leaf 노드에만 배정 → 중간 노드(대체투자, 원자재) 배정 불가
- 추후 분류 추가 시 `is_leaf` 값만 변경하면 확장 가능

### v_category_fullpath 뷰
- `full_path` 컬럼으로 UI에서 `'대체투자-원자재-금속'` 형태 바로 표시
- `category_l1 / l2 / l3` 컬럼으로 계층별 필터링 가능

---

## 다음 단계

- [ ] FastAPI 프로젝트 구조 생성
- [ ] SQLAlchemy ORM 모델 (`internal_categories`, `funds` 우선)
- [ ] 펀드 CRUD API + 분류 필터 API
- [ ] CSV/Excel 업로드 파서
- [ ] React 프론트엔드 (검색·비교 화면)
