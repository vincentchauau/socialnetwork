"use client";

import { useEffect, useState } from "react";

import { errorText } from "../lib/errors";
import type { TablePage } from "../lib/types";
import { getTable } from "../lib/workApi";
import DataTable from "./DataTable";

export const PAGE_SIZE = 50;
export const SEARCH_DELAY_MS = 300;

export default function TableViewer({ name }: { name: string }) {
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<TablePage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(input);
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    let cancelled = false;
    getTable(name, page, PAGE_SIZE, q)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(errorText(e));
      });
    return () => {
      cancelled = true;
    };
  }, [name, page, q]);

  const pages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1;

  return (
    <section className="stack" aria-label={`Bảng ${name}`}>
      <h3>Bảng: {name}</h3>
      <label htmlFor="table-search">Tìm kiếm</label>
      <input id="table-search" type="search" value={input} onChange={(e) => setInput(e.target.value)} />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {data && <DataTable columns={data.columns} rows={data.rows} caption={`Dữ liệu bảng ${name}`} />}
      {data && (
        <div className="row pager">
          <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Trước
          </button>
          <span role="status">
            Trang {data.page} / {pages} ({data.total} dòng)
          </span>
          <button type="button" className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Sau
          </button>
        </div>
      )}
    </section>
  );
}
