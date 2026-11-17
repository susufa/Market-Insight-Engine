export type Market = 'CN_A' | 'CN_HK' | 'US' | 'INDEX';
export type Timeframe = '1d' | '1w' | '1M' | '1Q' | '1Y';
export type AdjustType = 'none' | 'qfq' | 'hfq';
export type ColorScheme = 'CN' | 'INTL';
export type SubChartIndicator = 'VOL' | 'MACD' | 'RSI' | 'KDJ' | 'ATR';

export interface Security {
  symbol: string;
  name: string;
  market: Market;
  asset_type: string;
  listing_status: string;
  listed_date?: string | null;
  currency: string;
}

export interface BarItem {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
}

export interface IndicatorRow extends BarItem {
  ma_5?: number | null;
  ma_10?: number | null;
  ma_20?: number | null;
  ma_60?: number | null;
  ema_12?: number | null;
  ema_26?: number | null;
  macd_dif?: number | null;
  macd_dea?: number | null;
  macd_hist?: number | null;
  rsi_6?: number | null;
  rsi_12?: number | null;
  rsi_14?: number | null;
  rsi_24?: number | null;
  kdj_k?: number | null;
  kdj_d?: number | null;
  kdj_j?: number | null;
  boll_upper?: number | null;
  boll_mid?: number | null;
  boll_lower?: number | null;
  atr_14?: number | null;
}

export interface IndicatorsResponse {
  symbol: string;
  timeframe: string;
  adj_type: string;
  count: number;
  is_cached: boolean;
  rows: IndicatorRow[];
}

export interface BarsResponse {
  symbol: string;
  timeframe: string;
  adj_type: string;
  count: number;
  data_quality_status: string;
  source_id: string;
  updated_at: string;
  is_cached: boolean;
  bars: BarItem[];
  data_origin?: string;
  source_interface?: string;
  data_fingerprint?: string;
}

export interface QuoteResponse {
  symbol: string;
  last_price: number;
  open: number;
  high: number;
  low: number;
  prev_close: number;
  change: number;
  pct_change: number;
  volume: number;
  amount: number;
  ts: string;
  timeframe: string;
  data_origin?: string;
  source_interface?: string;
}

export interface AcquisitionTaskItem {
  item_id: number;
  symbol: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'INTERRUPTED' | 'SKIPPED';
  row_count: number;
  provider_used?: string | null;
  source_interface?: string | null;
  execution_latency_ms?: number | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface AcquisitionTaskRecord {
  task_id: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL_SUCCESS' | 'FAILED' | 'CANCELLED' | 'INTERRUPTED';
  symbols: string[];
  timeframe: string;
  start_date: string;
  end_date: string;
  total_symbols: number;
  completed_symbols: number;
  failed_symbols: number;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  last_heartbeat_at?: string | null;
  error_message?: string | null;
  params?: Record<string, any>;
  items?: AcquisitionTaskItem[];
  progress_percent?: number;
}

export interface CreateAcquisitionTaskRequest {
  symbols: string[];
  timeframe?: string;
  start_date?: string;
  end_date?: string;
  provider_preference?: string;
  force_refresh?: boolean;
}

export interface SecuritiesResponse {
  total: number;
  items: Security[];
}

export interface IndexTicker {
  symbol: string;
  name: string;
  price: number;
  change: number;
  pct_change: number;
}

export interface BreadthReport {
  trade_date: string;
  market: string;
  total_universe_count: number;
  active_traded_count: number;
  suspended_count: number;
  missing_count: number;
  advance_count: number;
  decline_count: number;
  flat_count: number;
  advance_ratio: number;
  decline_ratio: number;
  median_change_pct: number;
  mean_change_pct: number;
  limit_up_count: number;
  limit_down_count: number;
  distribution: Record<string, number>;
  coverage_rate: number;
  survivorship_bias_warning: string;
}

export interface SectorSummary {
  sector_name: string;
  constituent_count: number;
  active_count: number;
  suspended_count: number;
  advance_count: number;
  decline_count: number;
  flat_count: number;
  avg_change_pct: number;
  total_volume: number;
  total_amount: number;
  relative_strength_vs_bench: number;
  top_performer: string;
  top_performer_pct: number;
  worst_performer: string;
  worst_performer_pct: number;
  constituents_source: string;
  updated_at: string;
}

export interface RelativePerformance {
  symbol: string;
  benchmark_symbol: string;
  sample_count: number;
  start_date: string;
  end_date: string;
  beta: number;
  alpha_annualized: number;
  correlation: number;
  r_squared: number;
  stock_annualized_return: number;
  benchmark_annualized_return: number;
  stock_volatility_annualized: number;
  benchmark_volatility_annualized: number;
  cumulative_excess_return: number;
}

export interface PredictionResult {
  symbol: string;
  as_of: string;
  horizon: number;
  timeframe: string;
  model_name: string;
  model_version: string;
  point_estimate: number;
  lower_bound: number;
  upper_bound: number;
  confidence: number;
  probabilities: Record<string, number>;
  feature_importance: Record<string, number>;
  train_date_range: [string, string];
  test_evaluation: Record<string, number>;
  disclaimer: string;
  data_origin?: 'real_provider' | 'manual_import' | 'synthetic_test' | 'unknown';
  is_synthetic?: boolean;
  data_source?: string;
  warning_message?: string;
}

export interface ModelEvaluationSummary {
  model_name: string;
  model_version: string;
  sample_count: number;
  fold_count: number;
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown: number;
  mae: number;
  rmse: number;
  baseline_win_rate: number;
  baseline_sharpe: number;
  outperformed_baseline: boolean;
  evaluation_time: string;
  data_origin?: 'real_provider' | 'manual_import' | 'synthetic_test' | 'unknown';
  is_synthetic?: boolean;
  data_source?: string;
  warning_message?: string;
}

export interface ModelCatalogItem {
  name: string;
  version: string;
  type: string;
  description: string;
}

export interface IndexQuote {
  symbol: string;
  label: string;
  price: number | null;
  pct: number | null;
  asOf?: string | null;
}

export type HealthState = 'checking' | 'live' | 'offline';
