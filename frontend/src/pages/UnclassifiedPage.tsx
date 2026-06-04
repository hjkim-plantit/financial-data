import { useEffect, useState, useCallback } from 'react'
import type { Category, UnclassifiedFundItem } from '../types'
import { getUnclassifiedFunds, getUnclassifiedCount, getLeafCategories, bulkCategorize } from '../api/funds'

const PAGE_SIZE = 100

export default function UnclassifiedPage() {
  const [funds, setFunds] = useState<UnclassifiedFundItem[]>([])
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [leafCategories, setLeafCategories] = useState<Category[]>([])
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set())
  const [targetCategoryId, setTargetCategoryId] = useState<number | ''>('')
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [items, count] = await Promise.all([
        getUnclassifiedFunds({ search: search || undefined, skip, limit: PAGE_SIZE }),
        getUnclassifiedCount(),
      ])
      setFunds(items)
      setTotal(count)
      setSelectedCodes(new Set())
    } finally {
      setLoading(false)
    }
  }, [search, skip])

  useEffect(() => {
    getLeafCategories().then(cats => setLeafCategories(cats.filter(c => c.id !== 99)))
  }, [])

  useEffect(() => { load() }, [load])

  // 검색
  const handleSearch = () => {
    setSearch(searchInput)
    setSkip(0)
  }

  // 전체 선택/해제
  const allChecked = funds.length > 0 && funds.every(f => selectedCodes.has(f.fund_code))
  const toggleAll = () => {
    if (allChecked) {
      setSelectedCodes(new Set())
    } else {
      setSelectedCodes(new Set(funds.map(f => f.fund_code)))
    }
  }

  const toggleOne = (code: string) => {
    setSelectedCodes(prev => {
      const next = new Set(prev)
      next.has(code) ? next.delete(code) : next.add(code)
      return next
    })
  }

  // 일괄 분류 적용
  const handleApply = async () => {
    if (!targetCategoryId) {
      setMessage({ type: 'error', text: '분류를 선택하세요' })
      return
    }
    if (selectedCodes.size === 0) {
      setMessage({ type: 'error', text: '펀드를 선택하세요' })
      return
    }
    setApplying(true)
    setMessage(null)
    try {
      const { updated } = await bulkCategorize([...selectedCodes], Number(targetCategoryId))
      setMessage({ type: 'success', text: `${updated}건 분류 완료` })
      await load()
    } catch {
      setMessage({ type: 'error', text: '적용 중 오류가 발생했습니다' })
    } finally {
      setApplying(false)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(skip / PAGE_SIZE) + 1

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* 헤더 */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-800">미분류 펀드 관리</h1>
        <p className="text-sm text-slate-500 mt-1">자동 분류되지 않은 펀드를 수동으로 분류합니다</p>
      </div>

      {/* 액션 바 */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4 flex flex-wrap items-center gap-3">
        {/* 검색 */}
        <div className="flex gap-2 flex-1 min-w-[200px]">
          <input
            type="text"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="펀드명 검색"
            className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={handleSearch}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm rounded-lg transition-colors"
          >
            검색
          </button>
        </div>

        <div className="h-6 w-px bg-slate-200" />

        {/* 분류 선택 + 적용 */}
        <div className="flex items-center gap-2">
          <select
            value={targetCategoryId}
            onChange={e => setTargetCategoryId(e.target.value === '' ? '' : Number(e.target.value))}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
          >
            <option value="">분류 선택</option>
            {leafCategories.map(cat => (
              <option key={cat.id} value={cat.id}>{cat.name}</option>
            ))}
          </select>
          <button
            onClick={handleApply}
            disabled={applying || selectedCodes.size === 0 || targetCategoryId === ''}
            className="px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
          >
            {applying ? '적용 중…' : `선택 ${selectedCodes.size}건 분류 적용`}
          </button>
        </div>
      </div>

      {/* 메시지 */}
      {message && (
        <div className={`mb-4 px-4 py-2.5 rounded-lg text-sm font-medium ${
          message.type === 'success'
            ? 'bg-green-50 text-green-700 border border-green-200'
            : 'bg-red-50 text-red-700 border border-red-200'
        }`}>
          {message.text}
        </div>
      )}

      {/* 카운트 */}
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm text-slate-500">
          전체 미분류 <span className="font-semibold text-slate-800">{total.toLocaleString()}</span>건
          {selectedCodes.size > 0 && (
            <span className="ml-2 text-blue-600">{selectedCodes.size}건 선택됨</span>
          )}
        </span>
        {/* 페이지네이션 */}
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
              disabled={skip === 0}
              className="px-3 py-1 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50"
            >
              이전
            </button>
            <span className="text-sm text-slate-600">{currentPage} / {totalPages}</span>
            <button
              onClick={() => setSkip(skip + PAGE_SIZE)}
              disabled={currentPage >= totalPages}
              className="px-3 py-1 text-sm border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-50"
            >
              다음
            </button>
          </div>
        )}
      </div>

      {/* 테이블 */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50">
              <th className="w-10 px-4 py-3">
                <input
                  type="checkbox"
                  checked={allChecked}
                  onChange={toggleAll}
                  className="rounded border-slate-300 text-blue-500 focus:ring-blue-500"
                />
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">펀드명</th>
              <th className="px-4 py-3 text-left font-medium text-slate-600 w-32">KOFIA 유형</th>
              <th className="px-4 py-3 text-left font-medium text-slate-600 w-32">펀드코드</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-slate-400">로딩 중…</td>
              </tr>
            ) : funds.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-slate-400">
                  미분류 펀드가 없습니다
                </td>
              </tr>
            ) : (
              funds.map(fund => (
                <tr
                  key={fund.fund_code}
                  onClick={() => toggleOne(fund.fund_code)}
                  className={`border-b border-slate-50 cursor-pointer transition-colors ${
                    selectedCodes.has(fund.fund_code)
                      ? 'bg-blue-50'
                      : 'hover:bg-slate-50'
                  }`}
                >
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedCodes.has(fund.fund_code)}
                      onChange={() => toggleOne(fund.fund_code)}
                      className="rounded border-slate-300 text-blue-500 focus:ring-blue-500"
                    />
                  </td>
                  <td className="px-4 py-3 text-slate-800">{fund.fund_name}</td>
                  <td className="px-4 py-3">
                    <span className="inline-block px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-xs">
                      {fund.kofia_fund_type ?? '-'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 font-mono text-xs">{fund.fund_code}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
