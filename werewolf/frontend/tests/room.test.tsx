import { ApiError } from "@sn/api";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoomView from "../app/components/RoomView";
import { FakeSocket, makeGame, makeRoom, member, VILLAGER, WOLF } from "./helpers";
import { api, envelope, push, pushState, renderRoom, resetRoomTest } from "./roomHarness";

vi.mock("../app/lib/api", async () => (await import("./apiMock")).apiFactory());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: (path: string) => push(path) }) }));

beforeEach(resetRoomTest);

describe("Lobby", () => {
  it("shows the title, the code and every member, with roles only for your own seat", async () => {
    await renderRoom(
      makeRoom({
        members: [
          member(1, "alice", { faction: WOLF, ability: { code: "KILL", label: "Giết trực tiếp" } }),
          member(2, "Bình", { faction: VILLAGER, ability: { code: "NONE", label: "Không có" } }),
          member(3, "Cường"),
          member(4, "Dũng"),
          member(5, "Em"),
        ],
      }),
    );
    expect(screen.getByRole("heading", { name: "Làng Trăng Máu" })).toBeInTheDocument();
    expect(screen.getByText("🔑 ABCDE")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /5 người/ })).toBeInTheDocument();
    expect(screen.getByText(/🐺 Sói · 🗡️ Giết trực tiếp/)).toBeInTheDocument();
    // another member's role must never reach the screen, even if the server leaked it
    expect(screen.queryByText(/Không có/)).not.toBeInTheDocument();
    expect(screen.getByText("alice ★")).toBeInTheDocument();
    expect(screen.getAllByText("🤖").length).toBe(4);
  });

  it("lets the host add bots, then start", async () => {
    const u = userEvent.setup();
    const small = makeRoom({ members: [member(1, "alice"), member(2, "Bình"), member(3, "Cường")] });
    await renderRoom(small);
    expect(screen.getByRole("status")).toHaveTextContent("Cần thêm 2 người");
    expect(screen.getByRole("button", { name: /Bắt đầu game/ })).toBeDisabled();

    api.addBots.mockResolvedValue(envelope(makeRoom()));
    await u.click(screen.getByRole("button", { name: "🤖 +2 Bot" }));
    expect(api.addBots).toHaveBeenCalledWith("ABCDE", 2);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Đủ người"));

    api.start.mockResolvedValue(envelope(makeRoom({ started: true, game: makeGame() })));
    await u.click(screen.getByRole("button", { name: /Bắt đầu game/ }));
    expect(api.start).toHaveBeenCalledWith("ABCDE");
    expect(await screen.findByRole("heading", { name: "Đêm 1" })).toBeInTheDocument();
  });

  it("adds a single bot", async () => {
    const u = userEvent.setup();
    await renderRoom(makeRoom());
    api.addBots.mockResolvedValue(envelope(makeRoom()));
    await u.click(screen.getByRole("button", { name: "🤖 +1 Bot" }));
    expect(api.addBots).toHaveBeenCalledWith("ABCDE", 1);
    expect(screen.queryAllByRole("button", { name: /^🤖 \+[2-9]/ })).toHaveLength(0); // already 5 seats: nothing missing
  });

  it("stops offering bots when the room is full", async () => {
    const members = Array.from({ length: 40 }, (_, i) => member(i + 1, `P${i + 1}`));
    await renderRoom(makeRoom({ members }));
    expect(screen.getByRole("button", { name: "🤖 +1 Bot" })).toBeDisabled();
  });

  it("shows a guest only the waiting message", async () => {
    await renderRoom(makeRoom({ isHost: false }));
    expect(screen.getByText(/Đang chờ chủ phòng bắt đầu/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Bắt đầu game|Bot/ })).not.toBeInTheDocument();
  });

  it("describes the room settings", async () => {
    await renderRoom(makeRoom({ timer: 60, events: false, deadTalk: false, listed: false }));
    expect(screen.getByText(/⏱ 60s\/lượt/)).toBeInTheDocument();
    expect(screen.getByText(/Không thẻ sự kiện/)).toBeInTheDocument();
    expect(screen.getByText(/Người chết chat riêng/)).toBeInTheDocument();
    expect(screen.getByText(/Chỉ vào bằng mã/)).toBeInTheDocument();
  });

  it("leaves and goes back home", async () => {
    const u = userEvent.setup();
    api.leave.mockResolvedValue({ left: true });
    await renderRoom(makeRoom());
    await u.click(screen.getByRole("button", { name: /Rời phòng/ }));
    expect(api.leave).toHaveBeenCalledWith("ABCDE");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("explains a refused start with the server's message", async () => {
    const u = userEvent.setup();
    api.start.mockRejectedValue(new ApiError(403, "Chỉ chủ phòng mới được bắt đầu", { detail: "Chỉ chủ phòng mới được bắt đầu" }));
    await renderRoom(makeRoom());
    await u.click(screen.getByRole("button", { name: /Bắt đầu game/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chỉ chủ phòng mới được bắt đầu");
  });

  it("follows pushes: a new member shows up without any action", async () => {
    await renderRoom(makeRoom({ members: [member(1, "alice"), member(2, "Bình")] }));
    pushState(makeRoom({ members: [member(1, "alice"), member(2, "Bình"), member(3, "Mới vào", { isBot: false })] }));
    expect(screen.getByText("Mới vào")).toBeInTheDocument();
  });

  it("goes from lobby to game when the state frame carries a game", async () => {
    await renderRoom(makeRoom());
    pushState(makeRoom({ started: true, game: makeGame({ phase: "day", night: 2 }) }));
    expect(screen.getByRole("heading", { name: "Ngày 2" })).toBeInTheDocument();
  });
});

describe("Preview of a lobby you are not seated in", () => {
  it("joins, and the socket opens afterwards", async () => {
    const u = userEvent.setup();
    await renderRoom(makeRoom({ you: null, isHost: false }));
    expect(FakeSocket.instances).toHaveLength(0);
    expect(screen.queryByText(/Sói|Người/)).not.toBeInTheDocument();
    api.join.mockResolvedValue(envelope(makeRoom({ isHost: false })));
    await u.click(screen.getByRole("button", { name: "Vào phòng" }));
    expect(api.join).toHaveBeenCalledWith("ABCDE");
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1));
    expect(await screen.findByText(/Đang chờ chủ phòng bắt đầu/)).toBeInTheDocument();
  });

  it("cannot join a game that already started", async () => {
    await renderRoom(makeRoom({ you: null, started: true }));
    expect(screen.getByRole("button", { name: "Vào phòng" })).toBeDisabled();
    expect(screen.getByText(/Ván đã bắt đầu/)).toBeInTheDocument();
  });

  it("shows a full-room refusal", async () => {
    const u = userEvent.setup();
    api.join.mockRejectedValue(new ApiError(409, "Phòng đã đầy", { detail: "Phòng đã đầy" }));
    await renderRoom(makeRoom({ you: null }));
    await u.click(screen.getByRole("button", { name: "Vào phòng" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Phòng đã đầy");
  });
});

describe("Connection states", () => {
  it("shows a clear message and a way out when the room is gone", async () => {
    api.room.mockRejectedValue(new ApiError(404, "Không tìm thấy phòng", { detail: "Không tìm thấy phòng" }));
    render(<RoomView code="ZZZZZ" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy phòng");
    expect(screen.getByRole("link", { name: /Danh sách phòng/ })).toHaveAttribute("href", "/");
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("shows a banner while reconnecting and removes it once back", async () => {
    await renderRoom(makeRoom());
    act(() => FakeSocket.last().drop(1006));
    expect(await screen.findByText(/Mất kết nối, đang kết nối lại/)).toBeInTheDocument();
    await waitFor(() => expect(FakeSocket.instances.length).toBe(2), { timeout: 3000 });
    act(() => FakeSocket.last().open());
    await waitFor(() => expect(screen.queryByText(/Mất kết nối/)).not.toBeInTheDocument());
  });

  it("toasts an error frame from the server", async () => {
    await renderRoom(makeRoom());
    act(() => FakeSocket.last().push({ type: "error", error: "Chưa tới lượt" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chưa tới lượt");
  });

  it("reports a deleted room (1001) as fatal", async () => {
    await renderRoom(makeRoom());
    act(() => FakeSocket.last().drop(1001));
    expect(await screen.findByRole("alert")).toHaveTextContent("Phòng đã bị xoá.");
  });
});

describe("Room page extras", () => {
  it("shows no controls while loading", () => {
    api.room.mockReturnValue(new Promise(() => undefined));
    render(<RoomView code="ABCDE" />);
    expect(screen.getByText("Đang tải phòng…")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
