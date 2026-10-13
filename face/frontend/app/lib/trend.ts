export type Trend = "up" | "down" | "flat" | "none";

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
  up: "Đang tăng nhẹ so với các lần trước",
  down: "Đang giảm nhẹ so với các lần trước",
  flat: "Gần như ổn định",
  none: "Cần ít nhất 4 lần đo để xem xu hướng",
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
