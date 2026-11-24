import { ApiError, apiFetch, loadSession, refreshSession } from "@sn/api";
import { act, render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPage from "../../_pages/chat";
import type { MemberRow, Room } from "../../../app/chat/protocol";
import { FakeSocket, msg } from "./fakeSocket";

vi.mock("next/navigation", async (importOriginal) => ({ ...(await importOriginal<typeof import("next/navigation")>()), useRouter: () => ({ push: vi.fn() }) }));
vi.mock("../../../app/werewolf/components/RoomView", () => ({
  default: ({ code, onExit }: { code: string; onExit: () => void }) => (
    <div data-testid="werewolf">
      game {code}
      <button type="button" onClick={onExit}>leave the game</button>
    </div>
  ),
}));
vi.mock("@sn/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sn/api")>()),
  apiFetch: vi.fn(),
  loadSession: vi.fn(),
  refreshSession: vi.fn(),
}));

const fetchMock = vi.mocked(apiFetch);

// ---- a small server: rooms, members and messages it holds, and the calls it was asked ----

interface Call {
  method: string;
  path: string;
  body?: Record<string, unknown>;
}

const db = {
  rooms: [] as Room[],
  members: {} as Record<string, MemberRow[]>,
  history: {} as Record<string, unknown[]>,
  events: {} as Record<string, unknown[]>,
  gameError: null as ApiError | null,
  calls: [] as Call[],
  meeting: null as { id: number; room: string; url: string; base: string; mode: string } | null,
  fail: {} as Record<string, ApiError>,
  person: undefined as unknown,
  people: [] as { user_id: number; username: string; online: boolean }[],
  reports: [] as { id: number; target_type: string; target_id: string }[],
};

const ME = { role: "member", status: "joined", muted: false, unread: 0 } as const;

function room(slug: string, extra: Partial<Room> = {}): Room {
  return {
    id: db.rooms.length + 1, slug, kind: "chat", title: slug, category: "", user_id: 9,
    visibility: "public", join_policy: "open", capacity: 200, state: "open", members: 2, online: 0,
    me: { ...ME }, ...extra,
  } as Room;
}

const member = (user_id: number, username: string, extra: Partial<MemberRow> = {}): MemberRow => ({
  user_id, username, role: "member", status: "joined", muted: false, online: false, ...extra,
});

const bySlug = (slug: string): Room => {
  const found = db.rooms.find((r) => r.slug === slug);
  if (!found) throw new ApiError(404, "Room not found", { detail: "Room not found" });
  return found;
};

function serve(path: string, init: RequestInit = {}): unknown {
  const method = init.method ?? "GET";
  const body = init.body ? (JSON.parse(init.body as string) as Record<string, unknown>) : undefined;
  if (/^\/api\/chat\/rooms\/[^/]+\/meeting/.test(path)) {  // the meeting of a room: /api/chat/rooms/{slug}/meeting[/start|/end]
    db.calls.push({ method, path: path.replace(/^\/api\/chat/, ""), body });
    if (path.endsWith("/start")) return (db.meeting ??= { id: 1, room: "sn-secret", url: "https://meet.jit.si/sn-secret", base: "https://meet.jit.si", mode: String(body?.mode) });
    if (path.endsWith("/end")) return void (db.meeting = null);
    if (!db.meeting) throw new ApiError(404, "No open meeting", { detail: "No open meeting" });
    return db.meeting;
  }
  const url = new URL(path.replace(/^\/api\/chat/, ""), "http://x");
  db.calls.push({ method, path: url.pathname + url.search, body });
  const failure = db.fail[`${method} ${url.pathname}`];
  if (failure) throw failure;
  const parts = url.pathname.split("/").filter(Boolean); // rooms, slug, …
  if (parts[0] === "reports" && parts[1] === "mine") return db.reports;
  if (parts[0] === "reports" && method === "POST") {
    const made = { id: 70, target_type: String(body?.target_type), target_id: String(body?.target_id) };
    db.reports.push(made);
    return made;
  }
  if (parts[0] === "reports" && method === "DELETE") return void (db.reports = db.reports.filter((row) => row.id !== Number(parts[1])));
  if (["blocks", "friends"].includes(parts[0])) return undefined;  // (the people side has its own tests)
  if (parts[0] === "me") return { unread: 0 };
  if (parts[0] === "people") return db.person ?? undefined;  // (the people side has its own tests)
  if (parts[0] === "inbox") return { messages: 0, requests: db.rooms.filter((r) => r.kind === "dm" && r.me?.status === "pending").length, notices: 0 };
  if (parts[0] === "members") {
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const found = db.people.filter((p) => p.username.toLowerCase().includes(q));
    return { users: found.slice(offset, offset + 3), total: db.people.length, online: db.people.filter((p) => p.online).length };
  }
  if (parts[0] === "dm") {
    const chat = room("dm-1-2", { kind: "dm", title: "alice & bob", visibility: "private", capacity: 2, me: { ...ME, role: "owner" } });
    db.rooms.push(chat);
    return chat;
  }
  const slug = parts[1] ? decodeURIComponent(parts[1]) : "";
  const rest = parts.slice(2).join("/");
  if (!slug) {
    if (method === "POST") {
      const made = room(String(body?.slug ?? String(body?.title).toLowerCase().replace(/\W+/g, "-")), { ...(body as Partial<Room>), me: { ...ME, role: "owner" }, members: 1 });
      db.rooms.push(made);
      return made;
    }
    const scope = url.searchParams.get("scope");
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const hit = (r: Room) =>
      q === "" || r.title.toLowerCase().includes(q) || (r.hit ? true : false);
    const wanted = (r: Room) =>
      scope === "requests" ? r.kind === "dm" && r.me?.status === "pending"
      : scope === "mine" ? r.me !== null && (r.me.status === "joined" || (r.me.status === "pending" && r.kind !== "dm")) && r.state !== "deleted"
      : scope === "past" ? r.me !== null && ["left", "kicked"].includes(r.me.status)
      : r.visibility === "public" && r.state === "open";
    return db.rooms.filter((r) => wanted(r) && hit(r));
  }
  const found = bySlug(slug);
  if (rest === "") {
    if (method === "PATCH") return Object.assign(found, body);
    if (method === "DELETE") {
      found.state = "deleted";
      return undefined;
    }
    return found;
  }
  if (rest === "join") {
    found.me = { ...ME, status: found.join_policy === "approval" && !body?.code ? "pending" : "joined" };
    return found;
  }
  if (rest === "leave") {
    found.me = found.me && { ...found.me, status: "left" };
    return undefined;
  }
  if (rest === "events") return db.events[slug] ?? [];
  if (rest === "accept") return Object.assign(found, { me: { ...found.me, status: "joined" } });
  if (rest === "decline") return void (found.me = found.me && { ...found.me, status: "left" });
  if (rest === "me") return Object.assign(found, { me: { ...found.me, ...body } });
  if (rest === "secrets/renew") return undefined;
  if (rest === "game") {
    if (db.gameError) throw db.gameError;
    return { code: "WOLFS", seats: 7 };
  }
  if (rest === "members" && method === "POST") {
    const list = (db.members[slug] ??= []);
    const known = list.find((m) => m.user_id === body?.user_id || m.username === body?.username);
    if (known) return Object.assign(known, { status: "joined" });
    const added = { user_id: 90 + list.length, username: String(body?.username), role: "member", status: "joined", muted: false, joined_at: "2026-01-01T00:00:00Z", online: false } as MemberRow;
    list.push(added);
    return added;
  }
  if (rest === "members") {
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const wanted = url.searchParams.get("status") ?? "";
    return (db.members[slug] ?? []).filter((m) => m.username.toLowerCase().includes(q) && (!wanted || m.status === wanted));
  }
  if (rest.startsWith("members/")) {
    const id = Number(rest.split("/")[1]);
    const row = (db.members[slug] ?? []).find((m) => m.user_id === id)!;
    if (method === "DELETE") {
      db.members[slug] = db.members[slug].filter((m) => m !== row);
      return undefined;
    }
    return Object.assign(row, body);
  }
  if (rest === "messages") {
    const before = url.searchParams.get("before");
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const all = ((db.history[slug] ?? []) as { id: number; content: string }[]).filter((m) => m.content.toLowerCase().includes(q));
    return before ? all.filter((m) => m.id < Number(before)) : all;
  }
  if (rest.startsWith("messages/") && method === "PATCH") {
    const id = Number(rest.split("/")[1]);
    const row = ((db.history[slug] ?? []) as { id: number; content: string; edited_at?: string | null }[]).find((m) => m.id === id)!;
    return Object.assign(row, { content: body?.content, edited_at: "2026-01-01T00:05:00Z" });
  }
  return undefined;
}

// ---- the page ----

const flush = () => act(async () => {});

