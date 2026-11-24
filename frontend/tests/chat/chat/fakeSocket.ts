import { act } from "@testing-library/react";

/** Minimal controllable WebSocket stand-in. */
export class FakeSocket {
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  closeCalls = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closeCalls += 1;
    this.readyState = 3;
  }

  open() {
    this.readyState = FakeSocket.OPEN;
    act(() => this.onopen?.());
  }
  frame(data: unknown) {
    act(() => this.onmessage?.({ data: typeof data === "string" ? data : JSON.stringify(data) }));
  }
  drop(code: number, reason = "") {
    this.readyState = 3;
    act(() => this.onclose?.({ code, reason }));
  }

  static reset() {
    FakeSocket.instances = [];
  }
  static byPath(path: string): FakeSocket[] {
    return FakeSocket.instances.filter((s) => s.url.endsWith(path));
  }
  static last(path: string): FakeSocket {
    const list = FakeSocket.byPath(path);
    return list[list.length - 1];
  }
}

/** A message frame (or a history row: the same fields) as the server sends it. */
export const msg = (id: number, username = "bob", content = `m${id}`, extra: Record<string, unknown> = {}) => ({
  type: "message",
  id,
  user_id: username === "alice" ? 1 : 2,
  username,
  kind: "text",
  content,
  reply_to_id: null,
  pinned_at: null,
  edited_at: null,
  created_at: `2026-01-01T00:00:${String(id).padStart(2, "0")}Z`,
  ...extra,
});
