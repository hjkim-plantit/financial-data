import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getLatestBankImports, saveWooriMapping } from '../api/bankImports'
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

const LEVERAGE_INVERSE_RE = /레버리지|인버스|2X|2배|3X|3배|곱버전|200%|300%|short|bear/i

function buildMasterCsv(institutions: InstitutionData[]): string {
  const map = new Map<string, {
    name: string; fundCode: string; productType: string
    riskGrade: number | null
    assetClass: string; region: string; sector: string
    woori: boolean; busan: boolean; gyeongnam: boolean
  }>()

  for (const inst of institutions) {
    for (const item of inst.items) {
      if (!item.available) continue
      if (item.product_type === 'etf' && LEVERAGE_INVERSE_RE.test(item.fund_name)) continue
      const existing = map.get(item.fund_code)
      if (existing) {
        if (inst.key === 'woori')           existing.woori = true
        if (inst.key === 'bnk_busan')       existing.busan = true
        if (inst.key === 'bnk_gyeongnam')   existing.gyeongnam = true
      } else {
        map.set(item.fund_code, {
          name: item.fund_name, fundCode: item.fund_code,
          productType: item.product_type,
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
    const shortCode = /^(KR[75Z]|K[R5]5)/.test(p.fundCode) ? p.fundCode.slice(3, 9) : p.fundCode
    const riskLabel = p.riskGrade ? (RISK_LABEL[p.riskGrade] ?? '') : ''

    rows.push([
      p.name, shortCode, p.fundCode,
      isEtf ? 'ETF' : 'FUND',
      p.assetClass,
      '국내',
      p.region,
      '', '', '', '',
      p.sector,
      riskLabel,
      '',
      b(isEtf),
      b(isEtf && isBond),
      b(isEtf),
      b(isEtf),
      b(p.woori && isEtf),
      b(p.woori && !isEtf),
      b(isEtf),
      b(p.busan && isEtf),
      b(p.busan && !isEtf),
      b(p.gyeongnam && isEtf),
      b(p.gyeongnam && !isEtf),
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
  if (grade === null) return <span className="text-neutral-300 text-xs">—</span>
  const colors = [
    '',
    'bg-red-50 text-red-600',
    'bg-orange-50 text-orange-600',
    'bg-amber-50 text-amber-700',
    'bg-yellow-50 text-yellow-700',
    'bg-green-50 text-green-700',
    'bg-emerald-50 text-emerald-700',
  ]
  return (
    <span className={clsx('inline-flex px-2 py-0.5 rounded-full text-xs font-medium', colors[grade] ?? 'bg-neutral-100 text-neutral-500')}>
      {grade}등급
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span className={clsx(
      'inline-flex px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap',
      type === 'etf' ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-500'
    )}>
      {type === 'etf' ? 'ETF' : '펀드'}
    </span>
  )
}

function ChangeBadge({ type }: { type: string }) {
  const s = {
    added:   'bg-green-50 text-green-700',
    removed: 'bg-red-50 text-red-600',
    changed: 'bg-amber-50 text-amber-700',
  }
  const l = { added: '신규', removed: '삭제', changed: '변경' }
  return (
    <span className={clsx(
      'inline-flex px-2 py-0.5 rounded-full text-xs font-medium',
      s[type as keyof typeof s] ?? 'bg-neutral-100 text-neutral-500'
    )}>
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
      'text-left p-5 rounded-xl border transition-all w-full',
      selected
        ? 'border-black bg-neutral-50'
        : 'border-neutral-200 bg-white hover:border-neutral-400',
    )}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="font-semibold text-neutral-900 text-sm">{name}</p>
          <p className="text-xs text-neutral-400 mt-0.5">수신일 {latest?.email_date ?? '—'}</p>
          {diff && (diff.yesterday_date || diff.today_date) && (
            <p className="text-xs text-neutral-300 mt-0.5">
              비교 {diff.yesterday_date ?? '—'} → {diff.today_date ?? '—'}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-xs bg-neutral-100 text-neutral-500 px-2.5 py-0.5 rounded-full">
            총 {latest?.total ?? 0}건
          </span>
          {totalChanges > 0 && (
            <span className="text-xs bg-black text-white px-2.5 py-0.5 rounded-full font-medium">
              변경 {totalChanges}건
            </span>
          )}
        </div>
      </div>

      {latest?.error ? (
        <p className="text-xs text-red-400">{latest.error}</p>
      ) : (
        <div className="space-y-2.5">
          {[
            { label: '펀드', matched: latest?.fund_matched ?? 0, total: latest?.fund_total ?? 0, pct: fundPct, color: 'bg-neutral-800' },
            { label: 'ETF',  matched: latest?.etf_matched  ?? 0, total: latest?.etf_total  ?? 0, pct: etfPct,  color: 'bg-neutral-500' },
          ].map(row => (
            <div key={row.label}>
              <div className="flex justify-between text-xs mb-1">
                <span className="font-medium text-neutral-500">{row.label}</span>
                <span className="text-neutral-400">{row.matched}/{row.total} ({row.pct}%)</span>
              </div>
              <div className="h-1 rounded-full bg-neutral-100 overflow-hidden">
                <div className={clsx('h-full transition-all', row.color)} style={{ width: `${row.pct}%` }} />
              </div>
            </div>
          ))}
          {diff && (
            <div className="flex gap-3 pt-2 text-xs border-t border-neutral-100">
              <span className="text-green-600">+신규 {diff.added.length}</span>
              <span className="text-red-500">−삭제 {diff.removed.length}</span>
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
type RiskFilter  = 'all' | 1 | 2 | 3 | 4 | 5 | 6

function ProductTable({ inst }: { inst: InstitutionData }) {
  const [typeF, setTypeF]  = useState<TypeFilter>('all')
  const [matchF, setMatchF] = useState<MatchFilter>('all')
  const [riskF, setRiskF] = useState<RiskFilter>('all')
  const [search, setSearch] = useState('')
  const [editingKrz, setEditingKrz] = useState<string | null>(null)
  const [inputVal, setInputVal] = useState('')

  const queryClient = useQueryClient()
  const mappingMutation = useMutation({
    mutationFn: ({ krz, k55 }: { krz: string; k55: string }) => saveWooriMapping(krz, k55),
    onSuccess: () => {
      setEditingKrz(null)
      setInputVal('')
      queryClient.invalidateQueries({ queryKey: ['bank-imports'] })
    },
  })

  function handleSave(krz: string) {
    const k55 = inputVal.trim()
    if (!k55) return
    mappingMutation.mutate({ krz, k55 })
  }

  const rows = inst.items.filter(item => {
    if (typeF  === 'fund' && item.product_type !== 'fund') return false
    if (typeF  === 'etf'  && item.product_type !== 'etf')  return false
    if (matchF === 'matched'   && !item.matched) return false
    if (matchF === 'unmatched' && item.matched)  return false
    if (riskF !== 'all' && item.risk_grade !== riskF) return false
    if (search) {
      const q = search.toLowerCase()
      return item.fund_name.toLowerCase().includes(q) || item.fund_code.toLowerCase().includes(q)
    }
    return true
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <input
          type="text"
          placeholder="펀드명/코드 검색..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-48 h-9 px-4 rounded-full border border-neutral-200 bg-neutral-50 text-sm text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:border-black focus:bg-white transition-colors"
        />
        <div className="flex gap-1">
          {(['all','fund','etf'] as TypeFilter[]).map(v => (
            <button key={v} onClick={() => setTypeF(v)}
              className={clsx(
                'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                typeF === v ? 'bg-black text-white' : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
              )}>
              {v === 'all' ? `전체 ${inst.total}` : v === 'fund' ? `펀드 ${inst.fund_total}` : `ETF ${inst.etf_total}`}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(['all','matched','unmatched'] as MatchFilter[]).map(v => (
            <button key={v} onClick={() => setMatchF(v)}
              className={clsx(
                'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                matchF === v ? 'bg-black text-white' : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
              )}>
              {v === 'all' ? '전체' : v === 'matched' ? '매칭' : '미매칭'}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(['all', 1, 2, 3, 4, 5, 6] as RiskFilter[]).map(v => (
            <button key={v} onClick={() => setRiskF(v)}
              className={clsx(
                'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                riskF === v ? 'bg-black text-white' : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
              )}>
              {v === 'all' ? '전체등급' : `${v}등급`}
            </button>
          ))}
        </div>
      </div>

      <div className="border border-neutral-200 rounded-xl overflow-hidden bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '72px' }} />
              <col style={{ width: '145px' }} />
              <col style={{ width: '145px' }} />
              <col style={{ width: 'auto' }} />
              <col style={{ width: '72px' }} />
              <col style={{ width: '80px' }} />
              <col style={{ width: '56px' }} />
            </colgroup>
            <thead>
              <tr className="border-b border-neutral-100 bg-neutral-50">
                <th className="text-center py-2.5 px-3 text-xs font-medium text-neutral-500">종류</th>
                <th className="py-2.5 px-3 text-xs font-medium text-neutral-500 text-left">KRZ코드</th>
                <th className="py-2.5 px-3 text-xs font-medium text-neutral-500 text-left">K55코드</th>
                <th className="py-2.5 px-3 text-xs font-medium text-neutral-500 text-left">상품명</th>
                <th className="text-center py-2.5 px-3 text-xs font-medium text-neutral-500">위험등급</th>
                <th className="text-center py-2.5 px-3 text-xs font-medium text-neutral-500">취급시작</th>
                <th className="text-center py-2.5 px-3 text-xs font-medium text-neutral-500">매칭</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-50">
              {rows.length === 0
                ? <tr><td colSpan={7} className="py-12 text-center text-neutral-400 text-sm">결과 없음</td></tr>
                : rows.map((item: FundItem) => {
                  const hasK55 = item.fund_code !== item.raw_code
                  return (
                    <tr key={item.raw_code} className={clsx(
                      'hover:bg-neutral-50 transition-colors',
                      !item.matched && 'bg-amber-50/30'
                    )}>
                      <td className="text-center py-2.5 px-3"><TypeBadge type={item.product_type} /></td>
                      <td className="font-mono text-xs text-neutral-400 truncate py-2.5 px-3">{item.raw_code}</td>
                      <td className="font-mono text-xs py-2.5 px-3">
                        {hasK55 ? (
                          <span className="text-neutral-700 truncate block">{item.fund_code}</span>
                        ) : inst.key === 'woori' && item.product_type === 'fund' ? (
                          editingKrz === item.raw_code ? (
                            <div className="flex items-center gap-1">
                              <input
                                autoFocus
                                type="text"
                                value={inputVal}
                                onChange={e => setInputVal(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter') handleSave(item.raw_code); if (e.key === 'Escape') setEditingKrz(null) }}
                                placeholder="K55..."
                                className="w-24 border border-neutral-300 rounded-full px-2 py-0.5 text-xs focus:outline-none focus:border-black"
                              />
                              <button
                                onClick={() => handleSave(item.raw_code)}
                                disabled={mappingMutation.isPending}
                                className="text-neutral-900 text-xs font-medium disabled:opacity-40 hover:underline"
                              >저장</button>
                              <button onClick={() => setEditingKrz(null)} className="text-neutral-300 hover:text-neutral-500 text-xs">✕</button>
                            </div>
                          ) : (
                            <button
                              onClick={() => { setEditingKrz(item.raw_code); setInputVal('') }}
                              className="flex items-center gap-1 text-neutral-300 hover:text-neutral-700 group"
                            >
                              <span>—</span>
                              <span className="opacity-0 group-hover:opacity-100 text-xs">✎</span>
                            </button>
                          )
                        ) : (
                          <span className="text-neutral-300">—</span>
                        )}
                      </td>
                      <td className="text-sm text-neutral-700 truncate py-2.5 px-3" title={item.fund_name}>{item.fund_name}</td>
                      <td className="text-center py-2.5 px-3"><RiskBadge grade={item.risk_grade} /></td>
                      <td className="text-center text-xs text-neutral-400 py-2.5 px-3">{formatDate(item.start_date)}</td>
                      <td className="text-center py-2.5 px-3">
                        {item.matched
                          ? <span className="text-neutral-900 text-sm font-medium">✓</span>
                          : hasK55
                            ? <span className="text-amber-500 text-xs">DB없음</span>
                            : <span className="text-neutral-400 text-xs">미매칭</span>}
                      </td>
                    </tr>
                  )
                })
              }
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2.5 border-t border-neutral-100 text-xs text-neutral-400">{rows.length.toLocaleString()}건 표시</div>
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
      <div className="border border-neutral-200 rounded-xl p-12 text-center bg-white">
        <p className="text-sm text-neutral-400">전일 대비 변경사항이 없습니다.</p>
        {diff.yesterday_date && (
          <p className="text-xs mt-1 text-neutral-300">{diff.yesterday_date} → {diff.today_date}</p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <input
          type="text"
          placeholder="펀드명/코드 검색..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-48 h-9 px-4 rounded-full border border-neutral-200 bg-neutral-50 text-sm text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:border-black focus:bg-white transition-colors"
        />
        <div className="flex gap-1">
          {(['all','added','removed','changed'] as ChangeFilter[]).map(v => {
            const cnt = v === 'all' ? all.length
              : v === 'added' ? diff.added.length
              : v === 'removed' ? diff.removed.length
              : diff.changed.length
            return (
              <button key={v} onClick={() => setFilter(v)}
                className={clsx(
                  'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                  filter === v ? 'bg-black text-white' : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
                )}>
                {v === 'all' ? '전체' : v === 'added' ? '신규' : v === 'removed' ? '삭제' : '변경'}{cnt > 0 ? ` ${cnt}` : ''}
              </button>
            )
          })}
        </div>
      </div>

      <div className="border border-neutral-200 rounded-xl overflow-hidden bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '55px' }} /><col style={{ width: '55px' }} />
              <col style={{ width: '150px' }} /><col style={{ width: 'auto' }} /><col style={{ width: '200px' }} />
            </colgroup>
            <thead>
              <tr className="border-b border-neutral-100 bg-neutral-50">
                <th className="text-center py-2.5 px-3 text-xs font-medium text-neutral-500">구분</th>
                <th className="text-center py-2.5 px-3 text-xs font-medium text-neutral-500">종류</th>
                <th className="py-2.5 px-3 text-xs font-medium text-neutral-500 text-left">코드</th>
                <th className="py-2.5 px-3 text-xs font-medium text-neutral-500 text-left">상품명</th>
                <th className="py-2.5 px-3 text-xs font-medium text-neutral-500 text-left">변경 내용</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-50">
              {rows.length === 0
                ? <tr><td colSpan={5} className="py-12 text-center text-neutral-400 text-sm">결과 없음</td></tr>
                : rows.map((item: ProductChange) => (
                  <tr key={`${item.change_type}-${item.fund_code}`}
                    className={clsx(
                      'hover:bg-neutral-50 transition-colors',
                      item.change_type === 'added'   && 'bg-green-50/30',
                      item.change_type === 'removed' && 'bg-red-50/30',
                      item.change_type === 'changed' && 'bg-amber-50/20',
                    )}>
                    <td className="text-center py-2.5 px-3"><ChangeBadge type={item.change_type} /></td>
                    <td className="text-center py-2.5 px-3"><TypeBadge type={item.product_type} /></td>
                    <td className="font-mono text-xs text-neutral-500 truncate py-2.5 px-3">{item.fund_code}</td>
                    <td className="text-sm text-neutral-700 truncate py-2.5 px-3" title={item.fund_name}>{item.fund_name}</td>
                    <td className="text-xs text-neutral-500 py-2.5 px-3">
                      {item.changes.map(c => (
                        <div key={c.field} className="flex items-center gap-1 flex-wrap">
                          <span className="font-medium text-neutral-600">{c.label}</span>
                          <span className="line-through text-red-400">{c.old || '—'}</span>
                          <span className="text-neutral-400">→</span>
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
        <div className="px-4 py-2.5 border-t border-neutral-100 text-xs text-neutral-400">{rows.length}건 표시</div>
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

  const latestQ = useQuery({ queryKey: ['bank-imports'], queryFn: getLatestBankImports, staleTime: 30_000, retry: 1 })
  const diffQ   = useQuery({ queryKey: ['bank-diff'],    queryFn: getBankDiff,          staleTime: 30_000, retry: 1 })

  const isLoading  = latestQ.isLoading || diffQ.isLoading
  const isFetching = latestQ.isFetching || diffQ.isFetching

  const institutions = latestQ.data ?? []
  const diffs        = diffQ.data ?? []

  const isError = !isLoading && institutions.length === 0 && (latestQ.isError || diffQ.isError)

  const firstKey  = institutions[0]?.key ?? null
  const activeKey = selectedKey ?? firstKey

  const selectedLatest = institutions.find(d => d.key === activeKey)
  const selectedDiff   = diffs.find(d => d.key === activeKey)

  function refetch() { latestQ.refetch(); diffQ.refetch() }

  function handleDownload() {
    setDlState('working')
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
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900">기관 데이터</h1>
          <p className="text-sm text-neutral-500 mt-0.5">3개 기관 퇴직연금 상품목록 — 최신 이메일 기준</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownload}
            disabled={dlDisabled}
            className={clsx(
              'flex items-center gap-2 h-9 px-5 rounded-full text-sm font-medium transition-colors disabled:cursor-not-allowed',
              dlState === 'done'
                ? 'bg-neutral-900 text-white'
                : dlState === 'working'
                ? 'bg-neutral-300 text-neutral-500'
                : 'bg-black text-white hover:bg-neutral-800',
              dlDisabled && dlState === 'idle' && 'opacity-40',
            )}
          >
            {dlState === 'working' ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                생성 중...
              </>
            ) : dlState === 'done' ? (
              <>
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                완료
              </>
            ) : (
              <>
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                종목 마스터 CSV
              </>
            )}
          </button>
          <button
            onClick={refetch}
            disabled={isFetching}
            className="flex items-center gap-2 h-9 px-5 rounded-full text-sm font-medium text-neutral-700 bg-white border border-neutral-200 hover:border-neutral-400 transition-colors disabled:opacity-40"
          >
            <svg className={clsx('w-3.5 h-3.5', isFetching && 'animate-spin')} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {isFetching ? '불러오는 중...' : '새로고침'}
          </button>
        </div>
      </div>

      {/* 로딩 */}
      {isLoading && (
        <div className="flex items-center justify-center py-24">
          <div className="flex items-center gap-3 text-neutral-400">
            <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm">Gmail에서 최신 데이터를 가져오는 중...</span>
          </div>
        </div>
      )}

      {/* 에러 */}
      {isError && (
        <div className="flex flex-col items-center justify-center py-24 gap-4">
          <p className="text-sm text-neutral-900 font-medium">데이터를 불러오지 못했습니다</p>
          <p className="text-xs text-neutral-400">
            {latestQ.error instanceof Error ? latestQ.error.message : '서버 오류 — 잠시 후 새로고침해 주세요'}
          </p>
          <button
            onClick={refetch}
            className="h-9 px-5 rounded-full text-sm font-medium bg-black text-white hover:bg-neutral-800 transition-colors"
          >
            다시 시도
          </button>
        </div>
      )}

      {!isLoading && !isError && institutions.length > 0 && (
        <>
          {/* 기관 카드 */}
          <div className="grid grid-cols-3 gap-4">
            {institutions.map(inst => (
              <SummaryCard
                key={inst.key}
                instKey={inst.key}
                name={inst.name}
                selected={activeKey === inst.key}
                onClick={() => setSelectedKey(inst.key)}
                latest={inst}
                diff={diffs.find(d => d.key === inst.key)}
              />
            ))}
          </div>

          {/* 뷰 탭 */}
          <div className="flex items-center gap-1.5">
            {([['products', '상품 목록'], ['diff', '변경사항']] as [ViewTab, string][]).map(([v, label]) => (
              <button
                key={v}
                onClick={() => setViewTab(v)}
                className={clsx(
                  'h-9 px-4 rounded-full text-sm font-medium transition-colors',
                  viewTab === v ? 'bg-black text-white' : 'text-neutral-600 hover:bg-neutral-100'
                )}
              >
                {label}
                {v === 'diff' && selectedDiff && selectedDiff.total_changes > 0 && (
                  <span className="ml-1.5 px-1.5 py-0.5 bg-white/20 text-white text-xs rounded-full">
                    {selectedDiff.total_changes}
                  </span>
                )}
              </button>
            ))}
            {viewTab === 'diff' && selectedDiff && (
              <span className="text-xs text-neutral-400 ml-2">
                {selectedDiff.yesterday_date} → {selectedDiff.today_date}
              </span>
            )}
          </div>

          {/* 상세 테이블 */}
          {viewTab === 'products' && selectedLatest && <ProductTable inst={selectedLatest} />}
          {viewTab === 'diff' && selectedDiff && <DiffTable diff={selectedDiff} />}
        </>
      )}
    </div>
  )
}
