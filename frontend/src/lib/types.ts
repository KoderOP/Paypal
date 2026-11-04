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
  last_date: ISODate | null
  next_date: ISODate
  /** detected = learned from transactions · manual = added by you · paypal = PayPal Subscriptions API */
  source: 'detected' | 'manual' | 'paypal'
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

// ---- Buy now / wait / split ----------------------------------------------------------------------
export interface Payment { on: ISODate; amount: number }

export interface PaymentOption {
  id: string
  kind: 'pay_now' | 'wait' | 'pay_later'
  name: string
  summary: string
  get_it_on: ISODate
  payments: Payment[]
  total_paid: number
  extra_cost: number
  apr: number
  largest_payment: number
  min_balance: number
  min_balance_date: ISODate
  days_below_buffer: number
  safe: boolean
  series: number[]
  recommended: boolean
  action: 'checkout' | 'plan' | null
  funding: 'paypal' | 'paylater' | null
}

export interface PaymentComparison {
  as_of: ISODate
  amount: number
  label: string
  assumptions: Assumptions
  dates: ISODate[]
  baseline_series: number[]
  options: PaymentOption[]
  recommendation: { verdict: 'pay_now' | 'wait' | 'split' | 'not_recommended'; option_id: string | null; least_risky_id: string; headline: string; explanation: string[] }
  terms_note: string
  disclaimer: string
}

// ---- Goal solver -----------------------------------------------------------------------------------
export interface AffordabilityPoint { on: ISODate; day: number; max_safe_spend: number; limiting_date: ISODate; is_income_day: boolean }
export interface EarliestSafeDate {
  amount: number; found: boolean; on: ISODate | null; days_from_now: number | null
  max_safe_today: number; shortfall_today: number; explanation: string
}
export interface Affordability {
  as_of: ISODate
  assumptions: Assumptions
  search_days: number
  max_safe_today: number
  limiting_date_today: ISODate
  month_end: ISODate
  best_this_month: AffordabilityPoint
  best_in_window: AffordabilityPoint
  curve: AffordabilityPoint[]
  earliest: EarliestSafeDate | null
  explanation: string[]
}

// ---- Checkout --------------------------------------------------------------------------------------
export type CheckoutStatus = 'created' | 'awaiting_approval' | 'approved' | 'captured' | 'cancelled' | 'failed'
export interface CheckoutOrder {
  id: number
  paypal_order_id: string | null
  option_id: string
  funding: 'paypal' | 'paylater'
  label: string
  amount: number
  currency: string
  status: CheckoutStatus
  approve_url: string | null
  capture_id: string | null
  snapshot: {
    option_name?: string; summary?: string; safe?: boolean; recommended?: boolean
    min_balance?: string; min_balance_date?: ISODate; total_paid?: string; extra_cost?: string; apr?: string
    payments?: { on: ISODate; amount: string }[]; safety_buffer?: string; terms_note?: string | null
    recorded?: { kind: 'transaction' | 'obligations'; count?: number; external_id?: string }
  }
  error: string | null
  environment: string
}

// ---- Subscriptions --------------------------------------------------------------------------------
export interface LinkedSubscription {
  id: number; paypal_subscription_id: string; recurring_key: string | null; name: string; plan_id: string | null
  status: string; amount: number | null; currency: string | null; next_billing_date: ISODate | null; last_synced_at: string
}
export interface AddedSubscription { id: number; name: string; category: string; amount: number; next_billing_date: ISODate; key: string }
export interface SubscriptionInput { name: string; amount: number; next_billing_date: ISODate; category?: string }
export interface DetectedSubscription {
  key: string; merchant: string; name: string; category: string; amount: number; annual_cost: number
  day_of_month: number; next_date: ISODate; occurrences: number; source: RecurringItem['source']; cancelled: boolean
  cancelled_via: 'paypal' | 'manual' | null; linked: LinkedSubscription | null; added: AddedSubscription | null
}
export interface SubscriptionsOverview {
  api_available: boolean
  environment: string
  autopay_url: string
  detected: DetectedSubscription[]
  linked: LinkedSubscription[]
  /** Added by hand, but the merchant is now detected from history, so the added entry is ignored. */
  superseded: AddedSubscription[]
  totals: { monthly_active: number; annual_active: number; monthly_cancelled: number; annual_cancelled: number; count_active: number }
}

// ---- Scenarios -------------------------------------------------------------------------------------
export interface ScenarioChange { type: string; [k: string]: unknown }
export interface AppliedChange { type: string; description: string; monthly_effect: number; one_off_effect: number }
export interface ScenarioResult {
  as_of: ISODate; title: string; assumptions: Assumptions; applied: AppliedChange[]; notes: string[]
  baseline: Forecast; simulated: Forecast
  impacts: { day: number; on: ISODate; baseline: number; scenario: number; delta: number }[]
  monthly_effect: number; risks: Risk[]; summary: string[]
}

// ---- Auth ------------------------------------------------------------------------------------------
export interface PayPalIdentity { paypal_user_id: string; name: string; email: string | null; verified: boolean }
/** Sign in with PayPal is optional and open to any PayPal account; no feature depends on it. */
export interface AuthState {
  authenticated: boolean
  login_available: boolean
  environment: string
  identity: PayPalIdentity | null
  callback_url: string
  ephemeral_sessions: boolean
}

// ---- Assistant -------------------------------------------------------------------------------------
export interface ScenarioCard {
  kind: 'scenario'; title: string; applied: AppliedChange[]; notes: string[]; summary: string[]; risks: Risk[]
  impacts: { day: number; on: ISODate; baseline: number; scenario: number; delta: number }[]
  monthly_effect: number; safety_buffer: number; dates: ISODate[]; baseline_series: number[]; scenario_series: number[]
}
export interface SnapshotCard {
  kind: 'snapshot'; current_balance: number; monthly_income: number; avg_monthly_spending: number
  subscriptions_monthly: number; next_income_date: ISODate | null; projected_balance_90: number; safety_buffer: number
}
export type ToolCard = ({ kind: 'payment_options' } & PaymentComparison) | ({ kind: 'affordability' } & Affordability) | ScenarioCard | SnapshotCard

export interface ToolCall { tool: string; arguments: Record<string, unknown>; ok: boolean; summary: Record<string, unknown>; card: ToolCard | null }
export interface ChatTurn { role: 'user' | 'assistant'; content: string }
export interface ChatResponse {
  reply: string
  mode: 'llm' | 'rules'
  model: string | null
  verified: boolean
  guardrail: 'passed' | 'replaced' | null
  note: string | null
  tool_calls: ToolCall[]
}
export interface AssistantStatus { mode: 'llm' | 'rules'; model: string | null; guardrail: string }

export interface SettingsData {
  user_name: string
  currency: string
  data_source: string | null
  has_data: boolean
  assumptions: Assumptions
  paypal: PayPalStatus
  ai_configured: boolean
}
