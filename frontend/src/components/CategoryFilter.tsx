import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getCategories } from '../api/funds'
import type { Category } from '../types'
import clsx from 'clsx'

interface CategoryFilterProps {
  selectedId: number | null
  onChange: (id: number | null) => void
}

export default function CategoryFilter({ selectedId, onChange }: CategoryFilterProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: getCategories,
  })

  // Top-level categories (level 1)
  const topLevel = categories.filter((c) => c.level === 1)

  function getChildren(parentId: number): Category[] {
    return categories.filter((c) => c.parent_id === parentId)
  }

  function handleTopClick(cat: Category) {
    if (expandedId === cat.id) {
      setExpandedId(null)
      if (selectedId !== null) {
        // Check if selected is a child of this
        const isChild = getChildren(cat.id).some((c) => c.id === selectedId)
        if (isChild || selectedId === cat.id) {
          onChange(null)
        }
      }
    } else {
      setExpandedId(cat.id)
      onChange(cat.id)
    }
  }

  function handleChildClick(cat: Category) {
    if (selectedId === cat.id) {
      // Deselect child, keep parent selected
      const parent = categories.find((c) => c.id === cat.parent_id)
      onChange(parent?.id ?? null)
    } else {
      onChange(cat.id)
    }
  }

  function handleReset() {
    setExpandedId(null)
    onChange(null)
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        onClick={handleReset}
        className={clsx(
          'px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150 border',
          selectedId === null
            ? 'bg-slate-800 text-white border-slate-800'
            : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300',
        )}
      >
        전체
      </button>

      {topLevel.map((top) => {
        const isExpanded = expandedId === top.id
        const children = getChildren(top.id)
        const isTopSelected = selectedId === top.id
        const isChildSelected = children.some((c) => c.id === selectedId)
        const isHighlighted = isTopSelected || isChildSelected

        return (
          <div key={top.id} className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => handleTopClick(top)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150 border',
                isHighlighted
                  ? 'bg-blue-500 text-white border-blue-500'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300 hover:text-blue-600',
              )}
            >
              {top.name}
              {children.length > 0 && (
                <span className="ml-1 text-xs opacity-70">{isExpanded ? '▲' : '▼'}</span>
              )}
            </button>

            {/* Sub-categories */}
            {isExpanded && children.map((child) => (
              <button
                key={child.id}
                onClick={() => handleChildClick(child)}
                className={clsx(
                  'px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150 border',
                  selectedId === child.id
                    ? 'bg-blue-100 text-blue-700 border-blue-300'
                    : 'bg-slate-50 text-slate-500 border-slate-200 hover:border-blue-200 hover:text-blue-600',
                )}
              >
                {child.name}
              </button>
            ))}
          </div>
        )
      })}
    </div>
  )
}
