export interface Category {
  id: number
  code: string
  name: string
  level: number
  parent_id: number | null
  is_leaf: boolean
  children?: Category[]
}

export interface FundListItem {
  fund_code: string
  fund_name: string
  management_company: string
  risk_grade: number | null
  status: string
  inception_date: string | null
  product_type: string
  category_full_path: string | null
  nav: number | null
  aum: number | null
  nav_date: string | null
  return_1m: number | null
  return_3m: number | null
  return_1y: number | null
}

export interface ImportItem {
  id: number
  raw_code: string
  raw_name: string | null
  amount: number | null
  weight_pct: number | null
  matched_fund_code: string | null
  auto_category_id: number | null
  match_status: 'exact' | 'fuzzy' | 'unmatched'
  confirmed_category_id: number | null
  confirmed_by: string | null
  confirmed_at: string | null
}

export interface EmailImport {
  id: number
  email_subject: string | null
  email_date: string
  file_name: string | null
  status: '검토중' | '확정' | '무시'
  imported_at: string
  items?: ImportItem[]
}

export interface UnclassifiedFundItem {
  fund_code: string
  fund_name: string
  kofia_fund_type: string | null
}

export interface FundListParams {
  search?: string
  category_id?: number
  status?: string
  product_type?: string
  risk_grade?: number
  page?: number
  page_size?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
