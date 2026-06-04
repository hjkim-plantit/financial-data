-- ============================================================
-- 국내공모펀드 플랫폼 - PostgreSQL 데이터 모델 v2
-- ============================================================


-- ─────────────────────────────────────────
-- 0. 내부 분류 체계 (마스터 데이터)
--
--    계층 구조:
--      level 1 │ 주식 / 채권 / 대체투자
--      level 2 │ (대체투자 하위) 부동산 / 인프라 / 통화외환 / 원자재
--      level 3 │ (원자재 하위) 금속 / 에너지 / 농산물 / 기타
--
--    펀드는 반드시 leaf 노드(말단 분류)에만 배정
-- ─────────────────────────────────────────
CREATE TABLE internal_categories (
    id          SMALLSERIAL PRIMARY KEY,
    code        VARCHAR(40) UNIQUE NOT NULL,   -- 영문 식별코드 (API/필터링용)
    name        VARCHAR(50) NOT NULL,           -- 화면 표시명
    level       SMALLINT NOT NULL CHECK (level IN (1,2,3)),
    parent_id   SMALLINT REFERENCES internal_categories(id),
    is_leaf     BOOLEAN NOT NULL DEFAULT FALSE, -- TRUE인 노드만 펀드에 배정 가능
    sort_order  SMALLINT DEFAULT 0
);

-- 초기 분류 데이터
INSERT INTO internal_categories (id, code, name, level, parent_id, is_leaf, sort_order) VALUES
-- ── level 1
(1,  'equity',          '주식',         1, NULL, TRUE,  1),
(2,  'bond',            '채권',         1, NULL, TRUE,  2),
(3,  'alternative',     '대체투자',     1, NULL, FALSE, 3),   -- 중간 노드

-- ── level 2 (대체투자 하위)
(4,  'alt_realestate',  '부동산',       2, 3,    TRUE,  1),
(5,  'alt_infra',       '인프라',       2, 3,    TRUE,  2),
(6,  'alt_fx',          '통화/외환',    2, 3,    TRUE,  3),
(7,  'alt_commodity',   '원자재',       2, 3,    FALSE, 4),   -- 중간 노드

-- ── level 3 (원자재 하위)
(8,  'commodity_metal', '금속',         3, 7,    TRUE,  1),
(9,  'commodity_energy','에너지',       3, 7,    TRUE,  2),
(10, 'commodity_agri',  '농산물',       3, 7,    TRUE,  3),
(11, 'commodity_other', '기타',         3, 7,    TRUE,  4);


