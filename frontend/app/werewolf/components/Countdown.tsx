import { useCountdown } from "../hooks/useCountdown";
import { tr } from "../i18n";

const URGENT_SECONDS = 10;

export default function Countdown({ timer }: { timer: { total: number; secondsLeft: number } }) {
  const left = useCountdown(timer) ?? 0;
  const percent = Math.min(100, (left / Math.max(1, timer.total)) * 100);
  const seconds = Math.ceil(left);
  return (
    <div className={`ww-countdown${left <= URGENT_SECONDS ? " ww-urgent" : ""}`} role="timer" aria-label={tr("con_seconds_giay", { seconds })}>
      <div className="ww-countdown-bar">
        <div style={{ width: `${percent}%` }} />
      </div>
      <span aria-hidden="true">⏱ {seconds}s</span>
    </div>
  );
}
