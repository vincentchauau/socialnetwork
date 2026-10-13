import type { LabStatus } from "../lib/types";

export const MESSAGING_HINT =
  "RabbitMQ và Kafka đang tắt. Bật bằng COMPOSE_PROFILES=messaging (tốn thêm khoảng 0,7–1,3 GB RAM).";

const SERVICES: { key: "redis" | "grpc" | "rabbitmq" | "kafka"; label: string }[] = [
  { key: "redis", label: "Redis" },
  { key: "grpc", label: "gRPC" },
  { key: "rabbitmq", label: "RabbitMQ" },
  { key: "kafka", label: "Kafka" },
];

export default function StatusBar({ status, error }: { status: LabStatus | null; error: string | null }) {
  return (
    <section aria-labelledby="lab-status-title" className="stack">
      <h2 id="lab-status-title" className="sr-only">
        Trạng thái dịch vụ
      </h2>
      <ul className="lab-status" aria-labelledby="lab-status-title">
        {SERVICES.map(({ key, label }) => {
          const on = status?.[key] === true;
          return (
            <li key={key} className={`lab-badge${on ? " on" : ""}`}>
              {label}
              <span className="sr-only">{on ? ": đang chạy" : ": không chạy"}</span>
            </li>
          );
        })}
      </ul>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {status?.messaging === false && <p className="muted">{MESSAGING_HINT}</p>}
    </section>
  );
}
