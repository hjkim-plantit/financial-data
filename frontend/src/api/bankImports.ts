import client from './client'

export interface FundItem {
  fund_code: string       // KRZ 예탁원 코드 (은행 원본)
  fund_name: string
  product_type: string
  available: boolean
  risk_grade: number | null
  start_date: string | null
  end_date: string | null
  matched: boolean
  k55_code: string | null // K55/KR5 KOFIA 코드 (펀드조회 기준)
  asset_class: string
  region: string
  sector: string
}

export interface InstitutionData {
  key: string
  name: string
  email_date: string | null
  file_date: string | null
  total: number
  fund_total: number
  fund_matched: number
  etf_total: number
  etf_matched: number
  error: string | null
  items: FundItem[]
}

export async function getLatestBankImports(): Promise<InstitutionData[]> {
  const { data } = await client.get<InstitutionData[]>('/bank-imports/latest')
  return data
}
