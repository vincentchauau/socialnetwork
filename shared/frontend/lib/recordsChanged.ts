/** The tiny event that tells a gallery its table changed elsewhere on the page (e.g. a create form in another pane). */
const RECORDS_CHANGED = "sn:records-changed";

export interface RecordsChangedDetail {
  table: string;
}

/** Tells every gallery of `table` to reload. */
export function notifyRecordsChanged(table: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<RecordsChangedDetail>(RECORDS_CHANGED, { detail: { table } }));
}

/** Runs `onChange` when `table` changed; returns the function that stops listening. */
export function onRecordsChanged(table: string, onChange: () => void): () => void {
  const listener = (event: Event) => {
    if ((event as CustomEvent<RecordsChangedDetail>).detail?.table === table) onChange();
  };
  window.addEventListener(RECORDS_CHANGED, listener);
  return () => window.removeEventListener(RECORDS_CHANGED, listener);
}
