import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getLatestBankImports } from '../api/bankImports'
import { getBankDiff } from '../api/bankDiff'
import type { InstitutionData, FundItem } from '../api/bankImports'
import type { InstitutionDiff, ProductChange } from '../api/bankDiff'
import clsx from 'clsx'

// ── 종목 마스터 CSV 생성 ──────────────────────────────────────

const RISK_LABEL: Record<number, string> = {
  1: '매우높은위험 (1등급)',
  2: '높은위험 (2등급)',
  3: '다소높은위험 (3등급)',
  4: '보통위험 (4등급)',
  5: '낮은위험 (5등급)',
  6: '매우낮은위험 (6등급)',
}

const CSV_HEADERS = [
  '종목명', 'Short Code/티커', 'ISIN', '자산분류', '자산군', '상장', '지역',
  '환 전략', '과세유형', '복제방식', '운용방식', '섹터', '위험 등급', '간이투자설명서',
  'Plantit 배당', 'Plantit 채권 액티브', 'Plantit 섹터&테마', '18차 유니버설',
  '우리자산x퀀팃 ROBO 글로벌 자산배분 EMP_P', '우리자산x퀀팃 ROBO 글로벌 자산배분 FOF_P',
  '퀀팃 SAIV-ROBO 글로벌 자산배분',
  'BNK부산_EMP', 'BNK부산_FOF', 'BNK경남_EMP', 'BNK경남_FOF',
]

function csvCell(s: string | null | undefined): string {
  const str = s ?? ''
  if (str.includes(',') || str.includes('"') || str.includes('\n')) return `"${str.replace(/"/g, '""')}"`
  return str
}

function buildMasterCsv(institutions: InstitutionData[]): string {
  const map = new Map<string, {
    name: string; code: string; productType: string
    riskGrade: number | null
    assetClass: string; region: string; sector: string
    woori: boolean; busan: boolean; gyeongnam: boolean
  }>()

  for (const inst of institutions) {
    for (const item of inst.items) {
      if (!item.available) continue
      const existing = map.get(item.fund_code)
      if (existing) {
        if (inst.key === 'woori')           existing.woori = true
        if (inst.key === 'bnk_busan')       existing.busan = true
        if (inst.key === 'bnk_gyeongnam')   existing.gyeongnam = true
      } else {
        map.set(item.fund_code, {
          name: item.fund_name, code: item.fund_code, productType: item.product_type,
          riskGrade: item.risk_grade,
          assetClass: item.asset_class ?? '',
          region:     item.region ?? '',
          sector:     item.sector ?? '',
          woori:      inst.key === 'woori',
          busan:      inst.key === 'bnk_busan',
          gyeongnam:  inst.key === 'bnk_gyeongnam',
        })
      }
    }
  }

  const b = (v: boolean) => v ? 'TRUE' : 'FALSE'

  const rows: string[][] = [CSV_HEADERS]
  for (const p of map.values()) {
    const isEtf   = p.productType === 'etf'
    const isBond  = p.assetClass === '채권'
    const code    = p.code
    const shortCode = (code.startsWith('KR7') || code.startsWith('KRZ')) ? code.slice(3, 9) : code
    const isin      = (code.startsWith('KR7') || code.startsWith('KRZ')) ? code : ''
    const riskLabel = p.riskGrade ? (RISK_LABEL[p.riskGrade] ?? '') : ''

    rows.push([
      p.name, shortCode, isin,
      isEtf ? 'ETF' : 'FUND',
      p.assetClass,   // 자산군 — DB+키워드 분류
      '국내',
      p.region,       // 지역 — DB+키워드 분류
      '', '', '', '', // 환 전략, 과세유형, 복제방식, 운용방식 — 생략
      p.sector,       // 섹터 — 키워드 분류
      riskLabel,
      '',             // 간이투자설명서
      b(isEtf),                 // Plantit 배당
      b(isEtf && isBond),       // Plantit 채권 액티브 — ETF 중 채권만
      b(isEtf),                 // Plantit 섹터&테마
      b(isEtf),                 // 18차 유니버설
      b(p.woori && isEtf),      // 우리자산x퀀팃 EMP_P
      b(p.woori && !isEtf),     // 우리자산x퀀팃 FOF_P
      b(isEtf),                 // 퀀팃 SAIV-ROBO
      b(p.busan && isEtf),      // BNK부산_EMP
      b(p.busan && !isEtf),     // BNK부산_FOF
      b(p.gyeongnam && isEtf),  // BNK경남_EMP
      b(p.gyeongnam && !isEtf), // BNK경남_FOF
    ])
  }

  return rows.map(r => r.map(csvCell).join(',')).join('\r\n')
}

