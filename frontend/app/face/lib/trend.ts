import { tr } from "../i18n";
type Trend = "up" | "down" | "flat" | "none";

const TREND_THRESHOLD = 2;
const RECENT_COUNT = 3;

/** Newest-first values -> trend of the newest few against the older ones. */
export function trendOf(newestFirst: readonly number[]): Trend {
  if (newestFirst.length <= RECENT_COUNT) return "none";
  const avg = (xs: readonly number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  const delta = avg(newestFirst.slice(0, RECENT_COUNT)) - avg(newestFirst.slice(RECENT_COUNT));
  if (delta > TREND_THRESHOLD) return "up";
  if (delta < -TREND_THRESHOLD) return "down";
  return "flat";
}

export const TREND_LABEL: Record<Trend, string> = {
  get up() { return tr("dang_tang_nhe_so_voi_cac"); },
  get down() { return tr("dang_giam_nhe_so_voi_cac"); },
  get flat() { return tr("gan_nhu_on_dinh"); },
  get none() { return tr("can_it_nhat_4_lan_do"); },
};

/** SVG polyline points (oldest on the left) for 0..100 values. */
export function sparklinePoints(newestFirst: readonly number[], width: number, height: number): string {
  const values = [...newestFirst].reverse();
  if (values.length < 2) return "";
  const step = width / (values.length - 1);
  return values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - (Math.max(0, Math.min(100, v)) / 100) * height).toFixed(1)}`)
    .join(" ");
}
