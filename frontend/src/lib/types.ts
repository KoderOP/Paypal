// Mirrors backend Pydantic models. Monetary values arrive as JSON numbers already computed
// server-side with Decimal; the client only formats them, never does financial arithmetic.
export type ISODate = string

export interface Assumptions {
  horizon_days: number
  safety_buffer: number
  lookback_days: number
  variable_spend_multiplier: number
  include_obligations: boolean
  include_irregular_income: boolean
}

export interface CashEvent {
  on: ISODate
  amount: number
  label: string
  category: string
  kind: 'income' | 'recurring' | 'obligation' | 'variable' | 'scenario'
}

export interface DayPoint { on: ISODate; day: number; balance: number; inflow: number; outflow: number; events: CashEvent[] }

export interface Forecast {
  start_date: ISODate
  start_balance: number
  assumptions: Assumptions
  points: DayPoint[]
  end_balance: number
  min_balance: number
  min_balance_date: ISODate
  total_inflow: number
  total_outflow: number
  daily_variable_spend: number
  first_below_buffer: ISODate | null
  first_below_zero: ISODate | null
  days_below_buffer: number
}

export interface RecurringItem {
  key: string
  name: string
  merchant: string
  category: string
  kind: 'income' | 'subscription' | 'housing' | 'bill' | 'savings' | 'other'
  direction: 'in' | 'out'
  amount: number
  day_of_month: number
  occurrences: number
  last_date: ISODate
  next_date: ISODate
}

export interface CategorySpend {
  category: string
  monthly_average: number
  recurring_monthly: number
  variable_monthly: number
  share: string
  essential: boolean
}

export interface MonthSummary { month: string; income: number; spending: number; investments: number; net: number; partial: boolean }

export interface ObligationIn { title: string; category: string; amount: number; due_on: ISODate }

export interface HealthIndicator {
  key: string
  label: string
  value: string
  unit: 'percent' | 'months' | 'currency'
  status: 'good' | 'watch' | 'risk'
  detail: string
}

export interface Dashboard {
  as_of: ISODate
  user_name: string
  data_source: string
  kpis: {
    current_balance: number
    monthly_income: number
    monthly_expenditure: number
    monthly_investments: number
    savings_rate: string
    projected_balance_30: number
    projected_balance_90: number
    upcoming_obligations_total: number
    subscriptions_monthly: number
    next_income_date: ISODate | null
  }
  health: HealthIndicator[]
  history: { on: ISODate; balance: number }[]
  forecast: Forecast
  months: MonthSummary[]
  categories: CategorySpend[]
  upcoming_events: CashEvent[]
  recurring: RecurringItem[]
  obligations: ObligationIn[]
  assumptions: Assumptions
}

export interface FinancialProfile {
  as_of: ISODate
  current_balance: number
  history_start: ISODate | null
  transaction_count: number
  recurring_income: RecurringItem[]
  recurring_outflows: RecurringItem[]
  categories: CategorySpend[]
  months: MonthSummary[]
  monthly_income: number
  avg_monthly_income: number
  irregular_income_lookback: number
  avg_monthly_spending: number
  avg_monthly_investments: number
  essential_monthly: number
  variable_monthly: number
  recurring_outflow_monthly: number
  subscriptions_monthly: number
  savings_rate: string
  next_income_date: ISODate | null
  obligations: ObligationIn[]
}

export interface TwinData { profile: FinancialProfile; assumptions: Assumptions }

export interface Transaction { id: number; posted_on: ISODate; description: string; merchant: string; category: string; amount: number; source: string }
export interface TransactionPage { items: Transaction[]; total: number; page: number; page_size: number }
export interface ImportResult {
  format: string
  source: string
  rows: number
  imported: number
  skipped_duplicates: number
  account_id: number
  opening_balance: number
  warnings: string[]
}

export type FileFormat = 'paypal_activity' | 'bank_statement' | 'transactions'

export interface DemoFile {
  id: string
  title: string
  format: FileFormat
  filename: string
  description: string
  suggested_opening_balance: number | null
}

export interface StatusData { has_data: boolean; user_name: string; data_source: string | null; transaction_count: number }

export interface PayPalStatus { configured: boolean; environment: string; api_sync_available: boolean; message: string }

export interface PayPalOverview extends PayPalStatus {
  linked: boolean
  transaction_count: number
  inflow: number
  outflow: number
  first_date: ISODate | null
  last_date: ISODate | null
  top_merchants: { merchant: string; count: number; total: number }[]
}

export interface ObligationCreate { title: string; category: string; amount: number; due_on: ISODate; notes?: string }
export interface Obligation extends ObligationCreate { id: number; notes: string }

export interface PurchaseRequest { amount: number; purchase_date?: ISODate; label: string; safety_buffer?: number }

export interface TimingOption {
  label: string
  purchase_date: ISODate
  days_from_now: number
  balance_after_purchase: number
  min_balance: number
  min_balance_date: ISODate
  days_below_buffer: number
  safe: boolean
  is_selected: boolean
  is_recommended: boolean
}

export interface Risk { level: 'critical' | 'high' | 'medium' | 'low' | 'info'; title: string; detail: string }

export interface PurchaseSimulation {
  scenario: { amount: number; purchase_date: ISODate; label: string; category: string }
  as_of: ISODate
  assumptions: Assumptions
  starting_balance: number
  baseline: Forecast
  simulated: Forecast
  impacts: { day: number; on: ISODate; baseline: number; scenario: number; delta: number }[]
  risks: Risk[]
  timing_options: TimingOption[]
  recommendation: { verdict: 'safe_now' | 'wait' | 'not_recommended'; recommended_date: ISODate | null; headline: string; explanation: string[] }
  runway_months_before: string
  runway_months_after: string
  monthly_surplus: number
  months_to_recover: string | null
  disclaimer: string
}

export interface ScenarioInfo { type: string; title: string; description: string; status: 'available' | 'planned' }

export interface SettingsData {
  user_name: string
  currency: string
  data_source: string | null
  has_data: boolean
  assumptions: Assumptions
  paypal: PayPalStatus
  ai_configured: boolean
}
