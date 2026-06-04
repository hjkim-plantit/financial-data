import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getLatestBankImports } from '../api/bankImports'
import type { InstitutionData, FundItem } from '../api/bankImports'
import clsx from 'clsx'

// ── 유틸 ──────────────────────────────────────────────────────

function formatDate(d: string | null): string {
  if (!d) return '—'
  const s = String(d).replace(/\D/g, '')
  if (s.length === 8) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
  return d
}

function RiskBadge({ grade }: { grade: number | null }) {
  if (grade === null) return <span className="text-slate-300 text-xs">—</span>
  const colors = ['', 'bg-red-100 text-red-700', 'bg-orange-100 text-orange-700',
    'bg-amber-100 text-amber-800', 'bg-yellow-100 text-yellow-800',
    'bg-green-100 text-green-700', 'bg-emerald-100 text-emerald-700']
  return (
    <span className={clsx('inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium', colors[grade] ?? 'bg-slate-100 text-slate-500')}>
      {grade}등급
    </span>
  )
}

// ── 기관 요약 카드 ─────────────────────────────────────────────

function SummaryCard({ inst, selected, onClick }: {
  inst: InstitutionData; selected: boolean; onClick: () => void
}) {
  const fundPct = inst.fund_total > 0 ? Math.round(inst.fund_matched / inst.fund_total * 100) : 0
  const etfPct  = inst.etf_total  > 0 ? Math.round(inst.etf_matched  / inst.etf_total  * 100) : 0

  return (
    <button onClick={onClick} className={clsx(
      'text-left p-4 rounded-xl border transition-all w-full',
      selected ? 'border-blue-400 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm',
    )}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="font-semibold text-slate-800">{inst.name}</p>
          <p className="text-xs text-slate-400 mt-0.5">수신일 {inst.email_date ?? '—'}</p>
          {inst.file_date && (
            <p className="text-xs text-slate-300 mt-0.5">데이터기준 {formatDate(inst.file_date)}</p>
          )}
        </div>
        {inst.error
          ? <span className="text-xs bg-red-50 text-red-500 px-2 py-0.5 rounded">오류</span>
          : <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded">총 {inst.total}건</span>
        }
      </div>

      {inst.error ? (
        <p className="text-xs text-red-400">{inst.error}</p>
      ) : (
        <div className="space-y-2">
          {/* 펀드 행 */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-slate-500 font-medium">펀드</span>
              <span className="text-slate-400">{inst.fund_matched}/{inst.fund_total} ({fundPct}%)</span>
            </div>
            <div className="flex gap-1 h-1.5 rounded-full overflow-hidden bg-slate-100">
              <div className="bg-blue-400 h-full transition-all" style={{ width: `${fundPct}%` }} />
            </div>
            <div className="flex gap-2 text-xs mt-1">
              <span className="text-green-600">매칭 {inst.fund_matched}</span>
              <span className="text-orange-500">미매칭 {inst.fund_total - inst.fund_matched}</span>
            </div>
          </div>
          {/* ETF 행 */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-indigo-600 font-medium">ETF</span>
              <span className="text-slate-400">{inst.etf_matched}/{inst.etf_total} ({etfPct}%)</span>
            </div>
            <div className="flex gap-1 h-1.5 rounded-full overflow-hidden bg-slate-100">
              <div className="bg-indigo-400 h-full transition-all" style={{ width: `${etfPct}%` }} />
            </div>
            <div className="flex gap-2 text-xs mt-1">
              <span className="text-green-600">매칭 {inst.etf_matched}</span>
              <span className="text-orange-500">미매칭 {inst.etf_total - inst.etf_matched}</span>
            </div>
          </div>
        </div>
      )}
    </button>
  )
}

// ── 필터 탭 ──────────────────────────────────────────────────

type FilterType = 'all' | 'fund' | 'etf'
type FilterMatch = 'all' | 'matched' | 'unmatched'

// ── 펀드 테이블 ───────────────────────────────────────────────

function FundTable({ inst }: { inst: InstitutionData }) {
  const [typeFilter, setTypeFilter] = useState<FilterType>('all')
  const [matchFilter, setMatchFilter] = useState<FilterMatch>('all')
  const [search, setSearch] = useState('')

  const filtered = inst.items.filter((item) => {
    if (typeFilter === 'fund' && item.product_type !== 'fund') return false
    if (typeFilter === 'etf'  && item.product_type !== 'etf')  return false
    if (matchFilter === 'matched'   && !item.matched)  return false
    if (matchFilter === 'unmatched' &&  item.matched)  return false
    if (search) {
      const q = search.toLowerCase()
      if (!item.fund_name.toLowerCase().includes(q) && !item.fund_code.toLowerCase().includes(q)) return false
    }
    return true
  })

  const TYPE_TABS: { value: FilterType; label: string }[] = [
    { value: 'all',  label: `전체 ${inst.total}` },
    { value: 'fund', label: `펀드 ${inst.fund_total}` },
    { value: 'etf',  label: `ETF ${inst.etf_total}` },
  ]
  const MATCH_TABS: { value: FilterMatch; label: string }[] = [
    { value: 'all',       label: '전체' },
    { value: 'matched',   label: '매칭' },
    { value: 'unmatched', label: '미매칭' },
  ]

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <input type="text" placeholder="펀드명/코드 검색..." value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-base flex-1 min-w-48" />
        <div className="flex gap-1">
          {TYPE_TABS.map((t) => (
            <button key={t.value} onClick={() => setTypeFilter(t.value)}
              className={clsx('px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                typeFilter === t.value ? 'bg-indigo-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {MATCH_TABS.map((t) => (
            <button key={t.value} onClick={() => setMatchFilter(t.value)}
              className={clsx('px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                matchFilter === t.value ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="table-base w-full" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '60px' }} />
              <col style={{ width: '140px' }} />
              <col style={{ width: 'auto' }} />
              <col style={{ width: '80px' }} />
              <col style={{ width: '90px' }} />
              <col style={{ width: '90px' }} />
              <col style={{ width: '64px' }} />
              <col style={{ width: '64px' }} />
            </colgroup>
            <thead>
              <tr>
                <th className="text-center">종류</th>
                <th>코드</th>
                <th>상품명</th>
                <th className="text-center">위험등급</th>
                <th className="text-center">취급시작</th>
                <th className="text-center">취급종료</th>
                <th className="text-center">판매</th>
                <th className="text-center">매칭</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={8} className="py-10 text-center text-slate-400">결과 없음</td></tr>
              ) : (
                filtered.map((item) => <FundRow key={item.fund_code} item={item} />)
              )}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2 border-t border-slate-100 text-xs text-slate-400">
          {filtered.length.toLocaleString()}건 표시
        </div>
      </div>
    </div>
  )
}

function FundRow({ item }: { item: FundItem }) {
  return (
    <tr className={clsx(!item.matched && 'bg-orange-50/40')}>
      <td className="text-center">
        <span className={clsx('inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium',
          item.product_type === 'etf' ? 'bg-indigo-50 text-indigo-600' : 'bg-slate-100 text-slate-500')}>
          {item.product_type === 'etf' ? 'ETF' : '펀드'}
        </span>
      </td>
      <td className="font-mono text-xs text-slate-500 whitespace-nowrap truncate">{item.fund_code}</td>
      <td className="text-sm text-slate-800 truncate" title={item.fund_name}>{item.fund_name}</td>
      <td className="text-center"><RiskBadge grade={item.risk_grade} /></td>
      <td className="text-center text-xs text-slate-500 tabular-nums">{formatDate(item.start_date)}</td>
      <td className="text-center text-xs text-slate-500 tabular-nums">
        {item.end_date === '99991231' ? '∞' : formatDate(item.end_date)}
      </td>
      <td className="text-center">
        <span className={clsx('text-xs px-1.5 py-0.5 rounded font-medium',
          item.available ? 'bg-green-50 text-green-600' : 'bg-slate-100 text-slate-400')}>
          {item.available ? 'Y' : 'N'}
        </span>
      </td>
      <td className="text-center">
        {item.matched
          ? <span className="text-green-500 text-sm">✓</span>
          : <span className="text-orange-400 text-xs">미매칭</span>}
      </td>
    </tr>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────

export default function BankImportsPage() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['bank-imports'],
    queryFn: getLatestBankImports,
    staleTime: 5 * 60 * 1000,
  })

  const selected = data?.find((d) => d.key === selectedKey) ?? data?.[0] ?? null

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">기관 데이터</h1>
          <p className="text-sm text-slate-500 mt-0.5">3개 기관 퇴직연금 상품목록 — 최신 이메일 기준</p>
        </div>
        <button onClick={() => refetch()} disabled={isFetching}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-50 transition-colors">
          <svg className={clsx('w-4 h-4', isFetching && 'animate-spin')} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {isFetching ? '불러오는 중...' : '새로고침'}
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-24">
          <div className="flex items-center gap-3 text-slate-500">
            <svg className="animate-spin w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm">Gmail에서 최신 데이터를 가져오는 중...</span>
          </div>
        </div>
      )}

      {isError && (
        <div className="card p-8 text-center text-slate-500">
          <p className="text-sm">데이터를 불러오지 못했습니다.</p>
        </div>
      )}

      {!isLoading && data && (
        <>
          <div className="grid grid-cols-3 gap-4">
            {data.map((inst) => (
              <SummaryCard
                key={inst.key} inst={inst}
                selected={(selectedKey ?? data[0]?.key) === inst.key}
                onClick={() => setSelectedKey(inst.key)}
              />
            ))}
          </div>

          {selected && !selected.error && (
            <div>
              <p className="text-sm font-semibold text-slate-700 mb-3">
                {selected.name} 상품 목록
                {selected.key === 'woori' && (
                  <span className="ml-2 text-xs font-normal text-amber-500">
                    ※ 펀드 KSD 코드(KRZ) — K55 코드 없음, 미매칭 유지
                  </span>
                )}
              </p>
              <FundTable inst={selected} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
