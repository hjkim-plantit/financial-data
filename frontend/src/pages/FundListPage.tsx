import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFunds } from '../api/funds'
import CategoryFilter from '../components/CategoryFilter'
import type { FundListItem } from '../types'
import clsx from 'clsx'

// ── 포맷 헬퍼 ─────────────────────────────────────────────────

function formatDate(value: string | null): string {
  if (!value) return '—'
  return value.slice(0, 10)
}

function RiskBadge({ grade }: { grade: number | null }) {
  if (grade === null) return <span className="text-slate-300">—</span>
  const colors = ['', 'bg-red-100 text-red-700', 'bg-orange-100 text-orange-700',
    'bg-amber-100 text-amber-800', 'bg-yellow-100 text-yellow-800',
    'bg-green-100 text-green-700', 'bg-emerald-100 text-emerald-700']
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded text-xs font-medium', colors[grade] ?? 'bg-slate-100 text-slate-500')}>
      {grade}등급
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === '운용중') return null
  const style = status === '판매중단'
    ? 'bg-slate-100 text-slate-500'
    : status === '설정취소'
    ? 'bg-red-50 text-red-500'
    : 'bg-yellow-50 text-yellow-700'
  return (
    <span className={clsx('inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ml-1.5', style)}>
      {status}
    </span>
  )
}

// ── 필터 탭 정의 ──────────────────────────────────────────────

const STATUS_TABS = [
  { value: '운용중', label: '운용중' },
  { value: '판매중단', label: '판매중단' },
  { value: 'all', label: '전체' },
]

const PRODUCT_TABS = [
  { value: 'all', label: '전체' },
  { value: 'fund', label: '펀드' },
  { value: 'etf', label: 'ETF' },
]

const RISK_TABS = [
  { value: null,  label: '전체', active: 'bg-slate-700 text-white' },
  { value: 1, label: '1등급', active: 'bg-red-500 text-white' },
  { value: 2, label: '2등급', active: 'bg-orange-500 text-white' },
  { value: 3, label: '3등급', active: 'bg-amber-500 text-white' },
  { value: 4, label: '4등급', active: 'bg-yellow-500 text-white' },
  { value: 5, label: '5등급', active: 'bg-green-500 text-white' },
  { value: 6, label: '6등급', active: 'bg-emerald-500 text-white' },
]

// ── 메인 컴포넌트 ──────────────────────────────────────────────

