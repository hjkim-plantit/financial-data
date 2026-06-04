import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getImports, triggerImport } from '../api/imports'
import type { EmailImport } from '../types'
import clsx from 'clsx'

function StatusBadge({ status }: { status: EmailImport['status'] }) {
  const styles = {
    검토중: 'badge-yellow',
    확정: 'badge-green',
    무시: 'badge-gray',
  }
  return <span className={clsx('badge', styles[status])}>{status}</span>
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

export default function ImportReviewPage() {
  const queryClient = useQueryClient()

  const { data: imports = [], isLoading, isError, error } = useQuery({
    queryKey: ['imports'],
    queryFn: getImports,
  })

  const triggerMutation = useMutation({
    mutationFn: triggerImport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['imports'] })
    },
  })

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">이메일 임포트</h1>
          <p className="text-sm text-slate-500 mt-0.5">이메일에서 펀드 데이터를 가져와 검토합니다</p>
        </div>
        <button
          onClick={() => triggerMutation.mutate()}
          disabled={triggerMutation.isPending}
          className="btn-primary flex items-center gap-2"
        >
          {triggerMutation.isPending ? (
            <>
              <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              가져오는 중...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              이메일 가져오기
            </>
          )}
        </button>
      </div>

      {/* Success message */}
      {triggerMutation.isSuccess && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700 flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          이메일 가져오기가 완료되었습니다.
        </div>
      )}

      {/* Error message */}
      {triggerMutation.isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 flex items-center gap-2">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          가져오기 중 오류가 발생했습니다.
        </div>
      )}

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
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>이메일 날짜</th>
                  <th>제목</th>
                  <th>파일명</th>
                  <th className="text-center">상태</th>
                  <th className="text-center">항목수</th>
                  <th>가져온 시각</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {imports.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-slate-400">
                      임포트 내역이 없습니다. 이메일 가져오기를 실행해주세요.
                    </td>
                  </tr>
                ) : (
                  imports.map((imp) => (
                    <tr key={imp.id}>
                      <td className="text-slate-700 tabular-nums">{formatDate(imp.email_date)}</td>
                      <td className="max-w-xs">
                        <p className="truncate text-slate-600" title={imp.email_subject ?? ''}>
                          {imp.email_subject ?? <span className="text-slate-300">제목 없음</span>}
                        </p>
                      </td>
                      <td>
                        {imp.file_name ? (
                          <span className="text-xs font-mono text-slate-500 bg-slate-50 px-2 py-0.5 rounded">
                            {imp.file_name}
                          </span>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                      <td className="text-center">
                        <StatusBadge status={imp.status} />
                      </td>
                      <td className="text-center tabular-nums text-slate-600">
                        {imp.items ? imp.items.length : '—'}
                      </td>
                      <td className="text-slate-500 text-xs tabular-nums">{formatDate(imp.imported_at)}</td>
                      <td>
                        <Link
                          to={`/imports/${imp.id}`}
                          className={clsx(
                            'inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-150',
                            imp.status === '검토중'
                              ? 'bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200'
                              : 'bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200',
                          )}
                        >
                          {imp.status === '검토중' ? '검토하기' : '상세보기'}
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
