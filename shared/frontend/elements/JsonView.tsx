"use client";

import type { CSSProperties } from "react";

interface Props {
  /** The json value, shown as it is: every key and every item on its own line, nested ones indented. */
  value: unknown;
  /** The most height the json takes in a cell; more scrolls inside it. */
  maxHeight?: number;
}

const INDENT_PX = 12;
const LINE: CSSProperties = { whiteSpace: "pre-wrap", wordBreak: "break-word" };

function Scalar({ value }: { value: unknown }) {
  if (value === null) return <span style={{ opacity: 0.6, fontStyle: "italic" }}>null</span>;
  if (typeof value === "string") return <span>{value}</span>;
  return <span>{String(value)}</span>;
}

/** One key (or index) with its value: a scalar on the same line, an object or array below it, indented. */
function Entry({ name, value, depth }: { name: string; value: unknown; depth: number }) {
  const nested = value !== null && typeof value === "object";
  return (
    <div style={{ ...LINE, paddingLeft: depth === 0 ? 0 : INDENT_PX }}>
      <span style={{ fontWeight: 600 }}>{name}</span>
      {nested ? null : <>: <Scalar value={value} /></>}
      {nested ? <Block value={value} depth={depth + 1} /> : null}
    </div>
  );
}

/** The inside of an object or an array: one entry per key or item. An empty one says so. */
function Block({ value, depth }: { value: unknown; depth: number }) {
  if (value === null || typeof value !== "object") return null;
  const entries: [string, unknown][] = Array.isArray(value)
    ? value.map((item, index) => [`#${index + 1}`, item])
    : Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return <div style={{ ...LINE, paddingLeft: INDENT_PX, opacity: 0.6 }}>{Array.isArray(value) ? "[ ]" : "{ }"}</div>;
  return (
    <>
      {entries.map(([name, item]) => <Entry key={name} name={name} value={item} depth={depth} />)}
    </>
  );
}

/** A json value in plain sight, as a readable list of its keys and values (no summary, no dialog). Read only. */
export default function JsonView({ value, maxHeight = 140 }: Props) {
  const nested = value !== null && typeof value === "object";
  return (
    <div style={{ maxHeight, overflow: "auto", fontSize: 12, lineHeight: 1.45, fontFamily: "ui-monospace, Consolas, monospace", textAlign: "left" }}>
      {nested ? <Block value={value} depth={0} /> : <Scalar value={value} />}
    </div>
  );
}
