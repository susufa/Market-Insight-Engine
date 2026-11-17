/** Small, allocation-free formatting helpers shared by every panel. */

export const isNum = (v: unknown): v is number =>
  typeof v === 'number' && Number.isFinite(v);

export function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(v, min), max);
}

export function fmtPrice(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return '—';
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtSigned(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return sign + fmtPrice(value, digits);
}

export function fmtPct(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return sign + value.toFixed(digits) + '%';
}

export function fmtCompact(value: number | null | undefined, unit = ''): string {
  if (!isNum(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e8) return (value / 1e8).toFixed(2) + '亿' + unit;
  if (abs >= 1e4) return (value / 1e4).toFixed(2) + '万' + unit;
  return value.toLocaleString('zh-CN') + unit;
}

export const fmtVolume = (v: number | null | undefined) => fmtCompact(v, '股');
export const fmtAmount = (v: number | null | undefined) => fmtCompact(v, '元');

export function fmtDate(ts: string | null | undefined): string {
  if (!ts) return '—';
  return ts.slice(0, 10);
}

export function fmtClock(ts: string | null | undefined): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString('zh-CN', { hour12: false });
}

export function fmtDateTime(ts: string | null | undefined): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return (
    d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) +
    ' ' +
    d.toLocaleTimeString('zh-CN', { hour12: false })
  );
}

/** 0.47 → "47.0%" — a share of a whole, never signed. */
export function fmtShare(value: number | null | undefined, digits = 1): string {
  if (!isNum(value)) return '—';
  return (value * 100).toFixed(digits) + '%';
}

/** 0.0054 → "0.54%"; keeps sign for diverging values. */
export function pctFromRatio(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return '—';
  return fmtSigned(value * 100, digits) + '%';
}

export function percent(part: number, total: number, digits = 1): string {
  if (!isNum(part) || !isNum(total) || total <= 0) return '—';
  return ((part / total) * 100).toFixed(digits) + '%';
}

export type Tone = 'up' | 'down' | 'flat';

export function tone(value: number | null | undefined): Tone {
  if (!isNum(value) || value === 0) return 'flat';
  return value > 0 ? 'up' : 'down';
}