-- ─────────────────────────────────────────
-- 1. 펀드 기본정보
-- ─────────────────────────────────────────
CREATE TABLE funds (
    fund_code           VARCHAR(12) PRIMARY KEY,   -- KOFIA 표준 펀드코드 (예: KR5223941C37)
    fund_name           VARCHAR(200) NOT NULL,      -- 펀드명
    fund_name_short     VARCHAR(100),               -- 약칭

    -- KOFIA 공식 분류 (원천 데이터 그대로 보관)
    kofia_fund_type     VARCHAR(50),                -- 예: 주식형, 채권형, MMF, 특별자산, 부동산 등

    -- 내부 분류 (is_leaf=TRUE 인 노드만 배정)
    internal_category_id SMALLINT NOT NULL
        REFERENCES internal_categories(id),

    -- 투자 지역
    investment_region   VARCHAR(20) DEFAULT '국내'
        CHECK (investment_region IN ('국내','해외','글로벌')),

    -- 위험등급 (금융투자협회 기준 1=매우높음, 6=매우낮음)
    risk_grade          SMALLINT CHECK (risk_grade BETWEEN 1 AND 6),

    -- 운용/판매 주체
    management_company  VARCHAR(100) NOT NULL,      -- 운용사
    trustee_company     VARCHAR(100),               -- 수탁사

    -- 설정 정보
    inception_date      DATE NOT NULL,              -- 설정일
    maturity_date       DATE,                       -- 만기일 (개방형은 NULL)
    base_currency       CHAR(3) DEFAULT 'KRW',

    -- 상태
    status              VARCHAR(20) DEFAULT '운용중'
        CHECK (status IN ('운용중','판매중단','설정취소','만기상환')),

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_funds_internal_cat ON funds(internal_category_id);
CREATE INDEX idx_funds_company      ON funds(management_company);
CREATE INDEX idx_funds_status       ON funds(status);


-- ─────────────────────────────────────────
-- 2. 기준가 이력 (매일 업데이트)
-- ─────────────────────────────────────────
CREATE TABLE fund_nav (
    id                BIGSERIAL PRIMARY KEY,
    fund_code         VARCHAR(12) NOT NULL REFERENCES funds(fund_code) ON DELETE CASCADE,
    base_date         DATE NOT NULL,
    nav               NUMERIC(12, 2) NOT NULL,  -- 기준가 (원)
    aum               BIGINT,                   -- 설정원본 (백만원)
    units_outstanding BIGINT,                   -- 수익증권 잔액좌수

    UNIQUE(fund_code, base_date)
);

CREATE INDEX idx_nav_fund_date ON fund_nav(fund_code, base_date DESC);


-- ─────────────────────────────────────────
-- 3. 수익률 (정기 산출)
-- ─────────────────────────────────────────
CREATE TABLE fund_returns (
    id                     BIGSERIAL PRIMARY KEY,
    fund_code              VARCHAR(12) NOT NULL REFERENCES funds(fund_code) ON DELETE CASCADE,
    base_date              DATE NOT NULL,

    -- 누적수익률 (%)
    return_1m              NUMERIC(8, 4),
    return_3m              NUMERIC(8, 4),
    return_6m              NUMERIC(8, 4),
    return_ytd             NUMERIC(8, 4),
    return_1y              NUMERIC(8, 4),
    return_3y              NUMERIC(8, 4),
    return_5y              NUMERIC(8, 4),
    return_since_inception NUMERIC(8, 4),

    -- 연환산수익률 (%)
    annualized_1y          NUMERIC(8, 4),
    annualized_3y          NUMERIC(8, 4),
    annualized_5y          NUMERIC(8, 4),

    UNIQUE(fund_code, base_date)
);

CREATE INDEX idx_returns_fund_date ON fund_returns(fund_code, base_date DESC);


-- ─────────────────────────────────────────
-- 4. 보수 및 비용 (변경 이력 보관)
-- ─────────────────────────────────────────
CREATE TABLE fund_fees (
    id                   BIGSERIAL PRIMARY KEY,
    fund_code            VARCHAR(12) NOT NULL REFERENCES funds(fund_code) ON DELETE CASCADE,
    effective_date       DATE NOT NULL,

    -- 보수 (연율, %)
    total_expense_ratio  NUMERIC(6, 4),
    management_fee       NUMERIC(6, 4),
    sales_fee            NUMERIC(6, 4),
    trustee_fee          NUMERIC(6, 4),
    admin_fee            NUMERIC(6, 4),

    -- 수수료 (%)
    sales_load_front     NUMERIC(6, 4) DEFAULT 0,
    redemption_fee       NUMERIC(6, 4) DEFAULT 0,
    redemption_fee_period SMALLINT,               -- 환매수수료 적용기간 (일)

    UNIQUE(fund_code, effective_date)
);


-- ─────────────────────────────────────────
-- 5. 위험지표 (월간 산출)
-- ─────────────────────────────────────────
CREATE TABLE fund_risk_metrics (
    id                BIGSERIAL PRIMARY KEY,
    fund_code         VARCHAR(12) NOT NULL REFERENCES funds(fund_code) ON DELETE CASCADE,
    base_date         DATE NOT NULL,
    period            VARCHAR(10) NOT NULL CHECK (period IN ('1y','3y','5y')),

    std_deviation     NUMERIC(8, 4),  -- 표준편차 (연환산, %)
    sharpe_ratio      NUMERIC(8, 4),
    information_ratio NUMERIC(8, 4),
    tracking_error    NUMERIC(8, 4),
    max_drawdown      NUMERIC(8, 4),
    beta              NUMERIC(8, 4),
    alpha             NUMERIC(8, 4),

    UNIQUE(fund_code, base_date, period)
);


-- ─────────────────────────────────────────
-- 6. 벤치마크
-- ─────────────────────────────────────────
CREATE TABLE benchmarks (
    benchmark_code  VARCHAR(20) PRIMARY KEY,
    benchmark_name  VARCHAR(100) NOT NULL,
    description     VARCHAR(200)
);

CREATE TABLE fund_benchmarks (
    fund_code       VARCHAR(12) REFERENCES funds(fund_code) ON DELETE CASCADE,
    benchmark_code  VARCHAR(20) REFERENCES benchmarks(benchmark_code),
    is_primary      BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (fund_code, benchmark_code)
);

CREATE TABLE benchmark_index (
    id             BIGSERIAL PRIMARY KEY,
    benchmark_code VARCHAR(20) NOT NULL REFERENCES benchmarks(benchmark_code),
    base_date      DATE NOT NULL,
    index_value    NUMERIC(12, 4) NOT NULL,
    daily_return   NUMERIC(8, 4),

    UNIQUE(benchmark_code, base_date)
);


-- ─────────────────────────────────────────
-- 7. 포트폴리오 (월말 공시)
-- ─────────────────────────────────────────
CREATE TABLE fund_asset_allocation (
    id          BIGSERIAL PRIMARY KEY,
    fund_code   VARCHAR(12) NOT NULL REFERENCES funds(fund_code) ON DELETE CASCADE,
    base_date   DATE NOT NULL,

    equity_pct  NUMERIC(6, 2) DEFAULT 0,
    bond_pct    NUMERIC(6, 2) DEFAULT 0,
    cash_pct    NUMERIC(6, 2) DEFAULT 0,
    other_pct   NUMERIC(6, 2) DEFAULT 0,

    UNIQUE(fund_code, base_date)
);

CREATE TABLE fund_holdings (
    id            BIGSERIAL PRIMARY KEY,
    fund_code     VARCHAR(12) NOT NULL REFERENCES funds(fund_code) ON DELETE CASCADE,
    base_date     DATE NOT NULL,
    rank          SMALLINT NOT NULL,
    security_code VARCHAR(20),
    security_name VARCHAR(100) NOT NULL,
    weight_pct    NUMERIC(6, 2),
    asset_type    VARCHAR(20),

    UNIQUE(fund_code, base_date, rank)
);


-- ─────────────────────────────────────────
-- 8. 데이터 업로드 이력
-- ─────────────────────────────────────────
CREATE TABLE data_uploads (
    id           BIGSERIAL PRIMARY KEY,
    file_name    VARCHAR(255) NOT NULL,
    data_type    VARCHAR(30) NOT NULL
        CHECK (data_type IN ('nav','returns','fees','risk','portfolio','fund_master')),
    base_date    DATE,
    row_count    INTEGER,
    error_count  INTEGER DEFAULT 0,
    status       VARCHAR(20) DEFAULT '처리중'
        CHECK (status IN ('처리중','완료','오류')),
    error_log    TEXT,
    uploaded_by  VARCHAR(100),
    uploaded_at  TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────
-- 9. 사용자
-- ─────────────────────────────────────────
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    email           VARCHAR(200) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    name            VARCHAR(100),
    role            VARCHAR(20) DEFAULT 'viewer'
        CHECK (role IN ('admin','manager','viewer')),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────
-- 유용한 뷰: 내부 분류 전체 경로 (UI 표시용)
-- ─────────────────────────────────────────
CREATE VIEW v_category_fullpath AS
SELECT
    c.id,
    c.code,
    c.is_leaf,
    c.level,
    CASE c.level
        WHEN 1 THEN c.name
        WHEN 2 THEN p1.name || '-' || c.name
        WHEN 3 THEN p2.name || '-' || p1.name || '-' || c.name
    END AS full_path,              -- 예: '대체투자-원자재-금속'
    CASE c.level
        WHEN 1 THEN c.name
        WHEN 2 THEN p1.name
        WHEN 3 THEN p2.name
    END AS category_l1,
    CASE c.level
        WHEN 2 THEN c.name
        WHEN 3 THEN p1.name
        ELSE NULL
    END AS category_l2,
    CASE c.level
        WHEN 3 THEN c.name
        ELSE NULL
    END AS category_l3,
    c.sort_order
FROM internal_categories c
LEFT JOIN internal_categories p1 ON c.parent_id = p1.id
LEFT JOIN internal_categories p2 ON p1.parent_id = p2.id;
