import type { Cell } from "../lib/types";

/** Every cell is rendered as plain text (React escapes it). */
export default function DataTable({ columns, rows, caption }: { columns: string[]; rows: Cell[][]; caption: string }) {
  if (columns.length === 0) return null;
  return (
    <div style={{ overflow: "auto" }}>
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={i} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length}>
                Không có dòng nào.
              </td>
            </tr>
          )}
          {rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, i) => (
                <td key={i}>{cell === null ? <span style={{ opacity: 0.6 }}>NULL</span> : String(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
