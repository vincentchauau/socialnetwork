export type Source = "cache" | "grpc";
export type JobStatus = "queued" | "processing" | "retrying" | "done" | "dead";
export type LogLevel = "info" | "warn" | "error";

export interface LabStatus {
  redis: boolean;
  grpc: boolean;
  rabbitmq: boolean;
  kafka: boolean;
  messaging: boolean;
}

export interface UserLookup {
  id: string;
  name: string;
  source: Source;
  ms: number;
}

export interface NotificationRow {
  id: string | number;
  title: string;
  status: JobStatus;
  attempts: number;
}

/** GET /logs/replay: the topic read again from the beginning (only the caller's own messages). */
export interface ReplayResponse {
  fromBeginning: boolean;
  messages: LogRow[];
}

export interface LogRow {
  level: LogLevel;
  message: string;
  partition: number;
  offset: number;
}
