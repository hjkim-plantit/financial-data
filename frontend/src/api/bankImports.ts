import client from './client'

export interface FundItem {
  fund_code: string   // 매칭 기준: K55(BNK) 또는 KRZ(우리, K55 없을 때)
  raw_code: string    // 은행 원본 KRZ 예탁원 코드
  fund_name: string
  product_type: string
  available: boolean
  risk_grade: number | null
  start_date: string | null
  end_date: string | null
  matched: boolean
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
