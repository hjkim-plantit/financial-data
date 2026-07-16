import client from './client'

export interface SyncItemIn {
  raw_code: string
  fund_name: string
  product_type: string
}

export interface InstitutionItemsIn {
  key: string
  items: SyncItemIn[]
}

export interface UniverseTarget {
  key: string
  universe_id: number
  universe_name: string
}

export interface MissingProduct {
  raw_code: string
  fund_name: string
  product_type: string
  asset_missing: boolean
  universe_targets: UniverseTarget[]
  institutions: string[]
}

export interface InstitutionSummary {
  key: string
  total: number
  registered: number
  missing: number
}

export interface CompareResult {
  admin_asset_total: number
  universe_counts: Record<number, number>
  institutions: InstitutionSummary[]
  universe_note: string | null
  missing: MissingProduct[]
}

export interface ApplyItemResult {
  raw_code: string
  fund_name: string
  ok: boolean
  asset_created: boolean
  universes_added: number[]
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
  items: ApplyItemResult[]
  universes: ApplyUniverseResult[]
}

export async function comparePlantitSync(institutions: InstitutionItemsIn[]): Promise<CompareResult> {
  const { data } = await client.post<CompareResult>('/plantit-sync/compare', { institutions }, { timeout: 300_000 })
  return data
}

export async function applyPlantitSync(institutions: InstitutionItemsIn[]): Promise<ApplyResult> {
  const { data } = await client.post<ApplyResult>('/plantit-sync/apply', { institutions }, { timeout: 600_000 })
  return data
}
