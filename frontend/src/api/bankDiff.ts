import client from './client'

export interface FieldChange {
  field: string
  label: string
  old: string
  new: string
}

export interface ProductChange {
  fund_code: string
  fund_name: string
  product_type: string
  change_type: 'added' | 'removed' | 'changed'
  changes: FieldChange[]
}

export interface InstitutionDiff {
  key: string
  name: string
  today_date: string | null
  yesterday_date: string | null
  added: ProductChange[]
  removed: ProductChange[]
  changed: ProductChange[]
  total_changes: number
  error: string | null
}

export async function getBankDiff(): Promise<InstitutionDiff[]> {
  const { data } = await client.get<InstitutionDiff[]>('/bank-imports/diff')
  return data
}
