import client from './client'
import type { Category, FundListItem, FundListParams, PaginatedResponse, UnclassifiedFundItem } from '../types'

export async function getFunds(params?: FundListParams): Promise<PaginatedResponse<FundListItem>> {
  const { data } = await client.get<PaginatedResponse<FundListItem>>('/funds/', { params })
  return data
}

export async function getCategories(): Promise<Category[]> {
  const { data } = await client.get<Category[]>('/categories/')
  return data
}

export async function getLeafCategories(): Promise<Category[]> {
  const { data } = await client.get<Category[]>('/categories/leaves')
  return data
}

export async function getUnclassifiedFunds(params?: { search?: string; skip?: number; limit?: number }): Promise<UnclassifiedFundItem[]> {
  const { data } = await client.get<UnclassifiedFundItem[]>('/funds/unclassified', { params })
  return data
}

export async function getUnclassifiedCount(): Promise<number> {
  const { data } = await client.get<{ count: number }>('/funds/unclassified/count')
  return data.count
}

export async function getLastUpdated(): Promise<{ fund: string | null; etf: string | null }> {
  const { data } = await client.get<{ fund: string | null; etf: string | null }>('/funds/last-updated')
  return data
}

export async function bulkCategorize(fundCodes: string[], categoryId: number): Promise<{ updated: number }> {
  const { data } = await client.patch<{ updated: number }>('/funds/bulk-categorize', {
    fund_codes: fundCodes,
    category_id: categoryId,
  })
  return data
}
