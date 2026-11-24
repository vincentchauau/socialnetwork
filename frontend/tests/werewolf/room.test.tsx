import { ApiError } from "@sn/api";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoomView from "../../app/werewolf/components/RoomView";
import type { FactionCode, SeatRole } from "../../app/werewolf/lib/types";
import { FakeSocket, makeGame, makeRoom, member, VILLAGER, WOLF } from "./helpers";
import { api, envelope, push, pushState, renderRoom, resetRoomTest } from "./roomHarness";

vi.mock("../../app/werewolf/lib/api", async () => (await import("./apiMock")).apiFactory());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: (path: string) => push(path) }) }));

beforeEach(resetRoomTest);

describe("Lobby", () => {
  it("shows only Random and Start to the host: no list of members, no roles on the screen", async () => {
    await renderRoom(makeRoom({ members: [member(1, "alice"), member(2, "Bình"), member(3, "Cường"), member(4, "Dũng"), member(5, "Em")] }));
    expect(screen.queryByText("🔑 ABCDE")).toBeNull();
    expect(screen.queryByText("alice ★")).toBeNull();
    expect(screen.queryByText("🤖")).toBeNull();
    expect(screen.queryByRole("heading", { name: /trong phòng/ })).toBeNull();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["🎲 Ngẫu nhiên", "▶ Bắt đầu", "Hiện"]);
  });

  it("shows the rules from the server inside the lobby box, and an error when they cannot be loaded", async () => {
    await renderRoom(makeRoom());
    expect(await screen.findByText("Phe nào hết đối thủ thì thắng.")).toBeInTheDocument();
  });

  it("starts with the roles and the rules hidden, and shows and hides them with one button", async () => {
    const user = userEvent.setup();
    await renderRoom(makeRoom());
    const details = document.getElementById("ww-lobby-details") as HTMLElement;
    expect(details).toHaveAttribute("hidden");
    expect(screen.getByRole("button", { name: "Hiện" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hiện" }));
    expect(details).not.toHaveAttribute("hidden");
    await user.click(screen.getByRole("button", { name: "Ẩn" }));
    expect(details).toHaveAttribute("hidden");
  });

  it("opens the roles when the host presses Random", async () => {
    const user = userEvent.setup();
    await renderRoom(makeRoom());
    api.roles.mockResolvedValue(envelope(makeRoom()) as never);
    await user.click(screen.getByRole("button", { name: /Ngẫu nhiên/ }));
    expect(document.getElementById("ww-lobby-details")).not.toHaveAttribute("hidden");
  });

  it("lets the host tick abilities the random deal leaves out, and sends them with Random only when some are ticked", async () => {
    const user = userEvent.setup();
    const { META } = await import("./helpers");
    api.meta.mockResolvedValue({ ...META, bannable: ["SEE_FACTION", "BLOCK_EFFECTS"] });
    api.roles.mockResolvedValue(envelope(makeRoom()) as never);
    await renderRoom(makeRoom());
    await user.click(screen.getByRole("button", { name: /Ngẫu nhiên/ }));
    expect(api.roles).toHaveBeenLastCalledWith("ABCDE", { random: true }); // nothing ticked: as before
    const summary = await screen.findByText(/Chức năng không chia ngẫu nhiên|Abilities the random deal leaves out/);
    await user.click(summary);
    const boxes = within(summary.closest("details") as HTMLElement).getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    await user.click(boxes[0]);
    await user.click(screen.getByRole("button", { name: /Ngẫu nhiên/ }));
    expect(api.roles).toHaveBeenLastCalledWith("ABCDE", { random: true, banned: ["SEE_FACTION"] });
  });

  it("lets the host start when there are enough seats (the seats are the people of the chat room, the rest are bots)", async () => {
    const u = userEvent.setup();
    await renderRoom(makeRoom());
    expect(screen.queryByRole("button", { name: /Bot/ })).toBeNull(); // the seats follow the room: nobody adds bots by hand
    expect(screen.queryByRole("status")).toBeNull(); // (enough seats: nothing to say)
    api.start.mockResolvedValue(envelope(makeRoom({ started: true, game: makeGame() })));
    await u.click(screen.getByRole("button", { name: /Bắt đầu/ }));
    expect(api.start).toHaveBeenCalledWith("ABCDE");
    expect(await screen.findByRole("heading", { name: "Đêm 1" })).toBeInTheDocument();
  });

  it("does not let the host start with fewer seats than the game needs", async () => {
    const small = makeRoom({ members: [member(1, "alice"), member(2, "Bình"), member(3, "Cường")] });
    await renderRoom(small);
    expect(screen.getByRole("status")).toHaveTextContent("Cần thêm 2 người");
    expect(screen.getByRole("button", { name: /Bắt đầu/ })).toBeDisabled();
  });

  it("shows a guest only the waiting message", async () => {
    await renderRoom(makeRoom({ isHost: false }));
    expect(screen.getByText(/Đang chờ chủ phòng bắt đầu/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Bắt đầu|Bot/ })).not.toBeInTheDocument();
  });

  it("lets a guest leave and go back home (the host has only Random and Start)", async () => {
    const u = userEvent.setup();
    api.leave.mockResolvedValue({ left: true });
    await renderRoom(makeRoom({ isHost: false }));
    await u.click(screen.getByRole("button", { name: /Rời phòng/ }));
    expect(api.leave).toHaveBeenCalledWith("ABCDE");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
  });

  it("explains a refused start with the server's message", async () => {
    const u = userEvent.setup();
    api.start.mockRejectedValue(new ApiError(403, "Chỉ chủ phòng mới được bắt đầu", { detail: "Chỉ chủ phòng mới được bắt đầu" }));
    await renderRoom(makeRoom());
    await u.click(screen.getByRole("button", { name: /Bắt đầu/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chỉ chủ phòng mới được bắt đầu");
  });

  it("follows pushes: the missing-players message goes away when enough people are in", async () => {
    await renderRoom(makeRoom({ members: [member(1, "alice"), member(2, "Bình")] }));
    expect(screen.getByRole("status")).toHaveTextContent("Cần thêm 3 người");
    pushState(makeRoom({ members: [member(1, "alice"), member(2, "Bình"), member(3, "C"), member(4, "D"), member(5, "E")] }));
    expect(screen.queryByRole("status")).toBeNull();
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
    render(<RoomView code="ZZZZZ" onExit={() => push("/")} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy phòng");
    fireEvent.click(screen.getByRole("button", { name: /Danh sách phòng/ }));
    expect(push).toHaveBeenCalledWith("/");
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
    render(<RoomView code="ABCDE" onExit={() => push("/")} />);
    expect(screen.getByText("Đang tải phòng…")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("Lobby: Random (host only)", () => {
  it("deals the roles at random when the host presses Random", async () => {
    const user = userEvent.setup();
    await renderRoom(makeRoom());
    api.roles.mockResolvedValue(envelope(makeRoom()) as never);
    await user.click(screen.getByRole("button", { name: /Ngẫu nhiên/ }));
    expect(api.roles).toHaveBeenCalledWith("ABCDE", { random: true });
  });

  it("shows nothing about roles to a player who is not the host", async () => {
    await renderRoom(makeRoom({ isHost: false }));
    expect(screen.queryByRole("button", { name: /Ngẫu nhiên/ })).toBeNull();
  });
});