beforeEach(() => {
  window.localStorage.clear(); // the parts of the chat that were left open by the test before
  FakeSocket.reset();
  db.rooms = [];
  db.members = {};
  db.history = {};
  db.events = {};
  db.gameError = null;
  db.calls = [];
  db.reports = [];
  db.fail = {};
  db.meeting = null;
  db.people = [];
  db.person = undefined;
  window.history.replaceState(null, "", "/chat");
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  vi.mocked(loadSession).mockResolvedValue({ id: 1, username: "alice" });
  vi.mocked(refreshSession).mockResolvedValue(true);
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => serve(path, init) as never);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const called = (method: string, pattern: RegExp) => db.calls.filter((c) => c.method === method && pattern.test(c.path));

/** `hash` defaults to a room that does not exist: the chat opens on the room everyone is in only when there is none at all. */
async function open(hash = "#room=none") {
  if (hash) window.history.replaceState(null, "", `/chat${hash}`);
  render(<ChatPage />);
  await screen.findByRole("complementary", { name: "Phòng chat" });
  await waitFor(() => expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(1));
  const lobby = FakeSocket.last("/ws-lobby");
  lobby.open();
  return lobby;
}

async function enter(slug: string) {
  await waitFor(() => expect(FakeSocket.byPath(`/ws/${slug}`).length).toBeGreaterThan(0));
  const socket = FakeSocket.last(`/ws/${slug}`);
  socket.open();
  await flush();
  return socket;
}

/** The actions of a row sit behind its "More" button: open it. */
function opened(row: HTMLElement): HTMLElement {
  const more = within(row).queryByRole("button", { name: /^Khác/ });
  if (more && more.getAttribute("aria-expanded") === "false") fireEvent.click(more);
  return row;
}

describe("the gate", () => {
  it("asks an anonymous visitor to sign in and opens no socket", async () => {
    vi.mocked(loadSession).mockResolvedValue(null);
    render(<ChatPage />);
    expect(await screen.findByRole("link", { name: "đăng nhập" })).toHaveAttribute("href", "/user");
    expect(FakeSocket.instances).toHaveLength(0);
  });
});

describe("the list of rooms", () => {
  it("says when the list cannot be loaded", async () => {
    db.fail["GET /rooms"] = new ApiError(503, "down");
    await open();
    expect(await screen.findByText("down")).toBeInTheDocument();
  });
});

describe("a room I belong to", () => {
  async function inRoom(extra: Partial<Room> = {}, history: unknown[] = []) {
    db.rooms = [room("g", { title: "General", ...extra })];
    db.history.g = history;
    await open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "General" }));
    const socket = await enter("g");
    return { user, socket };
  }

  it("sends a message with Enter, keeps a new line with Shift+Enter, and clears the box", async () => {
    const { user, socket } = await inRoom();
    const box = screen.getByLabelText("Tin nhắn", { selector: "textarea" });
    await user.type(box, "hello{Shift>}{Enter}{/Shift}world");
    expect(socket.sent).toEqual([]);
    expect(box).toHaveValue("hello\nworld");
    await user.type(box, "{Enter}");
    expect(socket.sent).toEqual([JSON.stringify({ content: "hello\nworld" })]);
    expect(box).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Gửi" })).not.toBeInTheDocument(); // Enter sends: there is no button
  });

  it("searches the messages of the room and says when nothing was found", async () => {
    const { user } = await inRoom({}, [msg(1, "bob", "tranh sơn dầu"), msg(2, "carol", "giá 500 USD")]);
    await user.type(within(await screen.findByRole("toolbar", { name: "Tin nhắn" })).getByRole("searchbox"), "tranh{Enter}");
    const results = await screen.findByRole("list", { name: "Kết quả tìm kiếm" });
    expect(within(results).getByText("tranh sơn dầu")).toBeInTheDocument();
    expect(within(results).queryByText("giá 500 USD")).not.toBeInTheDocument();
    expect(called("GET", /messages\?limit=30&q=tranh$/)).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Xóa tất cả" }));
    await user.type(within(screen.getByRole("toolbar", { name: "Tin nhắn" })).getByRole("searchbox"), "zzz{Enter}");
    expect(await within(screen.getByRole("toolbar", { name: "Tin nhắn" }).parentElement!).findByText("Không tìm thấy")).toBeInTheDocument();
  });

  it("filters the search of the messages by who said them (from:name), shows Select all as a line and takes columns away", async () => {
    const { user } = await inRoom({}, [msg(1, "bob", "tranh sơn dầu"), msg(2, "carol", "tranh lụa")]);
    const toolbar = within(await screen.findByRole("toolbar", { name: "Tin nhắn" }));
    await user.type(toolbar.getByRole("searchbox"), "tranh,from:carol{Enter}");
    const results = await screen.findByRole("list", { name: "Kết quả tìm kiếm" });
    expect(within(results).getByText("tranh lụa")).toBeInTheDocument();
    expect(within(results).queryByText("tranh sơn dầu")).not.toBeInTheDocument();
    expect(called("GET", /messages\?limit=30&q=tranh$/)).toHaveLength(1); // only the word goes to the server
    await user.click(toolbar.getByRole("button", { name: "Cột" }));
    await user.click(within(screen.getByRole("group", { name: "Cột" })).getByRole("checkbox", { name: "Người gửi" }));
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Tin nhắn" })).queryByRole("columnheader", { name: /Người gửi/ })).not.toBeInTheDocument());
    expect(within(screen.getByRole("log", { name: "Tin nhắn" })).getByRole("checkbox", { name: "Chọn tất cả" })).toBeDisabled(); // the line stays, but none of them is mine
    expect(screen.queryByRole("button", { name: "Tin mới" })).not.toBeInTheDocument(); // Enter writes
  });

  it("loads older messages", async () => {
    const page = Array.from({ length: 50 }, (_, index) => msg(index + 11, "bob", `m${index + 11}`));
    db.history.g = page;
    const { user } = await inRoom({}, page);
    db.history.g = [msg(1, "bob", "ancient"), ...page];
    await user.selectOptions(within(screen.getByRole("log", { name: "Tin nhắn" })).getByRole("combobox"), "100");
    await user.click(await screen.findByRole("button", { name: "Xem tin cũ hơn" }));
    expect(await screen.findByText("ancient")).toBeInTheDocument();
    expect(called("GET", /messages\?limit=50&before=11$/)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Xem tin cũ hơn" })).not.toBeInTheDocument();
  });

  it("blocks the box for a muted member and for a closed room", async () => {
    await inRoom({ me: { ...ME, muted: true } });
    expect(screen.getByText("Bạn đang bị tắt tiếng trong phòng này.")).toBeInTheDocument();
  });

  it("tells a closed room", async () => {
    await inRoom({ state: "closed" });
    expect(screen.getAllByText("Phòng đã đóng").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Tin nhắn", { selector: "textarea" })).toBeDisabled();
  });

  it("closes the door on someone who was banned, and offers the way back to the rooms", async () => {
    const { user, socket } = await inRoom();
    socket.drop(1008, "You are banned from this room");
    expect(await screen.findByRole("alert")).toHaveTextContent("Bạn đã bị cấm khỏi phòng này.");
    db.rooms = [];
    await user.click(screen.getByRole("button", { name: "Về danh sách phòng" }));
    expect(await screen.findByText("Chào mừng đến phòng chat")).toBeInTheDocument();
  });

  it("retries after a refusal, sends to sign in when the session ended, and reconnects after a drop", async () => {
    const { user, socket } = await inRoom();
    socket.drop(1013, "Room is full");
    await user.click(await screen.findByRole("button", { name: "Thử lại" }));
    await waitFor(() => expect(FakeSocket.byPath("/ws/g")).toHaveLength(2));
    const second = FakeSocket.last("/ws/g");
    second.open();
    vi.mocked(refreshSession).mockResolvedValue(false);
    second.drop(1008, "");
    expect(await screen.findByRole("link", { name: "đăng nhập" })).toHaveAttribute("href", "/user");
  });
});

describe("making a room", () => {
  it("opens the form, makes the room from what was typed, and enters it", async () => {
    await open();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Mở phòng" }));
    const form = await screen.findByRole("form", { name: "Mở phòng" });
    await user.type(within(form).getByLabelText("Tên phòng"), "Garage sale Q7");
    await user.type(within(form).getByLabelText("Nhóm, nhãn (ví dụ: cư dân)"), "garage sale");
    await user.selectOptions(within(form).getByLabelText("Trạng thái"), "approval");
    await user.click(within(form).getByRole("button", { name: "Mở phòng" }));
    await waitFor(() => expect(called("POST", /^\/rooms$/)).toHaveLength(1));
    const sent = called("POST", /^\/rooms$/)[0].body!;
    expect(sent).toMatchObject({ title: "Garage sale Q7", category: "garage sale", join_policy: "approval", visibility: "public", capacity: 200 });
    expect(sent).not.toHaveProperty("slug");
    await enter("garage-sale-q7");
    expect(window.location.hash).toBe("#room=garage-sale-q7");
    expect(screen.getByRole("heading", { name: "Garage sale Q7" })).toBeInTheDocument();
  });

  it("asks for a name before anything is sent, and shows the server's refusal", async () => {
    await open();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Mở phòng" }));
    const form = await screen.findByRole("form", { name: "Mở phòng" });
    await user.click(within(form).getByRole("button", { name: "Mở phòng" }));
    expect(await screen.findByText("Hãy nhập tên phòng.")).toBeInTheDocument();
    expect(called("POST", /^\/rooms$/)).toHaveLength(0);
    db.fail["POST /rooms"] = new ApiError(409, "That address is already used");
    await user.type(within(form).getByLabelText("Tên phòng"), "Taken");
    await user.click(within(form).getByRole("button", { name: "Mở phòng" }));
    expect(await screen.findByText("Địa chỉ phòng này đã có người dùng.")).toBeInTheDocument();
  });

  it("offers only two ways in, open or with approval, and cancels", async () => {
    await open();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Mở phòng" }));
    const form = await screen.findByRole("form", { name: "Mở phòng" });
    const ways = within(form).getByLabelText("Trạng thái");
    expect(within(ways).getAllByRole("option")).toHaveLength(2);
    await user.click(within(form).getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(screen.queryByRole("form", { name: "Mở phòng" })).not.toBeInTheDocument());
  });
});

