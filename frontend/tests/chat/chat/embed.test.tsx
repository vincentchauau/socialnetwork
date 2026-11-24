import { ApiError, apiFetch } from "@sn/api";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EmbedChat from "../../../app/chat/components/EmbedChat";
import type { MemberRow, Room } from "../../../app/chat/protocol";
import { FakeSocket, msg } from "./fakeSocket";

vi.mock("next/navigation", async (importOriginal) => ({ ...(await importOriginal<typeof import("next/navigation")>()), useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));
const fetchMock = vi.mocked(apiFetch);

// ---- a small server: the rooms of the apps, who is in them, and the calls it was asked ----

const ME = { role: "member", status: "joined", muted: false, unread: 0 } as const;
const room = (slug: string, category: string, extra: Partial<Room> = {}): Room =>
  ({
    id: 1, slug, kind: "chat", title: slug === "village" ? "The village" : slug, category, user_id: 9,
    visibility: "public", join_policy: "open", capacity: 200, state: "open", members: 2, online: 0, me: { ...ME }, ...extra,
  }) as Room;

const db = { rooms: [] as Room[], calls: [] as { method: string; path: string; body?: Record<string, unknown> }[], fail: false };
const people: MemberRow[] = [
  { user_id: 1, username: "alice", role: "owner", status: "joined", muted: false, online: true } as MemberRow,
  { user_id: 2, username: "bob", role: "member", status: "joined", muted: false, online: false } as MemberRow,
];

function serve(path: string, init: RequestInit = {}): unknown {
  const method = init.method ?? "GET";
  const body = init.body ? (JSON.parse(init.body as string) as Record<string, unknown>) : undefined;
  const url = new URL(path.replace(/^\/api\/chat/, ""), "http://x");
  db.calls.push({ method, path: url.pathname + url.search, body });
  if (db.fail) throw new ApiError(403, "banned", { detail: "You are banned from this room" });
  const parts = url.pathname.split("/").filter(Boolean);
  if (parts[0] === "rooms" && parts.length === 1) {
    if (method === "POST") {
      const made = room(String(body?.title).toLowerCase().replace(/\W+/g, "-"), String(body?.category ?? ""), { title: String(body?.title) });
      db.rooms.push(made);
      return made;
    }
    const scope = url.searchParams.get("scope");
    return db.rooms.filter((r) => scope === "public" || r.me !== null);
  }
  const found = db.rooms.find((r) => r.slug === parts[1]);
  if (!found) throw new ApiError(404, "Room not found", { detail: "Room not found" });
  if (parts[2] === "members") return people;
  if (parts[2] === "messages") return [msg(1, "bob", "hello from bob")];
  if (parts[2] === "join") return Object.assign(found, { me: { ...ME } });
  return found;
}

type Parts = { rooms: boolean; members: boolean; messages: boolean; settings?: boolean };
const MESSAGES: Parts = { rooms: false, members: false, messages: true };
const show = (panels: Parts = MESSAGES) => {
  const view = render(<EmbedChat userId={1} username="alice" panels={{ settings: false, ...panels }} />);
  return (next: Parts) => view.rerender(<EmbedChat userId={1} username="alice" panels={{ settings: false, ...next }} />);
};

beforeEach(() => {
  FakeSocket.reset();
  db.rooms = [room("village", ""), room("market-deals", "market"), room("elsewhere", "files")];
  window.localStorage.setItem("sn_dock_room", "village"); // the room that was open last time
  db.calls = [];
  db.fail = false;
  fetchMock.mockImplementation((async (path: string, init?: RequestInit) => serve(path, init)) as never);
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => vi.unstubAllGlobals());

const called = (method: string, pattern: RegExp) => db.calls.filter((c) => c.method === method && pattern.test(c.path));

/** The actions of a row sit behind its "More" button: open it. */
function opened(row: HTMLElement): HTMLElement {
  const more = within(row).queryByRole("button", { name: /^Khác/ });
  if (more && more.getAttribute("aria-expanded") === "false") fireEvent.click(more);
  return row;
}

describe("the chat under the page of an app", () => {
  it("opens the room that was open last time (the same one in every app) and connects", async () => {
    show();
    await waitFor(() => expect(FakeSocket.byPath("/ws/village")).toHaveLength(1));
    expect(called("POST", /app-rooms/)).toHaveLength(0); // nothing is made for the app
    expect(await screen.findByText("hello from bob")).toBeInTheDocument();
  });

  it("opens no room by itself when none was open: it says to pick or make one", async () => {
    window.localStorage.removeItem("sn_dock_room");
    show();
    expect(await screen.findByText(/Chưa mở phòng nào/)).toBeInTheDocument();
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("does not open the remembered room when the person is not in it any more", async () => {
    db.rooms = db.rooms.map((r) => (r.slug === "village" ? { ...r, me: null } : r));
    show();
    expect(await screen.findByText(/Chưa mở phòng nào/)).toBeInTheDocument();
    expect(FakeSocket.byPath("/ws/village")).toHaveLength(0);
  });

  it("sends and receives only while Messages is on: off closes the connection and the box, on opens them again", async () => {
    const set = show();
    await waitFor(() => expect(FakeSocket.byPath("/ws/village")).toHaveLength(1));
    const first = FakeSocket.last("/ws/village");
    first.open();
    expect(await screen.findByRole("textbox")).toBeInTheDocument();
    set({ rooms: false, members: false, messages: false });
    await waitFor(() => expect(first.closeCalls).toBeGreaterThan(0));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText(/Chat đang tắt/)).toBeInTheDocument();
    set(MESSAGES);
    await waitFor(() => expect(FakeSocket.byPath("/ws/village")).toHaveLength(2));
  });

  it("reads the rooms under Rooms in a table, opens one (and remembers it), and makes a new one with every option", async () => {
    const user = userEvent.setup();
    show({ rooms: true, members: false, messages: true });
    const table = await screen.findByRole("table", { name: "Danh sách phòng" });
    expect(within(table).getByRole("button", { name: "The village" })).toBeInTheDocument();
    await user.click(within(table).getByRole("button", { name: "market-deals" }));
    await waitFor(() => expect(FakeSocket.byPath("/ws/market-deals")).toHaveLength(1));
    expect(window.localStorage.getItem("sn_dock_room")).toBe("market-deals");
    await user.click(within(screen.getByRole("toolbar", { name: "Phòng chat" })).getByRole("button", { name: "Mở phòng" }));
    const form = await screen.findByRole("form", { name: "Mở phòng" });
    await user.type(within(form).getByLabelText("Tên phòng"), "Lamps for sale");
    expect(within(form).getByLabelText("Trạng thái")).toBeInTheDocument(); // the options of a room, not only its name
    await user.click(within(form).getByRole("button", { name: "Mở phòng" }));
    await waitFor(() => expect(called("POST", /^\/rooms$/)[0]?.body).toMatchObject({ title: "Lamps for sale", category: "", visibility: "public" }));
    await waitFor(() => expect(FakeSocket.byPath("/ws/lamps-for-sale")).toHaveLength(1));
  });

  it("shows who is in the room under Members, without needing Messages", async () => {
    show({ rooms: false, members: true, messages: false });
    expect(await screen.findByText("bob")).toBeInTheDocument();
    expect(screen.getByText(/alice/)).toBeInTheDocument();
    expect(FakeSocket.byPath("/ws/village")).toHaveLength(0);
  });

  it("says why a room cannot be entered when the person picks it", async () => {
    window.localStorage.removeItem("sn_dock_room");
    const user = userEvent.setup();
    show({ rooms: true, members: false, messages: true });
    const table = await screen.findByRole("table", { name: "Danh sách phòng" });
    db.fail = true;
    await user.click(within(table).getByRole("button", { name: "market-deals" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(FakeSocket.byPath("/ws/market-deals")).toHaveLength(0);
  });
});

describe("virtual people in the member table", () => {
  const virtual = { user_id: 70, username: "Vinh_Phan", role: "member", status: "joined", muted: false, online: true, virtual: true } as MemberRow;

  it("are rows like the others, labelled virtual, with the dot of being online", async () => {
    people.push(virtual);
    try {
      render(<EmbedChat userId={1} username="alice" panels={{ rooms: false, members: true, messages: false }} />);
      const row = opened((await screen.findByText("Vinh_Phan")).closest("tr")!);
      expect(row).toHaveTextContent(/ảo/i);
      expect(within(row).getByRole("img", { name: "Đang trực tuyến" })).toBeInTheDocument(); // they are always there: online, like anybody
    } finally {
      people.splice(2);
    }
  });

  it("have the same two actions as every person to the owner: a box to be picked, and to be written to", async () => {
    people.push(virtual);
    db.rooms = db.rooms.map((r) => (r.slug === "village" ? { ...r, me: { ...ME, role: "owner" } } : r));
    try {
      show({ rooms: false, members: true, messages: false });
      const row = opened((await screen.findByText("Vinh_Phan")).closest("tr")!);
      expect(within(row).getByRole("checkbox")).toBeInTheDocument();
      expect(within(row).getByRole("button", { name: "Nhắn" })).toBeInTheDocument();
    } finally {
      people.splice(2);
    }
  });
});

describe("adding virtual people", () => {
  it("is in the member list of every chat room the person is in", async () => {
    const user = userEvent.setup();
    show({ rooms: false, members: true, messages: false });
    await user.click(await screen.findByRole("button", { name: "Mời người" })); // Create, in the same bar as every list
    expect(await screen.findByRole("button", { name: "Thêm người ảo" })).toBeInTheDocument();
  });

  it("is not offered in a private chat of two", async () => {
    db.rooms = db.rooms.map((r) => (r.slug === "village" ? { ...r, kind: "dm" } : r));
    show({ rooms: false, members: true, messages: false });
    await screen.findByText("bob");
    expect(screen.queryByRole("button", { name: "Mời người" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Thêm người ảo" })).toBeNull();
  });
});

describe("the buttons over the parts of the chat", () => {
  it("are there only where the page asks for them, one for each part, and tell what they are set to", async () => {
    const user = userEvent.setup();
    const told = vi.fn();
    render(<EmbedChat userId={1} username="alice" panels={{ rooms: false, members: false, messages: true }} onPanels={told} />);
    expect(screen.getAllByRole("button", { name: /^(Rooms|Members|Messages)/ }).map((button) => button.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"]); // Rooms, Messages, Members
    await user.click(screen.getByRole("button", { name: "Rooms" }));
    expect(told).toHaveBeenCalledWith({ rooms: true, messages: true, members: false });
  });
});