export default function FundListPage() {
  const [search, setSearch] = useState('')
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [status, setStatus] = useState('운용중')
  const [productType, setProductType] = useState('all')
  const [riskGrade, setRiskGrade] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const pageSize = 20

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['funds', { search, categoryId, status, productType, riskGrade, page, pageSize }],
    queryFn: () => getFunds({
      search: search || undefined,
      category_id: categoryId ?? undefined,
      status,
      product_type: productType,
      risk_grade: riskGrade ?? undefined,
      page,
      page_size: pageSize,
    }),
    placeholderData: (prev) => prev,
  })

  const handleCategoryChange = useCallback((id: number | null) => {
    setCategoryId(id); setPage(1)
  }, [])

  const handleSearch = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value); setPage(1)
  }, [])

  const handleStatus = useCallback((val: string) => {
    setStatus(val); setPage(1)
  }, [])

  const handleProductType = useCallback((val: string) => {
    setProductType(val); setPage(1)
  }, [])

  const handleRiskGrade = useCallback((val: number | null) => {
    setRiskGrade(val); setPage(1)
  }, [])

  const funds: FundListItem[] = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">펀드 조회</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {total > 0 ? `총 ${total.toLocaleString()}개 펀드` : '펀드 목록'}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="card p-4 space-y-3">
        {/* 검색 */}
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="펀드명으로 검색..."
            value={search}
            onChange={handleSearch}
            className="input-base w-full pl-9"
          />
        </div>

        {/* 자산군 필터 */}
        <div>
          <p className="text-xs text-slate-500 mb-2 font-medium">자산군 분류</p>
          <CategoryFilter selectedId={categoryId} onChange={handleCategoryChange} />
        </div>

        {/* 종류 + 상태 + 위험등급 탭 */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-1">
            <p className="text-xs text-slate-500 font-medium mr-2">종류</p>
            {PRODUCT_TABS.map((tab) => (
              <button
                key={tab.value}
                onClick={() => handleProductType(tab.value)}
                className={clsx(
                  'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                  productType === tab.value
                    ? 'bg-indigo-500 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <p className="text-xs text-slate-500 font-medium mr-2">상태</p>
            {STATUS_TABS.map((tab) => (
              <button
                key={tab.value}
                onClick={() => handleStatus(tab.value)}
                className={clsx(
                  'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                  status === tab.value
                    ? 'bg-blue-500 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <p className="text-xs text-slate-500 font-medium mr-2">위험등급</p>
            {RISK_TABS.map((tab) => (
              <button
                key={tab.value ?? 'all'}
                onClick={() => handleRiskGrade(tab.value)}
                className={clsx(
                  'px-3 py-1 rounded-full text-xs font-medium transition-colors',
                  riskGrade === tab.value
                    ? tab.active
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <div className="flex items-center gap-3 text-slate-500">
              <svg className="animate-spin w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-sm">데이터 불러오는 중...</span>
            </div>
          </div>
        )}

        {isError && (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-3">
                <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-sm font-medium text-slate-700">데이터를 불러오지 못했습니다</p>
              <p className="text-xs text-slate-400 mt-1">{(error as Error)?.message}</p>
            </div>
          </div>
        )}

        {!isLoading && !isError && (
          <>
            <div className="overflow-x-auto">
              <table className="table-base w-full" style={{ tableLayout: 'fixed' }}>
                <colgroup>
                  <col style={{ width: '120px' }} />  {/* 펀드코드 */}
                  <col style={{ width: 'auto' }} />    {/* 펀드명 */}
                  <col style={{ width: '160px' }} />   {/* 자산군 */}
                  <col style={{ width: '90px' }} />    {/* 위험등급 */}
                  <col style={{ width: '100px' }} />   {/* 생성일자 */}
                  <col style={{ width: '180px' }} />   {/* 운용사 */}
                </colgroup>
                <thead>
                  <tr>
                    <th>펀드코드</th>
                    <th>펀드명</th>
                    <th>자산군</th>
                    <th className="text-center">위험등급</th>
                    <th className="text-center">생성일자</th>
                    <th>운용사</th>
                  </tr>
                </thead>
                <tbody>
                  {funds.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-12 text-center text-slate-400">
                        검색 결과가 없습니다
                      </td>
                    </tr>
                  ) : (
                    funds.map((fund) => (
                      <tr key={fund.fund_code}>
                        <td className="font-mono text-xs text-slate-500 whitespace-nowrap">
                          {fund.fund_code}
                        </td>
                        <td>
                          <div className="flex items-center min-w-0 gap-1.5">
                            <p className="font-medium text-slate-800 truncate" title={fund.fund_name}>
                              {fund.fund_name}
                            </p>
                            {fund.product_type === 'etf' && (
                              <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 font-medium">ETF</span>
                            )}
                            <StatusBadge status={fund.status} />
                          </div>
                        </td>
                        <td>
                          {fund.category_full_path ? (
                            <span className="text-xs text-slate-500 bg-slate-50 px-2 py-0.5 rounded whitespace-nowrap">
                              {fund.category_full_path}
                            </span>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                        <td className="text-center">
                          <RiskBadge grade={fund.risk_grade} />
                        </td>
                        <td className="text-center text-xs text-slate-500 tabular-nums whitespace-nowrap">
                          {formatDate(fund.inception_date)}
                        </td>
                        <td className="text-slate-500 text-sm truncate" title={fund.management_company}>
                          {fund.management_company}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
                <p className="text-xs text-slate-500">
                  {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, total)}개 / 총 {total.toLocaleString()}개
                </p>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-2.5 py-1.5 rounded text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    이전
                  </button>
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const pageNum = Math.max(1, Math.min(totalPages - 4, page - 2)) + i
                    return (
                      <button
                        key={pageNum}
                        onClick={() => setPage(pageNum)}
                        className={clsx(
                          'w-8 h-8 rounded text-xs font-medium',
                          page === pageNum
                            ? 'bg-blue-500 text-white'
                            : 'text-slate-600 hover:bg-slate-100',
                        )}
                      >
                        {pageNum}
                      </button>
                    )
                  })}
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="px-2.5 py-1.5 rounded text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    다음
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