function downloadMasterCsv(institutions: InstitutionData[]) {
  const csv  = buildMasterCsv(institutions)
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url
  a.download = `종목마스터_${today}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ── 공통 유틸 ──────────────────────────────────────────────────

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
    <span className={clsx('inline-flex px-1.5 py-0.5 rounded text-xs font-medium', colors[grade] ?? 'bg-slate-100 text-slate-500')}>
      {grade}등급
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span className={clsx('inline-flex px-1.5 py-0.5 rounded text-xs font-medium',
      type === 'etf' ? 'bg-indigo-50 text-indigo-600' : 'bg-slate-100 text-slate-500')}>
      {type === 'etf' ? 'ETF' : '펀드'}
    </span>
  )
}

function ChangeBadge({ type }: { type: string }) {
  const s = { added: 'bg-green-50 text-green-700', removed: 'bg-red-50 text-red-600', changed: 'bg-amber-50 text-amber-700' }
  const l = { added: '신규', removed: '삭제', changed: '변경' }
  return (
    <span className={clsx('inline-flex px-1.5 py-0.5 rounded text-xs font-medium border',
      s[type as keyof typeof s] ?? 'bg-slate-100 text-slate-500')}>
      {l[type as keyof typeof l] ?? type}
    </span>
  )
}

// ── 기관 카드 ──────────────────────────────────────────────────

function SummaryCard({ instKey, name, selected, onClick, latest, diff }: {
  instKey: string; name: string; selected: boolean; onClick: () => void
  latest?: InstitutionData; diff?: InstitutionDiff
}) {
  const fundPct = latest && latest.fund_total > 0 ? Math.round(latest.fund_matched / latest.fund_total * 100) : 0
  const etfPct  = latest && latest.etf_total  > 0 ? Math.round(latest.etf_matched  / latest.etf_total  * 100) : 0
  const totalChanges = diff?.total_changes ?? 0

  return (
    <button onClick={onClick} className={clsx(
      'text-left p-4 rounded-xl border transition-all w-full',
      selected ? 'border-blue-400 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300',
    )}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="font-semibold text-slate-800">{name}</p>
          <p className="text-xs text-slate-400 mt-0.5">수신일 {latest?.email_date ?? '—'}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded">
            총 {latest?.total ?? 0}건
          </span>
          {totalChanges > 0 && (
            <span className="text-xs bg-orange-50 text-orange-600 px-2 py-0.5 rounded font-medium">
              변경 {totalChanges}건
            </span>
          )}
        </div>
      </div>

      {latest?.error ? (
        <p className="text-xs text-red-400">{latest.error}</p>
      ) : (
        <div className="space-y-2">
          {[{ label: '펀드', matched: latest?.fund_matched ?? 0, total: latest?.fund_total ?? 0, pct: fundPct, color: 'bg-blue-400' },
            { label: 'ETF',  matched: latest?.etf_matched  ?? 0, total: latest?.etf_total  ?? 0, pct: etfPct,  color: 'bg-indigo-400', labelClass: 'text-indigo-600' }
          ].map(row => (
            <div key={row.label}>
              <div className="flex justify-between text-xs mb-0.5">
                <span className={clsx('font-medium', row.labelClass ?? 'text-slate-500')}>{row.label}</span>
                <span className="text-slate-400">{row.matched}/{row.total} ({row.pct}%)</span>
              </div>
              <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div className={clsx('h-full', row.color)} style={{ width: `${row.pct}%` }} />
              </div>
            </div>
          ))}
          {diff && (
            <div className="flex gap-3 pt-1 text-xs border-t border-slate-100 mt-1">
              <span className="text-green-600">+신규 {diff.added.length}</span>
              <span className="text-red-500">-삭제 {diff.removed.length}</span>
              <span className="text-amber-600">~변경 {diff.changed.length}</span>
            </div>
          )}
        </div>
      )}
    </button>
  )
}

// ── 상품 목록 테이블 ──────────────────────────────────────────

type MatchFilter = 'all' | 'matched' | 'unmatched'
type TypeFilter  = 'all' | 'fund' | 'etf'

function ProductTable({ inst }: { inst: InstitutionData }) {
  const [typeF, setTypeF]  = useState<TypeFilter>('all')
  const [matchF, setMatchF] = useState<MatchFilter>('all')
  const [search, setSearch] = useState('')

  const rows = inst.items.filter(item => {
    if (typeF  === 'fund' && item.product_type !== 'fund') return false
    if (typeF  === 'etf'  && item.product_type !== 'etf')  return false
    if (matchF === 'matched'   && !item.matched) return false
    if (matchF === 'unmatched' && item.matched)  return false
    if (search) {
      const q = search.toLowerCase()
      return item.fund_name.toLowerCase().includes(q) || item.fund_code.toLowerCase().includes(q)
    }
    return true
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <input type="text" placeholder="펀드명/코드 검색..." value={search}
          onChange={e => setSearch(e.target.value)} className="input-base flex-1 min-w-48" />
        <div className="flex gap-1">
          {(['all','fund','etf'] as TypeFilter[]).map(v => (
            <button key={v} onClick={() => setTypeF(v)}
              className={clsx('px-3 py-1.5 rounded-full text-xs font-medium',
                typeF === v ? 'bg-indigo-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>
              {v === 'all' ? `전체 ${inst.total}` : v === 'fund' ? `펀드 ${inst.fund_total}` : `ETF ${inst.etf_total}`}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(['all','matched','unmatched'] as MatchFilter[]).map(v => (
            <button key={v} onClick={() => setMatchF(v)}
              className={clsx('px-3 py-1.5 rounded-full text-xs font-medium',
                matchF === v ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>
              {v === 'all' ? '전체' : v === 'matched' ? '매칭' : '미매칭'}
            </button>
          ))}
        </div>
      </div>
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="table-base w-full" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '55px' }} /><col style={{ width: '130px' }} />
              <col style={{ width: 'auto' }} /><col style={{ width: '80px' }} />
              <col style={{ width: '90px' }} /><col style={{ width: '90px' }} />
              <col style={{ width: '60px' }} /><col style={{ width: '60px' }} />
            </colgroup>
            <thead><tr>
              <th className="text-center">종류</th><th>코드</th><th>상품명</th>
              <th className="text-center">위험등급</th><th className="text-center">취급시작</th>
              <th className="text-center">취급종료</th><th className="text-center">판매</th><th className="text-center">매칭</th>
            </tr></thead>
            <tbody>
              {rows.length === 0
                ? <tr><td colSpan={8} className="py-10 text-center text-slate-400">결과 없음</td></tr>
                : rows.map((item: FundItem) => (
                  <tr key={item.fund_code} className={clsx(!item.matched && 'bg-orange-50/40')}>
                    <td className="text-center"><TypeBadge type={item.product_type} /></td>
                    <td className="font-mono text-xs text-slate-500 truncate">{item.fund_code}</td>
                    <td className="text-sm truncate" title={item.fund_name}>{item.fund_name}</td>
                    <td className="text-center"><RiskBadge grade={item.risk_grade} /></td>
                    <td className="text-center text-xs text-slate-500">{formatDate(item.start_date)}</td>
                    <td className="text-center text-xs text-slate-500">{item.end_date === '99991231' ? '∞' : formatDate(item.end_date)}</td>
                    <td className="text-center">
                      <span className={clsx('text-xs px-1 py-0.5 rounded font-medium', item.available ? 'bg-green-50 text-green-600' : 'bg-slate-100 text-slate-400')}>
                        {item.available ? 'Y' : 'N'}
                      </span>
                    </td>
                    <td className="text-center">
                      {item.matched ? <span className="text-green-500 text-sm">✓</span> : <span className="text-orange-400 text-xs">미매칭</span>}
                    </td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2 border-t border-slate-100 text-xs text-slate-400">{rows.length.toLocaleString()}건 표시</div>
      </div>
    </div>
  )
}

// ── 변경사항 테이블 ───────────────────────────────────────────

type ChangeFilter = 'all' | 'added' | 'removed' | 'changed'

function DiffTable({ diff }: { diff: InstitutionDiff }) {
  const [filter, setFilter] = useState<ChangeFilter>('all')
  const [search, setSearch] = useState('')

  const all = [...diff.added, ...diff.removed, ...diff.changed]
  const rows = all.filter(item => {
    if (filter !== 'all' && item.change_type !== filter) return false
    if (search) {
      const q = search.toLowerCase()
      return item.fund_name.toLowerCase().includes(q) || item.fund_code.toLowerCase().includes(q)
    }
    return true
  })

  if (all.length === 0) {
    return (
      <div className="card p-10 text-center text-slate-400">
        <p className="text-sm">전일 대비 변경사항이 없습니다.</p>
        {diff.yesterday_date && <p className="text-xs mt-1 text-slate-300">{diff.yesterday_date} → {diff.today_date}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <input type="text" placeholder="펀드명/코드 검색..." value={search}
          onChange={e => setSearch(e.target.value)} className="input-base flex-1 min-w-48" />
        <div className="flex gap-1">
          {(['all','added','removed','changed'] as ChangeFilter[]).map(v => {
            const cnt = v === 'all' ? all.length : v === 'added' ? diff.added.length : v === 'removed' ? diff.removed.length : diff.changed.length
            return (
              <button key={v} onClick={() => setFilter(v)}
                className={clsx('px-3 py-1.5 rounded-full text-xs font-medium',
                  filter === v ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>
                {v === 'all' ? '전체' : v === 'added' ? '신규' : v === 'removed' ? '삭제' : '변경'} {cnt > 0 && cnt}
              </button>
            )
          })}
        </div>
      </div>
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="table-base w-full" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '55px' }} /><col style={{ width: '55px' }} />
              <col style={{ width: '130px' }} /><col style={{ width: 'auto' }} /><col style={{ width: '200px' }} />
            </colgroup>
            <thead><tr>
              <th className="text-center">구분</th><th className="text-center">종류</th>
              <th>코드</th><th>상품명</th><th>변경 내용</th>
            </tr></thead>
            <tbody>
              {rows.length === 0
                ? <tr><td colSpan={5} className="py-10 text-center text-slate-400">결과 없음</td></tr>
                : rows.map((item: ProductChange) => (
                  <tr key={`${item.change_type}-${item.fund_code}`}
                    className={clsx(
                      item.change_type === 'added'   && 'bg-green-50/40',
                      item.change_type === 'removed' && 'bg-red-50/40',
                      item.change_type === 'changed' && 'bg-amber-50/30',
                    )}>
                    <td className="text-center"><ChangeBadge type={item.change_type} /></td>
                    <td className="text-center"><TypeBadge type={item.product_type} /></td>
                    <td className="font-mono text-xs text-slate-500 truncate">{item.fund_code}</td>
                    <td className="text-sm truncate" title={item.fund_name}>{item.fund_name}</td>
                    <td className="text-xs text-slate-500">
                      {item.changes.map(c => (
                        <div key={c.field} className="flex items-center gap-1 flex-wrap">
                          <span className="font-medium text-slate-600">{c.label}</span>
                          <span className="line-through text-red-400">{c.old || '—'}</span>
                          <span>→</span>
                          <span className="text-green-600 font-medium">{c.new || '—'}</span>
                        </div>
                      ))}
                    </td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2 border-t border-slate-100 text-xs text-slate-400">{rows.length}건 표시</div>
      </div>
    </div>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────

type ViewTab = 'products' | 'diff'

type DlState = 'idle' | 'working' | 'done'

export default function BankImportsPage() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [viewTab, setViewTab] = useState<ViewTab>('products')
  const [dlState, setDlState] = useState<DlState>('idle')

  const latestQ = useQuery({ queryKey: ['bank-imports'], queryFn: getLatestBankImports, staleTime: 5 * 60 * 1000 })
  const diffQ   = useQuery({ queryKey: ['bank-diff'],    queryFn: getBankDiff,          staleTime: 5 * 60 * 1000 })

  const isLoading = latestQ.isLoading || diffQ.isLoading
  const isFetching = latestQ.isFetching || diffQ.isFetching

  const institutions = latestQ.data ?? []
  const diffs        = diffQ.data ?? []

  const firstKey = institutions[0]?.key ?? null
  const activeKey = selectedKey ?? firstKey

  const selectedLatest = institutions.find(d => d.key === activeKey)
  const selectedDiff   = diffs.find(d => d.key === activeKey)

  function refetch() { latestQ.refetch(); diffQ.refetch() }

  function handleDownload() {
    setDlState('working')
    // setTimeout 0으로 렌더 먼저 반영 후 무거운 작업 실행
    setTimeout(() => {
      try {
        downloadMasterCsv(institutions)
        setDlState('done')
      } catch {
        setDlState('idle')
      }
      setTimeout(() => setDlState('idle'), 2000)
    }, 0)
  }

  const dlDisabled = institutions.length === 0 || isLoading || dlState === 'working'

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">기관 데이터</h1>
          <p className="text-sm text-slate-500 mt-0.5">3개 기관 퇴직연금 상품목록 — 최신 이메일 기준</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownload}
            disabled={dlDisabled}
            className={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-white transition-colors disabled:cursor-not-allowed',
              dlState === 'done'    ? 'bg-green-600'                        :
              dlState === 'working' ? 'bg-blue-400 opacity-80'              :
                                     'bg-blue-600 hover:bg-blue-700',
              dlDisabled && dlState !== 'working' && 'opacity-40',
            )}
          >
            {dlState === 'working' ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                생성 중...
              </>
            ) : dlState === 'done' ? (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                다운로드 완료
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                종목 마스터 CSV
              </>
            )}
          </button>
          <button onClick={refetch} disabled={isFetching}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-50">
            <svg className={clsx('w-4 h-4', isFetching && 'animate-spin')} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {isFetching ? '불러오는 중...' : '새로고침'}
          </button>
        </div>
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

      {!isLoading && institutions.length > 0 && (
        <>
          {/* 기관 카드 */}
          <div className="grid grid-cols-3 gap-4">
            {institutions.map(inst => (
              <SummaryCard key={inst.key}
                instKey={inst.key} name={inst.name}
                selected={activeKey === inst.key}
                onClick={() => setSelectedKey(inst.key)}
                latest={inst}
                diff={diffs.find(d => d.key === inst.key)}
              />
            ))}
          </div>

          {/* 뷰 탭 */}
          <div className="flex items-center gap-2">
            {([['products','상품 목록'], ['diff','변경사항']] as [ViewTab, string][]).map(([v, label]) => (
              <button key={v} onClick={() => setViewTab(v)}
                className={clsx('px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                  viewTab === v ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-100')}>
                {label}
                {v === 'diff' && selectedDiff && selectedDiff.total_changes > 0 && (
                  <span className="ml-1.5 px-1.5 py-0.5 bg-orange-400 text-white text-xs rounded-full">
                    {selectedDiff.total_changes}
                  </span>
                )}
              </button>
            ))}
            {viewTab === 'diff' && selectedDiff && (
              <span className="text-xs text-slate-400 ml-2">
                {selectedDiff.yesterday_date} → {selectedDiff.today_date}
              </span>
            )}
          </div>

          {/* 상세 테이블 */}
          {viewTab === 'products' && selectedLatest && (
            <div>
              {selectedLatest.key === 'woori' && (
                <p className="text-xs text-amber-500 mb-3">※ 우리은행 펀드는 KSD(KRZ) 코드 사용 — K55 매핑 없어 미매칭</p>
              )}
              <ProductTable inst={selectedLatest} />
            </div>
          )}
          {viewTab === 'diff' && selectedDiff && (
            <DiffTable diff={selectedDiff} />
          )}
        </>
      )}
    </div>
  )
}
