import {
  BarsResponse,
  QuoteResponse,
  SecuritiesResponse,
  Timeframe,
  AdjustType,
  IndicatorsResponse,
  BreadthReport,
  SectorSummary,
  RelativePerformance,
  PredictionResult,
  ModelEvaluationSummary,
  ModelCatalogItem,
  AcquisitionTaskRecord,
  CreateAcquisitionTaskRequest,
} from './types';

const MARKET_BASE = '/api/v1/market';
const ANALYSIS_BASE = '/api/v1/analysis';
const PREDICTION_BASE = '/api/v1/prediction';
const ACQUISITION_BASE = '/api/v1/acquisition';
const SYSTEM_BASE = '/api/v1/system';

export async function fetchHealth(): Promise<{ status: string; version: string } | null> {
  try {
    const res = await fetch(SYSTEM_BASE + '/health');
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchSecurities(
  market?: string,
  search?: string,
  limit: number = 20
): Promise<SecuritiesResponse> {
  const params = new URLSearchParams();
  if (market) params.append('market', market);
  if (search) params.append('search', search);
  params.append('limit', limit.toString());

  try {
    const res = await fetch(`${MARKET_BASE}/securities?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('API fetchSecurities failed, returning empty list:', err);
    return {
      total: 0,
      items: [],
    };
  }
}

export async function fetchBars(
  symbol: string,
  timeframe: Timeframe = '1d',
  adjType: AdjustType = 'none',
  limit: number = 1000
): Promise<BarsResponse> {
  const params = new URLSearchParams({
    symbol,
    timeframe,
    adj_type: adjType,
    limit: limit.toString(),
  });

  try {
    const res = await fetch(`${MARKET_BASE}/bars?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data: BarsResponse = await res.json();
    return data;
  } catch (err) {
    console.warn(`API fetchBars failed for ${symbol}:`, err);
    return {
      symbol,
      timeframe,
      adj_type: adjType,
      count: 0,
      data_quality_status: 'DISCONNECTED',
      source_id: 'offline',
      updated_at: new Date().toISOString(),
      is_cached: false,
      bars: [],
    };
  }
}

export async function fetchQuote(symbol: string): Promise<QuoteResponse | null> {
  try {
    const res = await fetch(`${MARKET_BASE}/quote?symbol=${encodeURIComponent(symbol)}`);
    if (!res.ok) {
      console.warn(`fetchQuote returned HTTP ${res.status} for ${symbol}`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.warn(`API fetchQuote failed for ${symbol}:`, err);
    return null;
  }
}

export async function fetchIndicators(
  symbol: string,
  timeframe: Timeframe = '1d',
  adjType: AdjustType = 'qfq',
  limit: number = 500
): Promise<IndicatorsResponse> {
  const params = new URLSearchParams({
    symbol,
    timeframe,
    adj_type: adjType,
    limit: limit.toString(),
  });

  try {
    const res = await fetch(`${ANALYSIS_BASE}/indicators?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data: IndicatorsResponse = await res.json();
    return data;
  } catch (err) {
    console.warn(`API fetchIndicators failed for ${symbol}:`, err);
    return {
      symbol,
      timeframe,
      adj_type: adjType,
      count: 0,
      is_cached: false,
      rows: [],
    };
  }
}

export async function fetchMarketBreadth(market: string = 'CN_A'): Promise<BreadthReport | null> {
  try {
    const res = await fetch(`${ANALYSIS_BASE}/breadth?market=${market}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('API fetchMarketBreadth failed:', err);
    return null;
  }
}

export async function fetchSectors(
  benchmarkSymbol: string = '000001.SH'
): Promise<SectorSummary[]> {
  try {
    const res = await fetch(`${ANALYSIS_BASE}/sectors?benchmark_symbol=${benchmarkSymbol}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.sectors || [];
  } catch (err) {
    console.warn('API fetchSectors failed:', err);
    return [];
  }
}

export async function fetchRelativePerformance(
  symbol: string,
  benchmarkSymbol: string = '000001.SH'
): Promise<RelativePerformance | null> {
  const params = new URLSearchParams({
    symbol,
    benchmark_symbol: benchmarkSymbol,
  });

  try {
    const res = await fetch(`${ANALYSIS_BASE}/relative-performance?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('API fetchRelativePerformance failed:', err);
    return null;
  }
}

export async function fetchModelCatalog(): Promise<ModelCatalogItem[]> {
  try {
    const res = await fetch(`${PREDICTION_BASE}/models`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.models || [];
  } catch (err) {
    console.warn('API fetchModelCatalog failed:', err);
    return [];
  }
}

export async function fetchForecast(
  symbol: string,
  horizon: number = 5,
  modelName: string = 'lightgbm_quant_model',
  allowSynthetic: boolean = false
): Promise<PredictionResult | null> {
  const params = new URLSearchParams();
  params.append('symbol', symbol);
  params.append('horizon', horizon.toString());
  params.append('model_name', modelName);
  if (allowSynthetic) {
    params.append('allow_synthetic', 'true');
  }

  try {
    const res = await fetch(`${PREDICTION_BASE}/forecast?${params.toString()}`);
    if (!res.ok) {
      console.warn(`fetchForecast returned HTTP ${res.status} for ${symbol}`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.warn('API fetchForecast failed:', err);
    return null;
  }
}

export async function fetchWalkForwardReport(
  symbol: string,
  horizon: number = 5,
  modelName: string = 'lightgbm_quant_model',
  allowSynthetic: boolean = false
): Promise<ModelEvaluationSummary | null> {
  const params = new URLSearchParams();
  params.append('symbol', symbol);
  params.append('horizon', horizon.toString());
  params.append('model_name', modelName);
  if (allowSynthetic) {
    params.append('allow_synthetic', 'true');
  }

  try {
    const res = await fetch(`${PREDICTION_BASE}/walk-forward-report?${params.toString()}`);
    if (!res.ok) {
      console.warn(`fetchWalkForwardReport returned HTTP ${res.status} for ${symbol}`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.warn('API fetchWalkForwardReport failed:', err);
    return null;
  }
}

// --------------------------------------------------------------------------- //
// Acquisition APIs (Directive 1, 5)
// --------------------------------------------------------------------------- //

export async function createAcquisitionTask(
  req: CreateAcquisitionTaskRequest
): Promise<{ task_id: string; status: string; symbols_count: number; created_at: string }> {
  const res = await fetch(`${ACQUISITION_BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function fetchAcquisitionTask(task_id: string): Promise<AcquisitionTaskRecord> {
  const res = await fetch(`${ACQUISITION_BASE}/tasks/${task_id}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function listAcquisitionTasks(
  limit: number = 20,
  status?: string
): Promise<{ tasks: AcquisitionTaskRecord[] }> {
  const params = new URLSearchParams();
  params.append('limit', limit.toString());
  if (status) params.append('status', status);

  const res = await fetch(`${ACQUISITION_BASE}/tasks?${params.toString()}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function cancelAcquisitionTask(
  task_id: string
): Promise<{ task_id: string; status: string; message: string }> {
  const res = await fetch(`${ACQUISITION_BASE}/tasks/${task_id}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function resumeAcquisitionTask(
  task_id: string
): Promise<{ task_id: string; resumed: boolean; message: string }> {
  const res = await fetch(`${ACQUISITION_BASE}/tasks/${task_id}/resume`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function cleanupZombieTasks(): Promise<{ cleaned_zombie_tasks_count: number }> {
  const res = await fetch(`${ACQUISITION_BASE}/tasks/cleanup-zombies`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}
