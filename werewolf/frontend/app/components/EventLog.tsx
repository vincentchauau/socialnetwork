import { groupLog } from "../lib/log";
import type { LogEntry } from "../lib/types";

export default function EventLog({ title, log }: { title: string; log: LogEntry[] }) {
  const groups = groupLog(log);
  return (
    <section className="card" aria-label={title}>
      <h2>📜 {title}</h2>
      {groups.length === 0 && <p className="muted">Chưa có sự kiện.</p>}
      {groups.map((group, index) => (
        <div key={`${group.round}-${index}`} className="ww-log-group">
          <h3>
            <span aria-hidden="true">{group.round.startsWith("Ngày") ? "☀️" : "🌙"}</span> {group.round}
          </h3>
          <ul>
            {group.lines.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