describe("a room I am not in", () => {
  it("lets me join an open room from its link", async () => {
    db.rooms = [room("garage", { title: "Garage sale", me: null })];
    await open("#room=garage");
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Garage sale" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Vào phòng" }));
    await waitFor(() => expect(called("POST", /rooms\/garage\/join$/)).toHaveLength(1));
    await enter("garage");
    expect(called("POST", /join$/)[0].body).toBeUndefined();
  });

  it("asks to join a room that needs approval and then waits", async () => {
    db.rooms = [room("club", { join_policy: "approval", me: null })];
    await open("#room=club");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Xin vào phòng" }));
    expect(await screen.findByText("Yêu cầu của bạn đang chờ chủ phòng duyệt.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rút yêu cầu" }));
    expect(await screen.findByRole("button", { name: "Xin vào phòng" })).toBeInTheDocument();
    expect(called("POST", /club\/leave$/)).toHaveLength(1);
  });

  it("shows why a closed room cannot be joined, and what a missing room says", async () => {
    db.rooms = [room("over", { state: "closed", me: null })];
    await open("#room=over");
    expect((await screen.findAllByText("Phòng đã đóng")).length).toBeGreaterThan(0); // in the room, and as the note of its row
    expect(screen.queryByRole("button", { name: "Vào phòng" })).not.toBeInTheDocument();
    window.history.replaceState(null, "", "/chat#room=nowhere");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy phòng.");
  });

  it("shows a banned person that they are banned", async () => {
    db.rooms = [room("club", { me: { ...ME, status: "banned" } })];
    await open("#room=club");
    expect(await screen.findByText("Bạn đã bị cấm khỏi phòng này.")).toBeInTheDocument();
  });
});

