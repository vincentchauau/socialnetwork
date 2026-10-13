import { ApiError, apiFetch, loadSession, refreshSession } from "@sn/api";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPage from "../app/page";
import { FakeSocket, msg } from "./fakeSocket";

vi.mock("@sn/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sn/api")>()),
  apiFetch: vi.fn(),
  loadSession: vi.fn(),
  refreshSession: vi.fn(),
}));

const fetchMock = vi.mocked(apiFetch);
const ROOMS = [
  { room: "general", users: 3 },
  { room: "dev", users: 1 },
];
let history: unknown = [];
let roomsReply: unknown = ROOMS;

const flush = () => act(async () => {});
const settle = async () => {
  await flush();
  await flush();
  expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(1);
};

beforeEach(() => {
  FakeSocket.reset();
  history = [];
  roomsReply = ROOMS;
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.mocked(loadSession).mockResolvedValue({ id: 1, username: "alice" });
  vi.mocked(refreshSession).mockResolvedValue(true);
  fetchMock.mockImplementation(async (path: string) => {
    if (path.endsWith("/messages")) {
      if (history instanceof Error) throw history;
      return history as never;
    }
    if (roomsReply instanceof Error) throw roomsReply;
    return roomsReply as never;
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function renderChat() {
  render(<ChatPage />);
  await screen.findByRole("heading", { name: "Chat" });
  await waitFor(() => expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(1));
  const lobby = FakeSocket.last("/ws-lobby");
  lobby.open();
  return lobby;
}

async function joinViaInput(name: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Tạo hoặc vào phòng"), name);
  await user.click(screen.getByRole("button", { name: "Vào" }));
  return user;
}

describe("session gate", () => {
  it("asks anonymous users to sign in and opens no socket", async () => {
    vi.mocked(loadSession).mockResolvedValue(null);
    render(<ChatPage />);
    expect(await screen.findByRole("link", { name: "đăng nhập" })).toHaveAttribute("href", "/login");
    expect(FakeSocket.instances).toHaveLength(0);
  });
});

describe("lobby", () => {
  it("shows live rooms with user counts and updates on rooms frames", async () => {
    const lobby = await renderChat();
    lobby.frame({ type: "rooms", rooms: ROOMS });
    const list = screen.getByRole("list", { name: "Danh sách phòng" });
    expect(within(list).getByRole("button", { name: /general/ })).toHaveTextContent("3 người");
    expect(screen.getByText("Cập nhật trực tiếp")).toBeInTheDocument();

    lobby.frame({ type: "rooms", rooms: [{ room: "new", users: 9 }] });
    expect(within(list).queryByText("general")).not.toBeInTheDocument();
    expect(within(list).getByRole("button", { name: /new/ })).toBeInTheDocument();
    lobby.frame({ type: "message" }); // ignored
    lobby.frame("garbage");
  });

  it("shows an empty state, and a select that lists rooms for narrow screens", async () => {
    const lobby = await renderChat();
    expect(screen.getByText("Chưa có phòng nào đang mở.")).toBeInTheDocument();
    lobby.frame({ type: "rooms", rooms: ROOMS });
    const select = screen.getByRole("combobox", { name: "Chọn phòng" });
    expect(within(select).getByRole("option", { name: "general (3)" })).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "dev" } });
    expect(await screen.findByRole("heading", { name: "#dev" })).toBeInTheDocument();
    expect(select).toHaveValue("dev");
    fireEvent.change(select, { target: { value: "" } }); // placeholder: no join
    expect(screen.getByRole("heading", { name: "#dev" })).toBeInTheDocument();
  });

  it("joins a room by clicking it and marks it current", async () => {
    const lobby = await renderChat();
    lobby.frame({ type: "rooms", rooms: ROOMS });
    await userEvent.click(screen.getByRole("button", { name: /general/ }));
    expect(await screen.findByRole("heading", { name: "#general" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /general/ })).toHaveAttribute("aria-current", "true");
    expect(FakeSocket.byPath("/ws/general")).toHaveLength(1);
  });

  it("falls back to polling GET /rooms every 10 s when the lobby socket closes", async () => {
    vi.useFakeTimers();
    render(<ChatPage />);
    await settle();
    FakeSocket.last("/ws-lobby").drop(1006);
    await flush();
    expect(screen.getByText("Cập nhật mỗi 10 giây")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /general/ })).toBeInTheDocument();

    const roomCalls = () => fetchMock.mock.calls.filter(([p]) => String(p).endsWith("/rooms")).length;
    const before = roomCalls();
    roomsReply = [{ room: "later", users: 2 }];
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(roomCalls()).toBe(before + 1);
    expect(screen.getByRole("button", { name: /later/ })).toBeInTheDocument();

    roomsReply = new ApiError(500, "down");
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.getByRole("button", { name: /later/ })).toBeInTheDocument(); // last list kept

    // backoff reconnect (1 s, then 2 s) and polling stops once the socket is back
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(2);
    FakeSocket.last("/ws-lobby").drop(1006);
    await act(async () => {
      vi.advanceTimersByTime(1999);
    });
    expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(2);
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(3);
    FakeSocket.last("/ws-lobby").open();
    expect(screen.getByText("Cập nhật trực tiếp")).toBeInTheDocument();
    const polled = roomCalls();
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    expect(roomCalls()).toBe(polled);
  });

  it("polls without reconnecting after a policy or refusal close", async () => {
    vi.useFakeTimers();
    render(<ChatPage />);
    await settle();
    FakeSocket.last("/ws-lobby").drop(1013, "Too many lobby connections");
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(1);
    expect(screen.getByText("Cập nhật mỗi 10 giây")).toBeInTheDocument();
  });

  it("closes the lobby socket on unmount", async () => {
    const { unmount } = render(<ChatPage />);
    await waitFor(() => expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(1));
    const lobby = FakeSocket.last("/ws-lobby");
    unmount();
    expect(lobby.closeCalls).toBe(1);
  });
});

