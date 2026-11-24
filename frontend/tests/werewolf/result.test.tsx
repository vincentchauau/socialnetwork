import { ApiError } from "@sn/api";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Game, Player } from "../../app/werewolf/lib/types";
import { GHOST, makeGame, makeRoom, player, VILLAGER, WOLF } from "./helpers";
import { api, envelope, push, renderRoom, resetRoomTest } from "./roomHarness";

vi.mock("../../app/werewolf/lib/api", async () => (await import("./apiMock")).apiFactory());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: (path: string) => push(path) }) }));

beforeEach(resetRoomTest);

const KILL = { code: "KILL", label: "Giết trực tiếp" };
const NONE = { code: "NONE", label: "Không có" };

const players: Player[] = [
  player(1, "alice", { faction: VILLAGER, ability: NONE }),
  player(2, "Bình", { alive: false, faction: WOLF, ability: KILL }),
  player(3, "Cường", { faction: VILLAGER, ability: NONE }),
];

const over = (game: Partial<Game> = {}, room = {}) =>
  makeRoom({
    started: true,
    history: { games: 3, VILLAGER: 1, WOLF: 1, GHOST: 0, draw: 1 },
    game: makeGame({ phase: "over", gameOver: true, winner: VILLAGER, players, chatChannel: "public", ...game }),
    ...room,
  });

