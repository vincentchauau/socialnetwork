export interface Entry {
  name: string;
  type: "folder" | "file";
  size: number;
  modifiedAt: string;
}

export interface Listing {
  path: string;
  entries: Entry[];
  usage: { usedBytes: number; quotaBytes: number };
}

export interface TableInfo {
  name: string;
  rows: number;
}

export type Cell = string | number | boolean | null;

export interface TablePage {
  columns: string[];
  rows: Cell[][];
  total: number;
  page: number;
  pageSize: number;
}

export interface QueryResult {
  columns: string[];
  rows: Cell[][];
  rowCount: number;
  changes: number;
  truncated: boolean;
}

export interface CallEvent {
  id: number | string;
  eventType: string;
  fromNumber: string;
  toNumber: string;
  createdAt: string;
}
