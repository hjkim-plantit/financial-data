import client from './client'
import type { EmailImport } from '../types'

export async function getImports(): Promise<EmailImport[]> {
  const { data } = await client.get<EmailImport[]>('/imports')
  return data
}

export async function getImportDetail(id: number): Promise<EmailImport> {
  const { data } = await client.get<EmailImport>(`/imports/${id}`)
  return data
}

export async function triggerImport(): Promise<{ message: string }> {
  const { data } = await client.post<{ message: string }>('/imports/trigger')
  return data
}

export async function confirmItem(
  importId: number,
  itemId: number,
  categoryId: number,
): Promise<void> {
  await client.patch(`/imports/${importId}/items/${itemId}`, {
    confirmed_category_id: categoryId,
  })
}

export async function confirmImport(id: number): Promise<void> {
  await client.post(`/imports/${id}/confirm`)
}
