import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getImportDetail, confirmItem, confirmImport } from '../api/imports'
import { getCategories } from '../api/funds'
import type { ImportItem, Category } from '../types'
import clsx from 'clsx'

function MatchStatusBadge({ status }: { status: ImportItem['match_status'] }) {
  const config = {
    exact: { label: '정확매칭', cls: 'badge-green' },
    fuzzy: { label: '유사매칭', cls: 'badge-yellow' },
    unmatched: { label: '미매칭', cls: 'badge-red' },
  }
  const { label, cls } = config[status]
  return <span className={clsx('badge', cls)}>{label}</span>
}

function formatAmount(value: number | null): string {
  if (value === null) return '—'
  return value.toLocaleString('ko-KR') + '원'
}

function formatWeight(value: number | null): string {
  if (value === null) return '—'
  return value.toFixed(2) + '%'
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return dateStr
  }
}

interface ItemRowProps {
  item: ImportItem
  importId: number
  leafCategories: Category[]
  categoryMap: Map<number, string>
  onSaved: () => void
}

function ItemRow({ item, importId, leafCategories, categoryMap, onSaved }: ItemRowProps) {
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | ''>(
    item.confirmed_category_id ?? item.auto_category_id ?? '',
  )
  const [saved, setSaved] = useState(false)

  const mutation = useMutation({
    mutationFn: (categoryId: number) => confirmItem(importId, item.id, categoryId),
    onSuccess: () => {
      setSaved(true)
      onSaved()
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const isConfirmed = item.confirmed_category_id !== null
  const needsAttention = !isConfirmed && item.match_status === 'unmatched'

  return (
    <tr className={clsx(needsAttention && 'bg-red-50/30')}>
      <td>
        <span className="font-mono text-xs text-slate-500">{item.raw_code}</span>
      </td>
      <td>
        <p className="text-slate-700 font-medium">{item.raw_name ?? '—'}</p>
        {item.matched_fund_code && (
          <p className="text-xs text-slate-400 font-mono mt-0.5">{item.matched_fund_code}</p>
        )}
      </td>
      <td className="text-right tabular-nums">{formatAmount(item.amount)}</td>
      <td className="text-right tabular-nums">{formatWeight(item.weight_pct)}</td>
      <td className="text-center">
        <MatchStatusBadge status={item.match_status} />
      </td>
      <td>
        {item.auto_category_id ? (
          <span className="text-xs text-slate-500 bg-slate-50 px-2 py-0.5 rounded border border-slate-100">
            {categoryMap.get(item.auto_category_id) ?? `ID: ${item.auto_category_id}`}
          </span>
        ) : (
          <span className="text-slate-300 text-xs">자동제안 없음</span>
        )}
      </td>
      <td>
        <div className="flex items-center gap-2">
          <select
            value={selectedCategoryId}
            onChange={(e) => setSelectedCategoryId(e.target.value === '' ? '' : Number(e.target.value))}
            className={clsx(
              'input-base text-xs py-1.5 min-w-36',
              !isConfirmed && needsAttention && 'border-red-300 ring-1 ring-red-200',
              isConfirmed && 'border-emerald-300',
            )}
          >
            <option value="">-- 분류 선택 --</option>
            {leafCategories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>

          <button
            onClick={() => {
              if (selectedCategoryId !== '') {
                mutation.mutate(Number(selectedCategoryId))
              }
            }}
            disabled={selectedCategoryId === '' || mutation.isPending}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 whitespace-nowrap',
              saved
                ? 'bg-emerald-500 text-white'
                : 'bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed',
            )}
          >
            {mutation.isPending ? '저장중...' : saved ? '저장됨 ✓' : '저장'}
          </button>
        </div>

        {isConfirmed && item.confirmed_by && (
          <p className="text-xs text-slate-400 mt-1">
            {item.confirmed_by} · {item.confirmed_at ? formatDate(item.confirmed_at) : ''}
          </p>
        )}
      </td>
    </tr>
  )
}

export default function ImportDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const importId = Number(id)

  const { data: importData, isLoading, isError } = useQuery({
    queryKey: ['import', importId],
    queryFn: () => getImportDetail(importId),
    enabled: !isNaN(importId),
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: getCategories,
  })

  const leafCategories = categories.filter((c) => c.is_leaf)
  const categoryMap = new Map(categories.map((c) => [c.id, c.name]))

  const confirmAllMutation = useMutation({
    mutationFn: () => confirmImport(importId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['import', importId] })
      queryClient.invalidateQueries({ queryKey: ['imports'] })
    },
  })

  const handleItemSaved = () => {
    queryClient.invalidateQueries({ queryKey: ['import', importId] })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="flex items-center gap-3 text-slate-500">
          <svg className="animate-spin w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm">데이터 불러오는 중...</span>
        </div>
      </div>
    )
  }

  if (isError || !importData) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="text-center">
          <p className="text-sm font-medium text-slate-700">데이터를 불러오지 못했습니다</p>
          <button onClick={() => navigate('/imports')} className="btn-secondary mt-4 text-xs">
            목록으로 돌아가기
          </button>
        </div>
      </div>
    )
  }

  const items = importData.items ?? []
  const totalCount = items.length
  const autoMatchedCount = items.filter((i) => i.match_status !== 'unmatched').length
  const unmatchedCount = items.filter((i) => i.match_status === 'unmatched').length
  const confirmedCount = items.filter((i) => i.confirmed_category_id !== null).length

  const statusLabel: Record<string, string> = {
    검토중: '검토중',
    확정: '확정',
    무시: '무시',
  }

  const statusColor: Record<string, string> = {
    검토중: 'badge-yellow',
    확정: 'badge-green',
    무시: 'badge-gray',
  }

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/imports')}
          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-700 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-800">임포트 검토</h1>
            <span className={clsx('badge', statusColor[importData.status])}>
              {statusLabel[importData.status]}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-0.5">
            {formatDate(importData.email_date)} · {importData.file_name ?? '파일 없음'}
          </p>
        </div>

        {importData.status === '검토중' && (
          <button
            onClick={() => confirmAllMutation.mutate()}
            disabled={confirmAllMutation.isPending || confirmedCount < totalCount}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150',
              confirmedCount < totalCount
                ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                : 'bg-emerald-500 text-white hover:bg-emerald-600',
            )}
            title={confirmedCount < totalCount ? '모든 항목을 확정해야 전체 확정 가능합니다' : ''}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            {confirmAllMutation.isPending ? '처리중...' : '전체 확정'}
          </button>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-4">
          <p className="text-xs text-slate-500 font-medium">전체 항목</p>
          <p className="text-2xl font-bold text-slate-800 mt-1">{totalCount}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-slate-500 font-medium">자동매칭</p>
          <p className="text-2xl font-bold text-emerald-600 mt-1">{autoMatchedCount}</p>
          <p className="text-xs text-slate-400 mt-0.5">
            {totalCount > 0 ? Math.round((autoMatchedCount / totalCount) * 100) : 0}%
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-slate-500 font-medium">미매칭</p>
          <p className="text-2xl font-bold text-red-500 mt-1">{unmatchedCount}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-slate-500 font-medium">확정 완료</p>
          <p className="text-2xl font-bold text-blue-600 mt-1">{confirmedCount}</p>
          <p className="text-xs text-slate-400 mt-0.5">
            {totalCount > 0 ? Math.round((confirmedCount / totalCount) * 100) : 0}% 완료
          </p>
        </div>
      </div>

      {/* Progress bar */}
      {totalCount > 0 && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium text-slate-600">확정 진행률</p>
            <p className="text-xs text-slate-500">{confirmedCount} / {totalCount}</p>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${totalCount > 0 ? (confirmedCount / totalCount) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Items Table */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">항목 목록</h2>
          {unmatchedCount > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-amber-600 bg-amber-50 px-3 py-1.5 rounded-lg border border-amber-200">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              미매칭 항목 {unmatchedCount}개 분류 필요
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="table-base">
            <thead>
              <tr>
                <th>원본코드</th>
                <th>원본이름</th>
                <th className="text-right">금액</th>
                <th className="text-right">비중</th>
                <th className="text-center">매칭상태</th>
                <th>자동제안 분류</th>
                <th>확정 분류</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    항목이 없습니다
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <ItemRow
                    key={item.id}
                    item={item}
                    importId={importId}
                    leafCategories={leafCategories}
                    categoryMap={categoryMap}
                    onSaved={handleItemSaved}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bottom confirm button */}
      {importData.status === '검토중' && totalCount > 0 && (
        <div className="flex justify-end">
          <div className="flex items-center gap-3">
            {confirmedCount < totalCount && (
              <p className="text-sm text-slate-500">
                {totalCount - confirmedCount}개 항목이 아직 확정되지 않았습니다
              </p>
            )}
            <button
              onClick={() => confirmAllMutation.mutate()}
              disabled={confirmAllMutation.isPending || confirmedCount < totalCount}
              className={clsx(
                'flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 shadow-sm',
                confirmedCount < totalCount
                  ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                  : 'bg-emerald-500 text-white hover:bg-emerald-600 shadow-emerald-200',
              )}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {confirmAllMutation.isPending ? '처리중...' : '전체 확정'}
            </button>
          </div>
        </div>
      )}

      {confirmAllMutation.isSuccess && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700 flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          전체 확정이 완료되었습니다.
        </div>
      )}
    </div>
  )
}