describe("create or join by name", () => {
  it("rejects invalid names with a hint and joins valid ones", async () => {
    await renderChat();
    const user = await joinViaInput("bad name!");
    expect(screen.getByRole("alert")).toHaveTextContent("Tên phòng chỉ gồm");
    expect(screen.getByLabelText("Tạo hoặc vào phòng")).toHaveAttribute("aria-invalid", "true");
    expect(FakeSocket.byPath("/ws/bad name!")).toHaveLength(0);

    const input = screen.getByLabelText("Tạo hoặc vào phòng");
    await user.clear(input);
    await user.type(input, "  my-room_1 ");
    await user.click(screen.getByRole("button", { name: "Vào" }));
    expect(await screen.findByRole("heading", { name: "#my-room_1" })).toBeInTheDocument();
    expect(screen.queryByText(/Tên phòng chỉ gồm/)).not.toBeInTheDocument();
    expect(input).toHaveValue("");
  });
});

describe("room view", () => {
  async function openRoom(name = "g") {
    const lobby = await renderChat();
    await joinViaInput(name);
    await screen.findByRole("heading", { name: `#${name}` });
    return { lobby, ws: FakeSocket.last(`/ws/${name}`) };
  }

  it("shows history, then merges live frames without duplicates", async () => {
    history = [msg(1, "bob", "one"), msg(2, "alice", "two"), { junk: true }];
    const { ws } = await openRoom();
    expect(await screen.findByText("one")).toBeInTheDocument();
    ws.open();
    await flush();
    ws.frame(msg(2, "alice", "two")); // already in history
    ws.frame(msg(3, "bob", "three"));
    ws.frame(msg(3, "bob", "three"));
    const log = screen.getByRole("log", { name: "Tin nhắn" });
    expect(within(log).getAllByRole("article")).toHaveLength(3);
    expect(log).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Đã kết nối")).toBeInTheDocument();
  });

  it("distinguishes own bubbles and renders content as plain text", async () => {
    const xss = "<img src=x onerror=alert(1)>";
    const { ws } = await openRoom();
    ws.open();
    ws.frame(msg(1, "alice", xss));
    ws.frame(msg(2, "bob", "hello"));
    const log = screen.getByRole("log");
    expect(log.querySelector("img")).toBeNull();
    expect(within(log).getByText(xss)).toBeInTheDocument();
    const [own, other] = within(log).getAllByRole("article");
    expect(own).toHaveClass("own");
    expect(other).not.toHaveClass("own");
    expect(own.querySelector("time")).toHaveTextContent(/\d{2}:\d{2}/);
  });

  it("renders a blank time for an invalid timestamp", async () => {
    const { ws } = await openRoom();
    ws.open();
    ws.frame({ ...msg(1), created_at: "nope" });
    expect(within(screen.getByRole("log")).getByRole("article").querySelector("time")).toHaveTextContent("");
  });

  it("shows join/leave system lines that are not messages", async () => {
    const { ws } = await openRoom();
    ws.open();
    ws.frame({ type: "system", event: "join", room: "g", userId: 2, username: "bob", at: "2026-01-01T00:00:01Z" });
    ws.frame(msg(5, "bob", "hi"));
    ws.frame({ type: "system", event: "leave", room: "g", userId: 2, username: "bob", at: "2026-01-01T00:00:09Z" });
    const log = screen.getByRole("log");
    expect(within(log).getByText("bob đã vào phòng")).toHaveClass("system-line");
    expect(within(log).getByText("bob đã rời phòng")).toHaveClass("system-line");
    expect(within(log).getAllByRole("article")).toHaveLength(1);
  });

  it("caps stored system lines", async () => {
    const { ws } = await openRoom();
    ws.open();
    for (let i = 0; i < 205; i += 1) {
      ws.frame({ type: "system", event: "join", username: `u${i}`, at: "2026-01-01T00:00:01Z" });
    }
    expect(within(screen.getByRole("log")).queryByText("u0 đã vào phòng")).toBeNull();
    expect(within(screen.getByRole("log")).getByText("u204 đã vào phòng")).toBeInTheDocument();
  });

  it("renders presence with total and the '+M người khác' cap note", async () => {
    const { ws } = await openRoom();
    expect(screen.getByText("Đang tải…")).toBeInTheDocument();
    ws.open();
    ws.frame({ type: "presence", room: "g", total: 2, members: [{ userId: 1, username: "alice" }, { userId: 2, username: "bob" }] });
    expect(screen.getByRole("heading", { name: "Đang trong phòng (2)" })).toBeInTheDocument();
    expect(screen.queryByText(/người khác/)).not.toBeInTheDocument();

    ws.frame({ type: "presence", room: "g", total: 250, members: [{ userId: 1, username: "alice" }] });
    expect(screen.getByRole("heading", { name: "Đang trong phòng (250)" })).toBeInTheDocument();
    expect(screen.getByText("+249 người khác")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Thành viên" })).toHaveTextContent("alice");
  });

  it("sends trimmed text with Enter, keeps Shift+Enter as newline, counts characters", async () => {
    const { ws } = await openRoom();
    const box = screen.getByLabelText("Tin nhắn", { selector: "textarea" });
    expect(screen.getByRole("button", { name: "Gửi" })).toBeDisabled();
    ws.open();
    const user = userEvent.setup();
    await user.type(box, "  hello{Shift>}{Enter}{/Shift}world  ");
    expect(box).toHaveValue("  hello\nworld  ");
    expect(screen.getByText("15/2000")).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(ws.sent).toEqual([JSON.stringify({ content: "hello\nworld" })]);
    expect(box).toHaveValue("");
    expect(screen.getByText("0/2000")).toBeInTheDocument();

    await user.keyboard("{Enter}"); // empty: nothing sent
    await user.type(box, "via button");
    await user.click(screen.getByRole("button", { name: "Gửi" }));
    expect(ws.sent).toHaveLength(2);
  });

  it("limits the draft to 2000 characters and ignores IME composition Enter", async () => {
    const { ws } = await openRoom();
    ws.open();
    const box = screen.getByRole("textbox", { name: "Tin nhắn" });
    expect(box).toHaveAttribute("maxlength", "2000");
    fireEvent.change(box, { target: { value: "x".repeat(2000) } });
    expect(screen.getByText("2000/2000")).toBeInTheDocument();
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    expect(ws.sent).toHaveLength(0);
    fireEvent.keyDown(box, { key: "a" });
    expect(ws.sent).toHaveLength(0);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(ws.sent).toHaveLength(1);
  });

  it("keeps the draft when the socket is not open", async () => {
    const { ws } = await openRoom();
    ws.open();
    const box = screen.getByRole("textbox", { name: "Tin nhắn" });
    fireEvent.change(box, { target: { value: "keep me" } });
    ws.readyState = 3; // dropped without an event yet
    fireEvent.submit(box.closest("form")!);
    expect(box).toHaveValue("keep me");
    expect(ws.sent).toHaveLength(0);
  });

  it("disables sending while disconnected", async () => {
    const { ws } = await openRoom();
    fireEvent.change(screen.getByRole("textbox", { name: "Tin nhắn" }), { target: { value: "x" } });
    expect(screen.getByRole("button", { name: "Gửi" })).toBeDisabled();
    ws.open();
    expect(screen.getByRole("button", { name: "Gửi" })).toBeEnabled();
  });

  it("autoscrolls only when the reader is at the bottom", async () => {
    const { ws } = await openRoom();
    ws.open();
    const log = screen.getByRole("log");
    let height = 1000;
    Object.defineProperty(log, "scrollHeight", { configurable: true, get: () => height });
    Object.defineProperty(log, "clientHeight", { configurable: true, value: 200 });

    log.scrollTop = 0;
    fireEvent.scroll(log); // far from bottom
    height = 1100;
    ws.frame(msg(1));
    expect(log.scrollTop).toBe(0);

    log.scrollTop = height - 200 - 10; // within tolerance
    fireEvent.scroll(log);
    height = 1300;
    ws.frame(msg(2));
    expect(log.scrollTop).toBe(1300);
  });

  it("shows server error frames and the history failure notice", async () => {
    history = new ApiError(500, "x");
    const { ws } = await openRoom();
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tải được lịch sử");
    ws.open(); // clears the notice
    ws.frame({ type: "error", error: "Message must be 1-2000 characters" });
    expect(screen.getByRole("alert")).toHaveTextContent("từ 1 đến 2000");
    ws.frame({ type: "error", error: "Custom" });
    expect(screen.getByRole("alert")).toHaveTextContent("Custom");
    ws.frame({ type: "bogus" });
  });
});

describe("connection handling", () => {
  async function openRoom() {
    await renderChat();
    await joinViaInput("g");
    await screen.findByRole("heading", { name: "#g" });
    return FakeSocket.last("/ws/g");
  }

  it("reconnects with backoff, re-fetches history and keeps messages", async () => {
    vi.useFakeTimers();
    render(<ChatPage />);
    await settle();
    FakeSocket.last("/ws-lobby").open();
    fireEvent.change(screen.getByLabelText("Tạo hoặc vào phòng"), { target: { value: "g" } });
    fireEvent.click(screen.getByRole("button", { name: "Vào" }));
    const first = FakeSocket.last("/ws/g");
    first.open();
    first.frame(msg(1, "bob", "old"));
    first.frame({ type: "presence", total: 1, members: [{ userId: 2, username: "bob" }] });
    const historyCalls = () => fetchMock.mock.calls.filter(([p]) => String(p).endsWith("/messages")).length;
    await flush();
    const calls = historyCalls();

    first.drop(1006);
    expect(screen.getByText("Mất kết nối, đang thử lại…")).toBeInTheDocument();
    expect(screen.getByText("old")).toBeInTheDocument();
    expect(screen.getByText("Đang tải…")).toBeInTheDocument(); // stale presence cleared
    await act(async () => {
      vi.advanceTimersByTime(999);
    });
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(1);
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    const second = FakeSocket.last("/ws/g");
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(2);
    second.drop(1006); // attempt 2 -> 2 s
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    const third = FakeSocket.last("/ws/g");
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(3);
    history = [msg(1, "bob", "old"), msg(2, "bob", "missed")];
    third.open();
    await flush();
    expect(historyCalls()).toBeGreaterThan(calls);
    expect(screen.getByText("missed")).toBeInTheDocument();
    expect(screen.getAllByText("old")).toHaveLength(1);
    third.drop(1006); // success resets the backoff to 1 s
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(4);
  });

  it("refreshes the session once on 1008 then reconnects", async () => {
    const ws = await openRoom();
    ws.open();
    ws.drop(1008);
    await flush();
    expect(refreshSession).toHaveBeenCalledTimes(1);
    const next = FakeSocket.last("/ws/g");
    expect(next).not.toBe(ws);
    next.open();
    next.drop(1008); // refreshed flag was reset by the successful open
    await flush();
    expect(refreshSession).toHaveBeenCalledTimes(2);
  });

  it("stops on 1008 when the refresh fails or repeats, with a login hint", async () => {
    vi.mocked(refreshSession).mockResolvedValue(false);
    const ws = await openRoom();
    ws.open();
    ws.drop(1008);
    await flush();
    expect(screen.getByRole("link", { name: "đăng nhập" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("alert")).toHaveTextContent("Phiên đăng nhập");
    expect(screen.getByText("Đã ngắt kết nối")).toBeInTheDocument();
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(1);
  });

  it("stops after a second consecutive 1008 without refreshing again", async () => {
    const ws = await openRoom();
    ws.drop(1008);
    await flush();
    FakeSocket.last("/ws/g").drop(1008);
    await flush();
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "đăng nhập" })).toBeInTheDocument();
  });

  it.each([
    ["Room is full", "Phòng đã đầy"],
    ["Too many active rooms", "Quá nhiều phòng đang hoạt động"],
    ["Too many connections", "Bạn mở quá nhiều kết nối"],
  ])("shows the Vietnamese refusal for 1013 %s and offers a retry", async (reason, text) => {
    const ws = await openRoom();
    ws.drop(1013, reason);
    expect(screen.getByRole("alert")).toHaveTextContent(text);
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(2);
    expect(ws.closeCalls).toBe(0); // already closed by the server; nothing to close
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("tells about 1009 and keeps reconnecting", async () => {
    vi.useFakeTimers();
    render(<ChatPage />);
    await settle();
    fireEvent.change(screen.getByLabelText("Tạo hoặc vào phòng"), { target: { value: "g" } });
    fireEvent.click(screen.getByRole("button", { name: "Vào" }));
    FakeSocket.last("/ws/g").drop(1009);
    expect(screen.getByRole("alert")).toHaveTextContent("quá lớn");
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(2);
  });

  it("leaving closes the room socket, and re-joining starts clean", async () => {
    const ws = await openRoom();
    ws.open();
    ws.frame(msg(1, "bob", "stale"));
    await userEvent.click(screen.getByRole("button", { name: "Rời phòng" }));
    expect(ws.closeCalls).toBe(1);
    expect(screen.getByText(/Chọn một phòng hoặc tạo phòng mới/)).toBeInTheDocument();
    expect(ws.onmessage).toBeNull();
    act(() => ws.onclose?.({ code: 1006, reason: "" })); // late event: ignored
    await joinViaInput("g");
    await screen.findByRole("heading", { name: "#g" });
    expect(screen.queryByText("stale")).not.toBeInTheDocument();
  });

  it("switching rooms closes the old socket and ignores its late frames and history", async () => {
    let release: (value: unknown) => void = () => {};
    const lobby = await renderChat();
    lobby.frame({ type: "rooms", rooms: ROOMS });
    fetchMock.mockImplementationOnce(
      () => new Promise((resolve) => (release = resolve)) as never,
    ); // general's history stays pending
    await userEvent.click(screen.getByRole("button", { name: /general/ }));
    const general = FakeSocket.last("/ws/general");
    general.open();
    await userEvent.click(screen.getByRole("button", { name: /dev/ }));
    const dev = FakeSocket.last("/ws/dev");
    expect(general.closeCalls).toBe(1);
    dev.open();
    general.onmessage?.({ data: JSON.stringify(msg(9, "bob", "ghost")) });
    await act(async () => release([msg(9, "bob", "ghost")]));
    await flush();
    expect(screen.queryByText("ghost")).not.toBeInTheDocument();
    expect(FakeSocket.byPath("/ws/general")).toHaveLength(1);
    expect(FakeSocket.byPath("/ws/dev")).toHaveLength(1);
    dev.frame(msg(1, "bob", "real"));
    expect(screen.getByText("real")).toBeInTheDocument();
  });

  it("closes the room and lobby sockets on unmount and cancels pending retries", async () => {
    vi.useFakeTimers();
    const { unmount } = render(<ChatPage />);
    await settle();
    fireEvent.change(screen.getByLabelText("Tạo hoặc vào phòng"), { target: { value: "g" } });
    fireEvent.click(screen.getByRole("button", { name: "Vào" }));
    const ws = FakeSocket.last("/ws/g");
    const lobby = FakeSocket.last("/ws-lobby");
    ws.drop(1006); // retry pending
    unmount();
    expect(lobby.closeCalls).toBe(1);
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(1);
  });

  it("does not refresh or reconnect after unmounting during a refresh", async () => {
    let finish: (ok: boolean) => void = () => {};
    vi.mocked(refreshSession).mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { unmount } = render(<ChatPage />);
    await waitFor(() => expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(1));
    FakeSocket.last("/ws-lobby").open();
    await joinViaInput("g");
    const ws = FakeSocket.last("/ws/g");
    ws.drop(1008);
    unmount();
    await act(async () => finish(true));
    expect(FakeSocket.byPath("/ws/g")).toHaveLength(1);
  });
});
