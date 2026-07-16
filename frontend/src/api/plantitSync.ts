import client from './client'

export interface SyncItemIn {
  raw_code: string
  fund_name: string
  product_type: string
}

export interface CompareItem {
  raw_code: string
  fund_name: string
  product_type: string
  status: 'asset_missing' | 'universe_missing'
  universe_id: number | null
}

export interface CompareResult {
  key: string
  universe_note: string | null
  admin_asset_total: number
  universe_counts: Record<number, number>
  registered: number
  missing: CompareItem[]
}

export interface ApplyItemResult {
  raw_code: string
  fund_name: string
  ok: boolean
  action: string
  detail: string
}

export interface ApplyUniverseResult {
  universe_id: number
  universe_name: string
  added: number
  ok: boolean
  detail: string
}

export interface ApplyResult {
  key: string
  items: ApplyItemResult[]
  universes: ApplyUniverseResult[]
}

export async function comparePlantitSync(key: string, items: SyncItemIn[]): Promise<CompareResult> {
  const { data } = await client.post<CompareResult>('/plantit-sync/compare', { key, items }, { timeout: 120_000 })
  return data
}

export async function applyPlantitSync(key: string, items: SyncItemIn[]): Promise<ApplyResult> {
  const { data } = await client.post<ApplyResult>('/plantit-sync/apply', { key, items }, { timeout: 300_000 })
  return data
}