describe("Result screen", () => {
  it("announces the winning faction, that you won, and the room's win stats", async () => {
    await renderRoom(over());
    expect(screen.getByRole("heading", { name: "Phe Người thắng!" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("🎉 Bạn thắng!");
    expect(screen.getByText(/📊 3 ván · 🧑 1 · 🐺 1 · 👻 0 · 🤝 1/)).toBeInTheDocument();
  });

  it("tells you lost when your final faction is not the winner", async () => {
    await renderRoom(over({ winner: WOLF }));
    expect(screen.getByRole("heading", { name: "Phe Sói thắng!" })).toBeInTheDocument();
    expect(screen.getByText("😢 Bạn thua")).toBeInTheDocument();
  });

  it("handles a ghost victory and a draw", async () => {
    await renderRoom(over({ winner: GHOST }));
    expect(screen.getByRole("heading", { name: "Phe Ma thắng!" })).toBeInTheDocument();
  });

  it("shows a draw", async () => {
    await renderRoom(over({ winner: null }));
    expect(screen.getByRole("heading", { name: "Hòa — không còn ai sống" })).toBeInTheDocument();
    expect(screen.getByText("🤝 Hòa")).toBeInTheDocument();
  });

  it("reveals every player's faction and ability, marking the dead", async () => {
    await renderRoom(over());
    const reveal = screen.getByRole("heading", { name: "Vai của mọi người" }).parentElement as HTMLElement;
    const rows = within(reveal).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("alice ★");
    expect(rows[1]).toHaveTextContent("Bình");
    expect(rows[1]).toHaveTextContent("🐺 Sói · 🗡️ Giết trực tiếp");
    expect(rows[1]).toHaveTextContent("đã chết");
    expect(rows[2]).toHaveTextContent("còn sống");
  });

  it("hides the stats line before any game was recorded", async () => {
    await renderRoom(over({}, { history: { games: 0, VILLAGER: 0, WOLF: 0, GHOST: 0, draw: 0 } }));
    expect(screen.queryByText(/📊/)).not.toBeInTheDocument();
  });

  it("replaces the action panel with the result", async () => {
    await renderRoom(over());
    expect(screen.queryByRole("region", { name: "Hành động" })).not.toBeInTheDocument();
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
  });
});

describe("Rematch and reset", () => {
  it("lets the host start a rematch and shows the fresh game", async () => {
    const u = userEvent.setup();
    await renderRoom(over());
    api.rematch.mockResolvedValue(envelope(makeRoom({ started: true, game: makeGame({ night: 1, players: [player(1, "alice")] }) })));
    await u.click(screen.getByRole("button", { name: /Chơi lại/ }));
    expect(api.rematch).toHaveBeenCalledWith("ABCDE");
    expect(await screen.findByRole("heading", { name: "Đêm 1" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /thắng/ })).not.toBeInTheDocument();
  });

  it("lets the host go back to the lobby", async () => {
    const u = userEvent.setup();
    await renderRoom(over());
    api.reset.mockResolvedValue(envelope(makeRoom()));
    await u.click(screen.getByRole("button", { name: /Về phòng chờ/ }));
    expect(api.reset).toHaveBeenCalledWith("ABCDE");
    expect(await screen.findByRole("button", { name: /Bắt đầu/ })).toBeInTheDocument();
  });

  it("asks guests to wait for the host", async () => {
    await renderRoom(over({}, { isHost: false }));
    expect(screen.getByText("Chờ chủ phòng chơi lại…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Chơi lại|Về phòng chờ/ })).not.toBeInTheDocument();
  });

  it("toasts a refused rematch", async () => {
    const u = userEvent.setup();
    await renderRoom(over());
    api.rematch.mockRejectedValue(new ApiError(409, "Ván chưa kết thúc", { detail: "Ván chưa kết thúc" }));
    await u.click(screen.getByRole("button", { name: /Chơi lại/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ván chưa kết thúc");
  });
});

describe("Log and perspectives (privacy gate)", () => {
  const log = [
    { round: "Đêm 1", text: "Sói cắn Bình" },
    { round: "Ngày 1", text: "Bình bị treo cổ" },
  ];

  it("a living player only sees their own log and cannot peek at other players", async () => {
    await renderRoom(makeRoom({ started: true, game: makeGame({ log: [{ round: "Đêm 1", text: "Bạn đã xem Bình: Sói" }] }) }));
    expect(screen.getByRole("heading", { name: /Nhật ký của bạn/ })).toBeInTheDocument();
    expect(screen.getByText("Bạn đã xem Bình: Sói")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Góc nhìn" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Xem nhật ký theo/)).not.toBeInTheDocument();
    expect(api.perspective).not.toHaveBeenCalled();
  });

  it("a dead player gets the full log and can open another player's perspective", async () => {
    const u = userEvent.setup();
    const dead = { me: { id: 1, name: "alice", alive: false, faction: VILLAGER, ability: NONE }, players, log };
    await renderRoom(makeRoom({ started: true, game: makeGame(dead) }));
    expect(screen.getByRole("heading", { name: /Nhật ký đầy đủ/ })).toBeInTheDocument();
    expect(screen.getByText("Sói cắn Bình")).toBeInTheDocument();
    expect(api.perspective).not.toHaveBeenCalled(); // "all" needs no request

    api.perspective.mockResolvedValue(
      makeGame({
        me: { id: 2, name: "Bình", alive: false, faction: WOLF, ability: KILL },
        players: [player(1, "alice", { faction: VILLAGER }), player(2, "Bình"), player(3, "Cường")],
        log: [{ round: "Đêm 1", text: "Bạn là Sói" }],
      }),
    );
    await u.click(within(screen.getByRole("group", { name: "Góc nhìn" })).getByRole("button", { name: /Bình/ }));
    expect(api.perspective).toHaveBeenCalledWith("ABCDE", 2);
    expect(await screen.findByRole("heading", { name: /Góc nhìn của Bình/ })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Góc nhìn của Bình" })).toHaveTextContent("🐺 Sói · 🗡️ Giết trực tiếp · 💀 Đã chết");
    expect(screen.getByText("Bạn là Sói")).toBeInTheDocument();
    expect(screen.queryByText("Sói cắn Bình")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Góc nhìn của Bình" })).toHaveTextContent("alice 🧑 Người");

    await u.click(within(screen.getByRole("group", { name: "Góc nhìn" })).getByRole("button", { name: /Toàn bộ/ }));
    expect(screen.queryByRole("region", { name: "Góc nhìn của Bình" })).not.toBeInTheDocument();
    expect(screen.getByText("Sói cắn Bình")).toBeInTheDocument();
  });

  it("everyone gets the picker once the game is over", async () => {
    await renderRoom(over({ log }));
    expect(screen.getByRole("group", { name: "Góc nhìn" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Nhật ký đầy đủ/ })).toBeInTheDocument();
  });

  it("tells a perspective with nobody known yet, and shows a refusal", async () => {
    const u = userEvent.setup();
    await renderRoom(over({ log }));
    api.perspective.mockResolvedValueOnce(makeGame({ me: { id: 3, name: "Cường", alive: true, faction: VILLAGER, ability: NONE }, players: [player(3, "Cường")] }));
    await u.click(within(screen.getByRole("group", { name: "Góc nhìn" })).getByRole("button", { name: /Cường/ }));
    expect(await screen.findByText("Chưa biết thêm ai.")).toBeInTheDocument();
    api.perspective.mockRejectedValueOnce(new ApiError(403, "Chưa được xem", { detail: "Chưa được xem" }));
    await u.click(within(screen.getByRole("group", { name: "Góc nhìn" })).getByRole("button", { name: /alice/ }));
    expect(await screen.findByText("Chưa được xem")).toBeInTheDocument();
  });

  it("shows an empty log message", async () => {
    await renderRoom(over({ log: [] }));
    expect(screen.getByText("Chưa có sự kiện.")).toBeInTheDocument();
  });
});