describe("members and settings", () => {
  async function asOwner(extra: Partial<Room> = {}) {
    db.rooms = [room("g", { title: "General", me: { ...ME, role: "owner" }, join_policy: "approval", ...extra })];
    db.members.g = [member(1, "alice", { role: "owner" }), member(2, "bob", { online: true }), member(3, "carol"), member(4, "dave", { status: "pending" })];
    await open("#room=g");
    await enter("g");
    return userEvent.setup();
  }

  it("has no Meeting entry (the call is the User pane) and not the video call and the screen sharing", async () => {
    await asOwner();
    expect(screen.queryByRole("button", { name: /Họp/ })).not.toBeInTheDocument(); // no Activities menu: the call is the User pane
    expect(screen.queryByRole("button", { name: /Gọi video/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Chia sẻ màn hình/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Chơi Ma Sói/ })).not.toBeInTheDocument(); // the game is the Werewolf pane, not a button of the room
  });

  it("lets the owner close the room from its header, and nobody else (the status is a field of Edit)", async () => {
    const user = await asOwner({ join_policy: "approval" });
    const header = within(screen.getByRole("region", { name: "General" }));  // the room itself (its row in the list has the same button)
    expect(header.queryByRole("button", { name: /^Đặt (Công khai|Riêng tư)$/ })).not.toBeInTheDocument();
    await user.click(header.getByRole("button", { name: "Đóng" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/g$/)[0].body).toEqual({ state: "closed" }));
  });

  it("gives a member who is not the owner no status to choose and no room to close", async () => {
    db.rooms = [room("g", { title: "General" })];
    db.members.g = [member(1, "alice"), member(2, "bob")];
    await open("#room=g");
    await enter("g");
    expect(screen.queryByRole("button", { name: /^Đặt (Công khai|Riêng tư)$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Đóng" })).not.toBeInTheDocument();
  });

  it("accepts a request to write, and the chat opens", async () => {
    db.rooms = [room("dm-3-1", { kind: "dm", title: "carol & alice", visibility: "private", user_id: 3, me: { ...ME, status: "pending" } })];
    await open("#room=dm-3-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Chấp nhận trò chuyện" }));
    await waitFor(() => expect(called("POST", /dm-3-1\/accept$/)).toHaveLength(1));
    await enter("dm-3-1");
    expect(await screen.findByRole("button", { name: /^Members/ })).toBeInTheDocument();
  });

  it("declines a request, and it is gone", async () => {
    db.rooms = [room("dm-3-1", { kind: "dm", title: "carol & alice", visibility: "private", user_id: 3, me: { ...ME, status: "pending" } })];
    await open("#room=dm-3-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Từ chối" }));
    await waitFor(() => expect(called("POST", /dm-3-1\/decline$/)).toHaveLength(1));
    expect(await screen.findByText("Chào mừng đến phòng chat")).toBeInTheDocument();
  });

  it("blocks the one who asked: the block is made and the request declined", async () => {
    db.rooms = [room("dm-3-1", { kind: "dm", title: "carol & alice", visibility: "private", user_id: 3, me: { ...ME, status: "pending" } })];
    await open("#room=dm-3-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Chặn người này" }));
    await waitFor(() => expect(called("POST", /\/blocks\/3$/)).toHaveLength(1));
    await waitFor(() => expect(called("POST", /dm-3-1\/decline$/)).toHaveLength(1));
  });

  it("shows no badge of unread messages on a room that was quieted", async () => {
    db.rooms = [room("a", { title: "Loud", me: { ...ME, unread: 4 } }), room("b", { title: "Quiet", me: { ...ME, unread: 7, notify: false } })];
    await open();
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.queryByText("7")).not.toBeInTheDocument();
  });

  it("draws no line when everything was read or nothing was", async () => {
    db.rooms = [room("g", { title: "General", me: { ...ME, last_read: 4 } })];
    db.history.g = [msg(1, "bob", "a"), msg(4, "bob", "b")];
    await open("#room=g");
    await enter("g");
    await screen.findByText("b");
    expect(screen.queryByText("Tin chưa đọc")).not.toBeInTheDocument();
  });

  it("lets the owner open a closed room again from the room itself", async () => {
    const user = await asOwner({ state: "closed" });
    expect(screen.getAllByText(/Phòng đã đóng/).length).toBeGreaterThan(0);
    await user.click(within(screen.getByRole("region", { name: "General" })).getByRole("button", { name: "Mở lại" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/g$/)[0].body).toEqual({ state: "open" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Mở lại" })).not.toBeInTheDocument());
  });

  it("shows no button to open a closed room to someone who is not its owner", async () => {
    db.rooms = [room("g", { title: "General", state: "closed" })];
    await open("#room=g");
    await enter("g");
    expect(screen.queryByRole("button", { name: "Mở lại" })).not.toBeInTheDocument();
  });

  it("takes a room I left off my list, keeping the room", async () => {
    db.rooms = [room("old", { title: "Old room", me: { ...ME, status: "left" }, state: "closed" })];
    await open("#room=old");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Xóa khỏi danh sách" }));
    await waitFor(() => expect(called("POST", /old\/hide$/)).toHaveLength(1));
    expect(await screen.findByText("Chào mừng đến phòng chat")).toBeInTheDocument();
    expect(called("DELETE", /^\/rooms\/old/)).toHaveLength(0);  // the room itself is not touched
  });

  it("refreshes the room when the server says its members changed", async () => {
    await asOwner();
    const socket = FakeSocket.last("/ws/g");
    const before = called("GET", /^\/rooms\/g$/).length;
    socket.frame({ type: "member", event: "join", user_id: 8, username: "eve" });
    await waitFor(() => expect(called("GET", /^\/rooms\/g$/).length).toBeGreaterThan(before));
  });
});

describe("the home page", () => {
  it("opens on the first of my rooms when nothing else is asked for", async () => {
    db.rooms = [room("garage", { title: "Garage", members: 9 }), room("other", { title: "Other", me: null })];
    await open("");
    await enter("garage");
    expect(window.location.hash).toBe("#room=garage");
    expect(await screen.findByRole("heading", { name: "Garage" })).toBeInTheDocument();
  });

  it("shows the welcome when I am in no room yet", async () => {
    db.rooms = [room("other", { me: null })];
    await open("");
    expect(await screen.findByText("Chào mừng đến phòng chat")).toBeInTheDocument();
    expect(window.location.hash).toBe("");
  });

  it("opens the room asked for in the address instead", async () => {
    db.rooms = [room("garage", { title: "Garage" }), room("club", { title: "Club" })];
    await open("#room=club");
    await enter("club");
    expect(called("GET", /^\/rooms\/garage$/)).toHaveLength(0);
  });

});

// ---- the three tables of the chat: the rooms, the messages and the members work the same way ----

describe("Rooms: make one, read them all, change one (the owner), delete the ones picked (the owner's)", () => {
  const roomsBar = () => within(screen.getByRole("toolbar", { name: "Phòng chat" }));
  const roomsTable = async () => within(await screen.findByRole("table", { name: "Danh sách phòng" }));
  const rowOf = async (title: string) => opened((await roomsTable()).getAllByRole("button", { name: new RegExp(title) }).find((button) => !button.getAttribute("aria-label")?.startsWith("Khác"))!.closest("tr")!);

  it("reads the rooms in one table: name, people, who is online, how to join, whose it is, what is unread; mine and the public ones together", async () => {
    db.rooms = [
      room("garage", { title: "Garage sale", members: 5, visibility: "private", join_policy: "invite", me: { ...ME, role: "owner", unread: 3 } }),
      room("other", { title: "Other", me: null }),
    ];
    const lobby = await open();
    const table = await roomsTable();
    expect(table.getAllByRole("row")).toHaveLength(3); // the head, my room, and a public one I am not in
    const row = await rowOf("Garage sale");
    expect(row).toHaveTextContent("5/200");
    expect(row).toHaveTextContent("Riêng tư"); // its status: the owner lets people in
    expect(row).toHaveTextContent("🔒"); // private
    expect(row).toHaveTextContent("bạn"); // whose it is
    expect(within(row).getByText("3")).toBeInTheDocument(); // what is unread
    expect(within(await rowOf("Other")).queryByRole("checkbox")).not.toBeInTheDocument(); // not mine: nothing to delete
    expect(await rowOf("Other")).toHaveTextContent("Công khai");
    expect(within(await rowOf("Other")).getByRole("button", { name: "Tham gia" })).toBeInTheDocument(); // not in it yet: join it from the row
    expect(within(row).queryByRole("button", { name: "Tham gia" })).not.toBeInTheDocument();
  });

  it("searches the rooms by what is typed in the bar, mine and the public ones alike", async () => {
    db.rooms = [room("garage", { title: "Garage sale", me: null }), room("buyers", { title: "Home buyers", me: null })];
    await open();
    const user = userEvent.setup();
    await waitFor(async () => expect((await roomsTable()).getAllByRole("row")).toHaveLength(3));
    await user.type(roomsBar().getByRole("searchbox"), "buy{Enter}");
    await waitFor(() => expect(called("GET", /scope=public&q=buy/)).toHaveLength(1));
    await waitFor(async () => expect((await roomsTable()).getAllByRole("row")).toHaveLength(2));
    await user.click(screen.getByRole("button", { name: "Xóa tất cả" }));
    await user.type(roomsBar().getByRole("searchbox"), "zzz{Enter}");
    expect(await screen.findByText("Không có phòng nào khớp bộ lọc.")).toBeInTheDocument();
  });

  it("sorts the rows when the head of a column is pressed: ascending, descending, then as they came", async () => {
    db.rooms = [room("b", { title: "Beta", members: 9 }), room("a", { title: "Alpha", members: 30 }), room("c", { title: "Gamma", members: 2 })];
    await open("#room=none");
    const user = userEvent.setup();
    const names = async () => (await roomsTable()).getAllByRole("row").slice(1).map((row) => row.querySelectorAll("td")[1].querySelector("button")?.textContent);
    expect(await names()).toEqual(["Beta", "Alpha", "Gamma"]);
    await user.click((await roomsTable()).getByRole("button", { name: /Tên phòng/ }));
    expect(await names()).toEqual(["Alpha", "Beta", "Gamma"]);
    expect((await roomsTable()).getByRole("columnheader", { name: /Tên phòng/ })).toHaveAttribute("aria-sort", "ascending");
    await user.click((await roomsTable()).getByRole("button", { name: /Tên phòng/ }));
    expect(await names()).toEqual(["Gamma", "Beta", "Alpha"]);
    await user.click((await roomsTable()).getByRole("button", { name: /Thành viên/ })); // by the number of people: 2, 9, 30
    expect(await names()).toEqual(["Gamma", "Beta", "Alpha"]);
    await user.click((await roomsTable()).getByRole("button", { name: /Thành viên/ }));
    await user.click((await roomsTable()).getByRole("button", { name: /Thành viên/ })); // a third press: the order they came in
    expect(await names()).toEqual(["Beta", "Alpha", "Gamma"]);
  });

  it("reads them again when the lobby says rooms changed", async () => {
    db.rooms = [room("one")];
    const lobby = await open();
    await roomsTable();
    db.rooms.push(room("two"));
    lobby.frame({ type: "rooms", rooms: [], version: 1 });
    await waitFor(async () => expect((await roomsTable()).getAllByRole("row")).toHaveLength(3));
    lobby.drop(1013, "Too many lobby connections"); // the list keeps working: it is polled
    expect(await roomsTable()).toBeTruthy();
  });

  it("shows a request to write to me in the same table, and opens it to be answered", async () => {
    db.rooms = [
      room("g", { title: "General" }),
      room("dm-3-1", { kind: "dm", title: "carol & alice", visibility: "private", user_id: 3, me: { ...ME, status: "pending" } }),
    ];
    db.history["dm-3-1"] = [msg(1, "carol", "hi, we met at the market")];
    await open();
    const user = userEvent.setup();
    const row = await rowOf("carol & alice");
    expect(row).toHaveTextContent(/đang chờ duyệt/i); // marked as waiting for my answer
    expect(within(row).queryByRole("checkbox")).not.toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: /^(?!Khác).*carol & alice/ }));
    const request = await screen.findByRole("region", { name: "Yêu cầu nhắn tin" });
    expect(within(request).getByText(/carol muốn nhắn tin cho bạn/)).toBeInTheDocument();
    expect(await within(request).findByText("hi, we met at the market")).toBeInTheDocument();
  });


  it("gives the owner Edit and the others Leave, and everybody the link of the room", async () => {
    db.rooms = [room("mine", { title: "Mine", me: { ...ME, role: "owner" } }), room("his", { title: "His" })];
    await open();
    const mine = await rowOf("Mine");
    const his = await rowOf("His");
    expect(within(mine).getByRole("button", { name: "Sửa" })).toBeInTheDocument();
    expect(within(mine).getByRole("button", { name: "Rời" })).toBeInTheDocument(); // the owner leaves too, after handing the room over
    expect(within(his).queryByRole("button", { name: "Sửa" })).not.toBeInTheDocument();
    expect(within(his).getByRole("button", { name: "Rời" })).toBeInTheDocument();
    expect(within(mine).getByRole("checkbox")).toBeInTheDocument(); // only the owner's rooms can be picked, to be deleted
    expect(within(his).queryByRole("checkbox")).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(within(his).getByRole("button", { name: "Liên kết" }));
    expect(await navigator.clipboard.readText()).toBe(`${window.location.origin}/chat#room=his`);
  });

  it("filters the rooms with column:value in the same box (kind:dm, status:private), shown as chips, with no other filter box", async () => {
    db.rooms = [room("g", { title: "General" }), room("dm-1-2", { kind: "dm", title: "bob", visibility: "private", join_policy: "invite", capacity: 2 })];
    await open();
    const user = userEvent.setup();
    await waitFor(async () => expect((await roomsTable()).getAllByRole("row")).toHaveLength(3));
    expect(roomsBar().queryByRole("combobox")).not.toBeInTheDocument(); // the Rooms / Direct messages choice is a term now
    expect(screen.getByPlaceholderText(/Từ khóa|Words or/)).toBeInTheDocument();
    await user.type(roomsBar().getByRole("searchbox"), "kind:dm{Enter}");
    await waitFor(async () => expect((await roomsTable()).getAllByRole("row")).toHaveLength(2));
    expect((await roomsTable()).getByRole("button", { name: /^(?!Khác).*bob/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /kind:dm/ })).toBeInTheDocument();
    expect(called("GET", /q=kind/)).toHaveLength(0); // a column term filters here: it is not a word for the server
    await user.click(screen.getByRole("button", { name: "Xóa tất cả" }));
    await user.type(roomsBar().getByRole("searchbox"), "status:public{Enter}");
    await waitFor(async () => expect((await roomsTable()).getAllByRole("row")).toHaveLength(2));
    expect((await roomsTable()).getByRole("button", { name: "General" })).toBeInTheDocument();
  });

  it("has the bar of the Table pane: Search, Columns, rows per page, and a line to select all, and no saved views", async () => {
    db.rooms = [room("mine", { title: "Mine", me: { ...ME, role: "owner" } }), room("his", { title: "His" })];
    await open();
    const user = userEvent.setup();
    await roomsTable();
    const panel = within(screen.getByRole("complementary", { name: "Phòng chat" }));
    expect(roomsBar().queryByRole("button", { name: "Tìm" })).not.toBeInTheDocument(); // Enter searches
    expect(panel.queryByRole("button", { name: /Lưu view|Save view/ })).not.toBeInTheDocument();
    expect(panel.getByRole("combobox", { name: "Số dòng mỗi trang" })).toHaveValue("20");
    expect(panel.getByRole("checkbox", { name: "Chọn tất cả" })).toBeInTheDocument();
    expect((await roomsTable()).queryByRole("checkbox", { name: "Chọn tất cả" })).not.toBeInTheDocument(); // not in the head: the line over the table has it
    expect((await roomsTable()).getByRole("columnheader", { name: /Chủ phòng/ })).toBeInTheDocument();
    await user.click(roomsBar().getByRole("button", { name: "Cột" }));
    await user.click(within(screen.getByRole("group", { name: "Cột" })).getByRole("checkbox", { name: "Chủ phòng" }));
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Danh sách phòng" })).queryByRole("columnheader", { name: /Chủ phòng/ })).not.toBeInTheDocument());
  });

  it("pages the rooms by the rows a page has", async () => {
    db.rooms = Array.from({ length: 25 }, (_, n) => room(`r${n}`, { title: `Room ${String(n).padStart(2, "0")}`, me: null }));
    await open();
    const user = userEvent.setup();
    const panel = within(screen.getByRole("complementary", { name: "Phòng chat" }));
    await waitFor(async () => expect((await roomsTable()).getAllByRole("row")).toHaveLength(21)); // the head and 20
    await user.click(panel.getByRole("button", { name: "Sau" }));
    await waitFor(async () => expect((await roomsTable()).getAllByRole("row")).toHaveLength(6)); // the head and the last 5
  });

  it("shows the picture of a room by its name, or the first letter of the name when it has none, and sets it from Create and from Edit", async () => {
    db.rooms = [
      room("pics", { title: "Pictures", avatar: "https://img.example/p.png", me: { ...ME, role: "owner" } }),
      room("plain", { title: "Plain", avatar: "" }),
    ];
    await open();
    const user = userEvent.setup();
    const pictured = await rowOf("Pictures");
    expect(pictured.querySelector("img")).toHaveAttribute("src", "https://img.example/p.png");
    const plain = await rowOf("Plain");
    expect(plain.querySelector("img")).toBeNull();
    expect(plain).toHaveTextContent("P"); // the first letter stands for the picture
    await user.click(within(pictured).getByRole("button", { name: "Sửa" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Sửa dòng" }));
    expect(dialog.getByLabelText("Avatar")).toHaveValue("https://img.example/p.png");
    await user.clear(dialog.getByLabelText("Avatar"));
    await user.type(dialog.getByLabelText("Avatar"), "/media/new.png");
    await user.click(dialog.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/pics$/)[0].body).toEqual({ avatar: "/media/new.png" }));
    await user.click(roomsBar().getByRole("button", { name: "Mở phòng" }));
    const form = await screen.findByRole("form", { name: "Mở phòng" });
    await user.type(within(form).getByLabelText("Tên phòng"), "With face");
    expect(within(form).getByLabelText("Tải ảnh lên")).toHaveAttribute("type", "file"); // a picture is uploaded from a file
    await user.click(within(form).getByRole("button", { name: "Mở phòng" }));
    await waitFor(() => expect(called("POST", /^\/rooms$/)[0].body).toMatchObject({ title: "With face" }));
  });

  it("lets the person who started a chat of two close it and reopen it, and leave it", async () => {
    db.rooms = [room("dm-1-2", { kind: "dm", title: "bob", visibility: "private", join_policy: "invite", capacity: 2, me: { ...ME, role: "owner" } })];
    await open();
    const user = userEvent.setup();
    const row = await rowOf("bob");
    expect(within(row).queryByRole("button", { name: "Sửa" })).not.toBeInTheDocument(); // a chat of two has nothing to edit
    expect(within(row).getByRole("button", { name: "Rời" })).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Đóng" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/dm-1-2$/)[0].body).toEqual({ state: "closed" }));
    await user.click(await within(await rowOf("bob")).findByRole("button", { name: "Mở lại" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/dm-1-2$/)[1].body).toEqual({ state: "open" }));
  });

  it("lets the owner close or reopen a room from its row, and nobody else", async () => {
    db.rooms = [room("mine", { title: "Mine", join_policy: "open", me: { ...ME, role: "owner" } }), room("his", { title: "His" })];
    await open();
    const user = userEvent.setup();
    expect(within(await rowOf("His")).queryByRole("button", { name: "Đóng" })).not.toBeInTheDocument();
    await user.click(within(await rowOf("Mine")).getByRole("button", { name: "Đóng" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/mine$/)[0].body).toEqual({ state: "closed" }));
    await user.click(await within(await rowOf("Mine")).findByRole("button", { name: "Mở lại" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/mine$/)[1].body).toEqual({ state: "open" }));
  });

  it("makes a room from the form of Create, with every option, and enters it", async () => {
    await open();
    const user = userEvent.setup();
    await user.click(roomsBar().getByRole("button", { name: "Mở phòng" }));
    const form = await screen.findByRole("form", { name: "Mở phòng" });
    await user.type(within(form).getByLabelText("Tên phòng"), "Lamps for sale");
    await user.selectOptions(within(form).getByLabelText("Trạng thái"), "approval");
    await user.click(within(form).getByRole("button", { name: "Mở phòng" }));
    await waitFor(() => expect(called("POST", /^\/rooms$/)[0]?.body).toMatchObject({ title: "Lamps for sale", join_policy: "approval", visibility: "public" }));
    await enter("lamps-for-sale");
    expect(screen.getByRole("heading", { name: "Lamps for sale" })).toBeInTheDocument();
  });

  it("changes a room from the Edit form of the Table pane, only what the owner changed (the status too), and only for the owner", async () => {
    db.rooms = [room("mine", { title: "Mine", join_policy: "open", me: { ...ME, role: "owner" } }), room("his", { title: "His" })];
    await open();
    const user = userEvent.setup();
    expect(within(await rowOf("His")).queryByRole("button", { name: "Sửa" })).not.toBeInTheDocument();
    await user.click(within(await rowOf("Mine")).getByRole("button", { name: "Sửa" }));
    let dialog = within(await screen.findByRole("dialog", { name: "Sửa dòng" }));
    expect(dialog.getByLabelText("Title")).toHaveValue("Mine");
    expect(dialog.getByLabelText(/^Status$/)).toHaveValue("public");
    expect(dialog.getByLabelText(/^Slug/)).toBeDisabled(); // the address is chosen when the room is made, never after
    await user.click(dialog.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Sửa dòng" })).not.toBeInTheDocument()); // nothing changed: nothing sent
    expect(called("PATCH", /^\/rooms\/mine$/)).toHaveLength(0);
    await user.click(within(await rowOf("Mine")).getByRole("button", { name: "Sửa" }));
    dialog = within(await screen.findByRole("dialog", { name: "Sửa dòng" }));
    await user.clear(dialog.getByLabelText("Title"));
    await user.type(dialog.getByLabelText("Title"), "Renamed");
    await user.clear(dialog.getByLabelText(/^Status$/));
    await user.type(dialog.getByLabelText(/^Status$/), "private");
    await user.click(dialog.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/mine$/)[0].body).toEqual({ title: "Renamed", join_policy: "approval" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Sửa dòng" })).not.toBeInTheDocument());
  });

  it("says why an Edit of a room is refused, in the form", async () => {
    db.rooms = [room("mine", { title: "Mine", me: { ...ME, role: "owner" } })];
    await open();
    const user = userEvent.setup();
    await user.click(within(await rowOf("Mine")).getByRole("button", { name: "Sửa" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Sửa dòng" }));
    await user.clear(dialog.getByLabelText(/^Status$/));
    await user.type(dialog.getByLabelText(/^Status$/), "secret");
    await user.click(dialog.getByRole("button", { name: "Lưu" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent("Trạng thái phải là public");
    expect(called("PATCH", /^\/rooms\/mine$/)).toHaveLength(0);
  });

  it("deletes the rooms that are picked, after asking, and only the owner's can be picked", async () => {
    db.rooms = [room("g", { title: "General", me: { ...ME, role: "owner" } }), room("h", { title: "Other", me: { ...ME, role: "owner" } }), room("x", { title: "His" })];
    await open("#room=none");
    const user = userEvent.setup();
    expect(roomsBar().queryByRole("button", { name: "Xóa" })).not.toBeInTheDocument(); // nothing picked: nothing to do
    await roomsTable();
    await user.click(within(screen.getByRole("complementary", { name: "Phòng chat" })).getByRole("checkbox", { name: "Chọn tất cả" })); // the line over the table, as in the Table pane
    expect(roomsBar().getByText("Đã chọn 2")).toBeInTheDocument(); // the two of the owner, not His
    await user.click(roomsBar().getByRole("button", { name: "Xóa" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Xóa 2 phòng?");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(called("DELETE", /^\/rooms\/(g|h)$/)).toHaveLength(2));
    expect(called("DELETE", /^\/rooms\/x$/)).toHaveLength(0);
  });

  it("leaves a room of another owner from its row, after asking", async () => {
    db.rooms = [room("g", { title: "General" })];
    await open("#room=none");
    const user = userEvent.setup();
    await user.click(within(await rowOf("General")).getByRole("button", { name: "Rời" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent('Rời phòng "General"?');
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Rời phòng" }));
    await waitFor(() => expect(called("POST", /g\/leave$/)).toHaveLength(1));
  });

  it("brings a room back that its owner deleted", async () => {
    db.rooms = [room("g", { title: "General", state: "deleted", me: { ...ME, role: "owner" } })];
    await open("#room=g");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Khôi phục phòng" }));
    await waitFor(() => expect(called("PATCH", /^\/rooms\/g$/)[0].body).toEqual({ state: "open" }));
  });

  it("removes a deleted room for good, after asking", async () => {
    db.rooms = [room("g", { title: "General", state: "deleted", me: { ...ME, role: "owner" } })];
    await open("#room=g");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Xóa vĩnh viễn" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Không thể hoàn tác");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Xóa vĩnh viễn" }));
    await waitFor(() => expect(called("DELETE", /^\/rooms\/g\?permanent=true$/)).toHaveLength(1));
  });

  it("shows how many places a room has, as taken/capacity", async () => {
    db.rooms = [room("club", { title: "Club", members: 12, capacity: 50 })];
    await open();
    expect(await rowOf("Club")).toHaveTextContent("12/50");
  });
});

describe("Messages: write one (Send), read them all, change one (the sender), delete the ones picked (the sender's)", () => {
  async function inRoomAs(extra: Partial<Room> = {}, history: unknown[] = []) {
    db.rooms = [room("g", { title: "General", ...extra })];
    db.history.g = history;
    await open("#room=g");
    const socket = await enter("g");
    return { user: userEvent.setup(), socket };
  }
  const bar = () => within(screen.getByRole("toolbar", { name: "Tin nhắn" }));
  const rowOf = async (text: string) => opened((await screen.findByText(text)).closest("tr")!);

  it("reads them in one table: when, who, what; takes the live ones; tells how the connection is", async () => {
    const { socket } = await inRoomAs({}, [msg(1, "bob", "earlier")]);
    const earlier = await rowOf("earlier");
    expect(earlier).toHaveTextContent("bob");
    expect(window.location.hash).toBe("#room=g");
    expect(screen.queryByText("Đã kết nối")).not.toBeInTheDocument(); // nothing to say while all is well: only a lost connection is said
    socket.frame(msg(2, "carol", "live one"));
    expect((await rowOf("live one"))).toHaveTextContent("carol");
    socket.frame({ type: "presence", members: [{ userId: 2, username: "bob" }], total: 3 });
    expect(screen.getByRole("heading", { name: "General" }).closest("div")).toHaveTextContent("3 trực tuyến");
    socket.frame({ type: "system", event: "join", username: "dave", at: "2026-01-01T00:00:10Z" });
    expect(await rowOf("dave đã trực tuyến")).toHaveTextContent("system"); // said by system
    socket.frame({ type: "error", error: "You are muted" });
    expect(screen.getByRole("alert")).toHaveTextContent("Bạn đang bị tắt tiếng trong phòng này.");
  });

  it("answers a message and sends which one", async () => {
    const { user, socket } = await inRoomAs({}, [msg(1, "bob", "where?")]);
    await user.click(within(await rowOf("where?")).getByRole("button", { name: "Trả lời" }));
    expect(screen.getByText(/Đang trả lời bob/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Tin nhắn", { selector: "textarea" }), "here{Enter}");
    expect(JSON.parse(socket.sent[0])).toEqual({ content: "here", reply_to: 1 });
    socket.frame(msg(2, "alice", "here", { reply_to_id: 1 }));
    expect((await rowOf("here"))).toHaveTextContent("bob: where?");
  });

  it("lets only the sender edit a message, and shows it as edited", async () => {
    const { user, socket } = await inRoomAs({}, [msg(1, "alice", "helo"), msg(2, "bob", "his")]);
    const mine = await rowOf("helo");
    expect(within(await rowOf("his")).queryByRole("button", { name: "Sửa" })).not.toBeInTheDocument();
    await user.click(within(mine).getByRole("button", { name: "Sửa" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Sửa dòng" }));
    const box = dialog.getByLabelText("Content");
    await user.clear(box);
    await user.type(box, "hello");
    await user.click(dialog.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(called("PATCH", /messages\/1$/)[0].body).toEqual({ content: "hello" }));
    socket.frame({ type: "edited", id: 1, content: "hello", edited_at: "2026-01-01T00:05:00Z" });
    expect(await rowOf("hello")).toHaveTextContent("(đã sửa)");
  });

  it("lets any member pin a message, and only the sender (not the owner of the room) pick their own", async () => {
    const { user } = await inRoomAs({}, [msg(1, "bob", "his"), msg(2, "alice", "mine")]);
    await user.click(within(await rowOf("his")).getByRole("button", { name: "Ghim" }));
    await waitFor(() => expect(called("PUT", /messages\/1\/pin$/)).toHaveLength(1));
    await user.click(within(await rowOf("mine")).getByRole("button", { name: "Ghim" }));
    await waitFor(() => expect(called("PUT", /messages\/2\/pin$/)).toHaveLength(1));
    expect(within(await rowOf("his")).queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("lets the owner of the room pick and remove the message of anyone", async () => {
    const { user } = await inRoomAs({ me: { ...ME, role: "owner" } }, [msg(1, "bob", "his"), msg(2, "alice", "mine")]);
    await user.click(within(await rowOf("his")).getByRole("checkbox"));
    await user.click(bar().getByRole("button", { name: "Xóa" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(called("DELETE", /messages\/1$/)).toHaveLength(1));
  });

  it("reports the message of someone else with a reason and takes the report back, and has no report for my own", async () => {
    const { user } = await inRoomAs({}, [msg(1, "bob", "his"), msg(2, "alice", "mine")]);
    expect(within(await rowOf("mine")).queryByRole("button", { name: "Báo cáo" })).not.toBeInTheDocument();
    await user.click(within(await rowOf("his")).getByRole("button", { name: "Báo cáo" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Báo cáo" }));
    await user.selectOptions(dialog.getByLabelText("Lý do"), "abuse");
    await user.click(dialog.getByRole("button", { name: "Gửi báo cáo" }));
    await waitFor(() => expect(called("POST", /^\/reports$/)[0].body).toEqual({ target_type: "message", target_id: "1", reason: "abuse", details: "" }));
    await user.click(await within(await rowOf("his")).findByRole("button", { name: "Hủy báo cáo" }));
    await waitFor(() => expect(called("DELETE", /^\/reports\/70$/)).toHaveLength(1));
    expect(await within(await rowOf("his")).findByRole("button", { name: "Báo cáo" })).toBeInTheDocument();
  });

  it("removes a message from its row after asking: mine, and (for the owner of the room) anyone's", async () => {
    const { user } = await inRoomAs({}, [msg(1, "bob", "his"), msg(2, "alice", "mine")]);
    expect(within(await rowOf("his")).queryByRole("button", { name: "Xóa" })).not.toBeInTheDocument(); // not mine, and I do not own the room
    await user.click(within(await rowOf("mine")).getByRole("button", { name: "Xóa" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Xóa 1 tin nhắn?");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(called("DELETE", /messages\/2$/)).toHaveLength(1));
  });

  it("lets only the sender pick a message, and deletes the ones picked after asking", async () => {
    const { user, socket } = await inRoomAs({}, [msg(1, "alice", "mine"), msg(2, "bob", "his"), msg(3, "alice", "mine too")]);
    const mine = await rowOf("mine");
    expect(within(await rowOf("his")).queryByRole("checkbox")).not.toBeInTheDocument(); // not the sender: no box
    expect(bar().queryByRole("button", { name: "Xóa" })).not.toBeInTheDocument(); // nothing picked yet
    await user.click(within(mine).getByRole("checkbox"));
    expect(bar().getByText("Đã chọn 1")).toBeInTheDocument();
    await user.click(within(screen.getByRole("log", { name: "Tin nhắn" })).getByRole("checkbox", { name: "Chọn tất cả" })); // every one of mine: two
    expect(bar().getByText("Đã chọn 2")).toBeInTheDocument();
    await user.click(bar().getByRole("button", { name: "Xóa" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Xóa 2 tin nhắn?");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(called("DELETE", /messages\/(1|3)$/)).toHaveLength(2));
    expect(called("DELETE", /messages\/2$/)).toHaveLength(0);
    socket.frame({ type: "deleted", id: 2 });
    expect(screen.queryByText("his")).not.toBeInTheDocument();
  });

  it("sorts the messages by the head of a column, and goes back to the order of the conversation on the third press", async () => {
    const { user } = await inRoomAs({}, [msg(1, "carol", "one"), msg(2, "alice", "two"), msg(3, "bob", "three")]);
    await rowOf("one");
    const senders = () => within(screen.getByRole("table", { name: "Tin nhắn" })).getAllByRole("row").slice(1).filter((row) => row.querySelectorAll("td").length > 1).map((row) => row.querySelectorAll("td")[2].textContent);
    expect(senders()).toEqual(["carol", "alice", "bob"]);
    const head = () => within(screen.getByRole("table", { name: "Tin nhắn" })).getByRole("button", { name: /Người gửi/ });
    await user.click(head());
    expect(senders()).toEqual(["alice", "bob", "carol"]);
    await user.click(head());
    await user.click(head());
    expect(senders()).toEqual(["carol", "alice", "bob"]);
  });

  it("shows the lines about the room as said by system, and nobody picks them", async () => {
    await inRoomAs({ me: { ...ME, role: "owner" } }, [msg(1, "alice", "hello"), msg(2, "system", "joined:bob", { kind: "system", user_id: -1 }), msg(3, "system", "kicked:carol", { kind: "system", user_id: -1 })]);
    const joined = await rowOf("bob đã tham gia phòng");
    expect(joined).toHaveTextContent("system");
    expect(await rowOf("carol đã bị mời ra khỏi phòng")).toHaveTextContent("system");
    expect(within(joined).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(joined).queryByRole("button")).not.toBeInTheDocument(); // not to answer, not to change
  });

  it("shows what is pinned, and takes it off when the server says it is not", async () => {
    const { socket } = await inRoomAs({}, [msg(1, "bob", "rules apply")]);
    await rowOf("rules apply");
    socket.frame({ type: "pinned", id: 1, pinned: true });
    expect(screen.getByRole("note", { name: "Tin đã ghim" })).toHaveTextContent("bob: rules apply");
    socket.frame({ type: "pinned", id: 1, pinned: false });
    expect(screen.queryByRole("note", { name: "Tin đã ghim" })).not.toBeInTheDocument();
  });

  it("draws a line before the first message I had not read", async () => {
    await inRoomAs({ me: { ...ME, last_read: 2 } }, [msg(1, "bob", "old one"), msg(2, "bob", "read one"), msg(3, "bob", "new one"), msg(4, "bob", "newer one")]);
    const line = (await screen.findByText("Tin chưa đọc")).closest("tr")!;
    expect(line.nextElementSibling).toHaveTextContent("new one");
    expect(screen.getAllByText("Tin chưa đọc")).toHaveLength(1);
  });
});

describe("Members: add one (a name, or virtual people), read them all, change the ones picked (the owner), write to one", () => {
  async function asOwner(extra: Partial<Room> = {}) {
    db.rooms = [room("g", { title: "General", me: { ...ME, role: "owner" }, ...extra })];
    db.members.g = [
      member(1, "alice", { role: "owner" }),
      member(2, "bob", { online: true }),
      member(3, "carol"),
      member(4, "dave", { status: "pending" }),
      member(5, "v1", { virtual: true }),
      member(6, "v2", { virtual: true }),
    ];
    await open("#room=g");
    await enter("g");
    return userEvent.setup();
  }
  const bar = () => within(screen.getByRole("toolbar", { name: "Thành viên" }));
  const table = async () => within(await screen.findByRole("table", { name: "Thành viên" }));
  const rowOf = async (name: string) => opened((await table()).getByText(new RegExp(`^${name}`)).closest("tr")!);

  it("reads them in one table: who, role, a person or a virtual one, in the room or waiting", async () => {
    await asOwner();
    expect(await rowOf("alice")).toHaveTextContent("(bạn)");
    expect(await rowOf("alice")).toHaveTextContent(/chủ phòng/i);
    expect(await rowOf("bob")).toHaveTextContent(/thành viên/i);
    expect(await rowOf("carol")).toHaveTextContent(/thành viên/i);
    expect(await rowOf("dave")).toHaveTextContent(/đang chờ duyệt/i);
    expect(await rowOf("v1")).toHaveTextContent(/ảo/i);
    expect(within(await rowOf("bob")).getByRole("img", { name: "Đang trực tuyến" })).toBeInTheDocument();
    expect(within(await rowOf("v1")).getByRole("img", { name: /tuyến/i })).toBeInTheDocument(); // a dot for them too, like anybody
  });

  const stranger = (extra: Record<string, unknown> = {}) => ({ user_id: 2, username: "bob", display_name: "", headline: "", region: "", avatar: "", summary: null, relation: "none", blocked: false, virtual: false, age: null, interests: [], companion: false, ...extra });

  it("offers Add friend, Block and Report on a virtual person in the row, like on anybody", async () => {
    db.person = stranger({ user_id: 5, username: "v1", virtual: true });
    await asOwner();
    const row = within(await rowOf("v1"));
    expect(await row.findByRole("button", { name: "Chặn" })).toBeInTheDocument();
    expect(row.getByRole("button", { name: "Báo cáo" })).toBeInTheDocument();
    expect(row.getByRole("button", { name: "Bạn bè" })).toBeInTheDocument(); // a virtual person is a friend as soon as they are asked
  });

  it("links a member to the profile and puts every action in the row, for the people other than me", async () => {
    await asOwner();
    expect(within(await rowOf("bob")).getByRole("link", { name: "bob" })).toHaveAttribute("href", "/chat/people/bob");
    expect(within(await rowOf("bob")).getByRole("link", { name: "Hồ sơ" })).toHaveAttribute("href", "/chat/people/bob");
    expect(within(await rowOf("bob")).queryByRole("button", { name: /Hành động/ })).not.toBeInTheDocument(); // no menu to open
    expect(within(await rowOf("alice")).queryByRole("link", { name: "Hồ sơ" })).not.toBeInTheDocument();
  });

  it("asks to be friends, reports and blocks from the row of a member", async () => {
    db.person = stranger();
    await asOwner();
    const user = userEvent.setup();
    const row = within(await rowOf("bob"));
    await user.click(await row.findByRole("button", { name: "Bạn bè" }));
    await waitFor(() => expect(called("POST", /^\/friends\/2$/)).toHaveLength(1));
    await user.click(row.getByRole("button", { name: "Báo cáo" }));
    const form = screen.getByRole("dialog", { name: "Báo cáo" });
    await user.selectOptions(within(form).getByLabelText("Lý do"), "spam");
    await user.click(within(form).getByRole("button", { name: "Gửi báo cáo" }));
    await waitFor(() => expect(called("POST", /^\/reports$/)[0].body).toEqual({ target_type: "user", target_id: "2", reason: "spam", details: "" }));
    await user.click(within(await rowOf("bob")).getByRole("button", { name: "Chặn" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Chặn" }));
    await waitFor(() => expect(called("POST", /^\/blocks\/2$/)).toHaveLength(1));
  });

  it("offers to unfriend a friend from the row", async () => {
    db.person = stranger({ relation: "friends" });
    await asOwner();
    const user = userEvent.setup();
    await user.click(await within(await rowOf("bob")).findByRole("button", { name: "Hủy kết bạn" }));
    await waitFor(() => expect(called("DELETE", /^\/friends\/2$/)).toHaveLength(1));
  });

  it("moves a person between online and offline as the room says they come and go", async () => {
    await asOwner();
    const socket = FakeSocket.last("/ws/g");
    const bob = await rowOf("bob");
    expect(within(bob).getByRole("img", { name: "Đang trực tuyến" })).toBeInTheDocument();
    socket.frame({ type: "presence", members: [{ userId: 1, username: "alice" }], total: 1 }); // bob went away
    await waitFor(() => expect(within(bob).getByRole("img", { name: "Ngoại tuyến" })).toBeInTheDocument());
  });

  it("shows the picture and the name of a person next to the user name, in a column of their own", async () => {
    db.rooms = [room("g", { title: "General", me: { ...ME, role: "owner" } })];
    db.members.g = [member(1, "alice", { role: "owner" }), member(2, "bob", { name: "Bob Tran", avatar: "https://img.example/b.png" }), member(3, "carol")];
    await open("#room=g");
    await enter("g");
    const user = userEvent.setup();
    expect((await table()).queryByRole("columnheader", { name: /Họ tên/ })).not.toBeInTheDocument(); // starts hidden
    await user.click(bar().getByRole("button", { name: "Cột" }));
    await user.click(within(screen.getByRole("group", { name: "Cột" })).getByRole("checkbox", { name: "Họ tên" }));
    const bob = await rowOf("bob");
    expect(bob.querySelector("img")).toHaveAttribute("src", "https://img.example/b.png");
    expect(bob).toHaveTextContent("Bob Tran");
    expect(await rowOf("carol")).toHaveTextContent("—"); // a person who shows no name
    expect((await table()).getByRole("columnheader", { name: /Họ tên/ })).toBeInTheDocument();
  });

  it("filters the people with column:value from the same box (role:owner, status:banned) and has no view box", async () => {
    const user = await asOwner();
    await rowOf("bob");
    expect(bar().queryByRole("combobox")).not.toBeInTheDocument();
    await user.type(bar().getByRole("searchbox"), "role:owner{Enter}");
    expect(await rowOf("alice")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("bob")).not.toBeInTheDocument());
  });

  it("searches the members by name, from the same bar", async () => {
    const user = await asOwner();
    await rowOf("bob");
    await user.type(bar().getByRole("searchbox"), "car{Enter}");
    await waitFor(() => expect(called("GET", /members\?q=car$/)).toHaveLength(1));
    expect(await rowOf("carol")).toBeInTheDocument();
    await waitFor(() => expect((screen.queryByText("bob"))).not.toBeInTheDocument());
  });

  it("adds a person by name, or some virtual people at random, from Create", async () => {
    const user = await asOwner();
    await user.click(bar().getByRole("button", { name: "Mời người" }));
    await user.type(screen.getByRole("textbox", { name: "Tên đăng nhập" }), "gina");
    await user.click(screen.getByRole("button", { name: "Thêm" }));
    await waitFor(() => expect(called("POST", /members$/)[0].body).toEqual({ username: "gina" }));
    expect(await screen.findByRole("button", { name: "Thêm người ảo" })).toBeInTheDocument();
  });

  it("gives the owner a box on the people who can be changed, and nobody else", async () => {
    await asOwner();
    expect(within(await rowOf("bob")).getByRole("checkbox")).toBeInTheDocument();
    expect(within(await rowOf("alice")).queryByRole("checkbox")).not.toBeInTheDocument(); // yourself and the owner are not for picking
  });

  it("approves the ones who wait, only those, with one button", async () => {
    const user = await asOwner();
    expect(bar().queryByRole("button", { name: "Duyệt" })).not.toBeInTheDocument(); // nothing picked
    await user.click(within(await rowOf("bob")).getByRole("checkbox"));
    expect(bar().queryByRole("button", { name: "Duyệt" })).not.toBeInTheDocument(); // nobody picked waits: no Approve
    await user.click(within(await rowOf("dave")).getByRole("checkbox"));
    expect(bar().getByRole("button", { name: "Duyệt" })).toBeInTheDocument();
    await user.click(bar().getByRole("button", { name: "Duyệt" }));
    await waitFor(() => expect(called("PATCH", /members\/4$/)[0].body).toEqual({ status: "joined" }));
    expect(called("PATCH", /members\/2$/)).toHaveLength(0);
  });

  it("kicks the ones picked after asking, and bans them after asking, virtual or not", async () => {
    const user = await asOwner();
    await user.click(within(await rowOf("v1")).getByRole("checkbox"));
    await user.click(within(await rowOf("v2")).getByRole("checkbox"));
    expect(bar().getByText("Đã chọn 2")).toBeInTheDocument();
    await user.click(bar().getByRole("button", { name: "Mời ra" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Mời 2 người ra khỏi phòng?");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Mời ra" }));
    await waitFor(() => expect(called("DELETE", /members\/(5|6)$/)).toHaveLength(2));
    await user.click(within(await rowOf("bob")).getByRole("checkbox"));
    await user.click(bar().getByRole("button", { name: "Cấm" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Cấm 1 người khỏi phòng này?");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Cấm" }));
    await waitFor(() => expect(called("PATCH", /members\/2$/)[0].body).toEqual({ status: "banned" }));
  });

  it("mutes the people picked and lifts it, and declines the ones who wait", async () => {
    const user = await asOwner();
    expect(bar().queryByRole("combobox", { name: "Thời gian tắt tiếng" })).not.toBeInTheDocument(); // a mute is on or off
    await user.click(within(await rowOf("bob")).getByRole("checkbox"));
    await user.click(bar().getByRole("button", { name: "Tắt tiếng" }));
    await waitFor(() => expect(called("PATCH", /members\/2$/)[0].body).toEqual({ muted: true }));
    expect(await screen.findByText("Bị tắt tiếng")).toBeInTheDocument();
    await user.click(within(await rowOf("bob")).getByRole("checkbox"));
    await user.click(bar().getByRole("button", { name: "Bật tiếng" }));
    await waitFor(() => expect(called("PATCH", /members\/2$/)[1].body).toEqual({ muted: false }));
    await user.click(within(await rowOf("dave")).getByRole("checkbox"));
    await user.click(bar().getByRole("button", { name: "Từ chối" }));
    await waitFor(() => expect(called("DELETE", /members\/4$/)).toHaveLength(1));
  });

  it("changes a member from the Edit form: the mute, and the role (handing the room over)", async () => {
    const user = await asOwner();
    expect(within(await rowOf("alice")).queryByRole("button", { name: /^Sửa/ })).not.toBeInTheDocument();
    await user.click(within(await rowOf("bob")).getByRole("button", { name: "Sửa bob" }));
    let dialog = within(await screen.findByRole("dialog", { name: "Sửa dòng" }));
    expect(dialog.getByLabelText("Role")).toHaveValue("member");
    await user.click(dialog.getByRole("checkbox", { name: "Muted" }));
    await user.click(dialog.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(called("PATCH", /members\/2$/)[0].body).toEqual({ muted: true }));
    await user.click(within(await rowOf("bob")).getByRole("button", { name: "Sửa bob" }));
    dialog = within(await screen.findByRole("dialog", { name: "Sửa dòng" }));
    await user.clear(dialog.getByLabelText("Role"));
    await user.type(dialog.getByLabelText("Role"), "owner");
    await user.click(dialog.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(called("POST", /\/transfer$/)[0].body).toEqual({ user_id: 2 }));
  });

  it("keeps Invite in a closed room (a person by name), but not the virtual people, who need an open one", async () => {
    const user = await asOwner({ state: "closed" });
    await user.click(bar().getByRole("button", { name: "Mời người" }));
    expect(screen.getByRole("textbox", { name: "Tên đăng nhập" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Thêm người ảo" })).not.toBeInTheDocument();
  });

  it("lets a member who is not the owner invite a person by name", async () => {
    db.rooms = [room("g", { title: "General" })];
    db.members.g = [member(1, "alice"), member(2, "bob")];
    await open("#room=g");
    await enter("g");
    const user = userEvent.setup();
    await user.click(bar().getByRole("button", { name: "Mời người" }));
    await user.type(screen.getByRole("textbox", { name: "Tên đăng nhập" }), "gina");
    await user.click(screen.getByRole("button", { name: "Thêm" }));
    await waitFor(() => expect(called("POST", /members$/)[0].body).toEqual({ username: "gina" }));
  });

  it("writes to one person: a private chat opens", async () => {
    db.rooms = [room("g", { title: "General" })];
    db.members.g = [member(1, "alice"), member(2, "bob")];
    await open("#room=g");
    await enter("g");
    const user = userEvent.setup();
    expect(within(await rowOf("alice")).queryByRole("button", { name: "Nhắn" })).not.toBeInTheDocument(); // not to yourself
    expect(within(await rowOf("bob")).queryByRole("checkbox")).not.toBeInTheDocument(); // not the owner: nothing to change
    await user.click(within(await rowOf("bob")).getByRole("button", { name: "Nhắn" }));
    await waitFor(() => expect(called("POST", /^\/dm$/)[0].body).toEqual({ user_id: 2 }));
    await enter("dm-1-2");
    expect(await screen.findByRole("heading", { name: /alice & bob/ })).toBeInTheDocument();
  });

  it("lists who left, was sent away or banned, and brings them back", async () => {
    const user = await asOwner();
    db.members.g.push(member(7, "erin", { status: "kicked" }), member(8, "frank", { status: "banned" }), member(9, "gus", { status: "left" }));
    const ask = async (term: string) => {
      const clear = screen.queryByRole("button", { name: "Xóa tất cả" });
      if (clear) await user.click(clear);
      await user.type(bar().getByRole("searchbox"), `${term}{Enter}`);
    };
    await ask("status:kicked");
    await user.click(within(await rowOf("erin")).getByRole("checkbox"));
    await user.click(bar().getByRole("button", { name: "Thêm lại" }));
    await waitFor(() => expect(called("POST", /members$/)[0].body).toEqual({ user_id: 7 }));
    await ask("status:banned");
    await user.click(within(await rowOf("frank")).getByRole("checkbox"));
    await user.click(bar().getByRole("button", { name: "Bỏ cấm" }));
    await waitFor(() => expect(called("PATCH", /members\/8$/)[0].body).toEqual({ status: "joined" }));
    await ask("status:left");
    expect(await rowOf("gus")).toBeInTheDocument();
  });

  it("sorts the people by the head of a column, like every table", async () => {
    const user = await asOwner();
    const names = async () => (await table()).getAllByRole("row").slice(1).map((row) => row.querySelectorAll("td")[1].querySelector("a")?.textContent);
    await rowOf("bob");
    await user.click((await table()).getByRole("button", { name: /^Tên đăng nhập/ }));
    expect(await names()).toEqual(["alice", "bob", "carol", "dave", "v1", "v2"]);
    await user.click((await table()).getByRole("button", { name: /^Tên đăng nhập/ }));
    expect(await names()).toEqual(["v2", "v1", "dave", "carol", "bob", "alice"]);
  });

  it("has the three bars the same: search, Create, and what can be done to what is picked", async () => {
    await asOwner();
    for (const [name, create] of [["Phòng chat", "Mở phòng"], ["Thành viên", "Mời người"]] as const) {
      const toolbar = within(await screen.findByRole("toolbar", { name }));
      expect(toolbar.getByRole("searchbox")).toBeInTheDocument();
      expect(toolbar.getByRole("button", { name: create })).toBeInTheDocument();
    }
  });
});
