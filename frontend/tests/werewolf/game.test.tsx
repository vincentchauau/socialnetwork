import { ApiError } from "@sn/api";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Game, GameAction, Player } from "../../app/werewolf/lib/types";
import { GHOST, makeGame, makeRoom, player, VILLAGER, WOLF } from "./helpers";
import { api, envelope, push, pushState, renderRoom, resetRoomTest } from "./roomHarness";

vi.mock("../../app/werewolf/lib/api", async () => (await import("./apiMock")).apiFactory());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: (path: string) => push(path) }) }));

beforeEach(resetRoomTest);

const action = (extra: Partial<GameAction> = {}): GameAction => ({
  kind: "night",
  options: [2, 3],
  submitted: false,
  current: null,
  canAbstain: false,
  ...extra,
});

const running = (game: Partial<Game>, room = {}) => makeRoom({ started: true, game: makeGame(game), ...room });

describe("Night actions", () => {
  it("lets a seer pick a target with their own ability (kind=ability) and shows the choice", async () => {
    const u = userEvent.setup();
    await renderRoom(running({ actions: [action()], waitingFor: 2 }));
    expect(screen.getByRole("heading", { name: /Xem nhóm/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bỏ trắng" })).not.toBeInTheDocument(); // no blank on a night ability
    api.act.mockResolvedValue(envelope(running({ actions: [action({ submitted: true, current: 2 })], waitingFor: 1 })));
    await u.click(screen.getByRole("button", { name: /^Bình/ }));
    expect(api.act).toHaveBeenCalledWith("ABCDE", 2, "ability");
    expect(await screen.findByText("✔ Đã chọn")).toBeInTheDocument();
    expect(screen.getByText(/Bạn chọn:/)).toHaveTextContent("Bình");
    expect(screen.getByText(/Chờ 1 người còn lại/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Cường/ })).not.toBeInTheDocument();
  });

  it("gives a wolf two actions at night: ability and the kill vote (blank allowed)", async () => {
    const u = userEvent.setup();
    const wolfGame = {
      me: { id: 1, name: "alice", alive: true, faction: WOLF, ability: { code: "SEE_FACTION", label: "Xem nhóm" } },
      actions: [action({ kind: "night" }), action({ kind: "wolf", options: [2, 3], canAbstain: true })],
    };
    await renderRoom(running(wolfGame));
    const ability = screen.getByRole("region", { name: /Xem nhóm/ });
    const wolfVote = screen.getByRole("region", { name: /Vote giết/ });
    expect(within(ability).queryByRole("button", { name: "Bỏ trắng" })).not.toBeInTheDocument();
    expect(within(wolfVote).getByRole("button", { name: "Bỏ trắng" })).toBeInTheDocument();

    api.act.mockResolvedValue(envelope(running({ ...wolfGame, actions: [action({ kind: "night", submitted: true, current: 3 }), wolfGame.actions[1]] })));
    await u.click(within(ability).getByRole("button", { name: /^Cường/ }));
    expect(api.act).toHaveBeenLastCalledWith("ABCDE", 3, "ability");
    await waitFor(() => expect(within(screen.getByRole("region", { name: /Xem nhóm/ })).getByText("✔ Đã chọn")).toBeInTheDocument());

    api.act.mockResolvedValue(
      envelope(running({ ...wolfGame, actions: [action({ kind: "night", submitted: true, current: 3 }), action({ kind: "wolf", submitted: true, current: 0, canAbstain: true })] })),
    );
    await u.click(within(screen.getByRole("region", { name: /Vote giết/ })).getByRole("button", { name: "Bỏ trắng" }));
    expect(api.act).toHaveBeenLastCalledWith("ABCDE", 0, "wolf");
    expect(await screen.findByText("Bạn bỏ trắng.")).toBeInTheDocument();
  });

  it("sends the wolf kill vote with kind=wolf", async () => {
    const u = userEvent.setup();
    await renderRoom(running({ me: { id: 1, name: "alice", alive: true, faction: WOLF, ability: { code: "KILL", label: "Giết trực tiếp" } }, actions: [action({ kind: "wolf", canAbstain: true })] }));
    api.act.mockResolvedValue(envelope(running({ actions: [action({ kind: "wolf", submitted: true, current: 2, canAbstain: true })] })));
    await u.click(screen.getByRole("button", { name: /^Bình/ }));
    expect(api.act).toHaveBeenCalledWith("ABCDE", 2, "wolf");
  });

  it("says so when there is nothing to do, and who we wait for", async () => {
    await renderRoom(running({ phase: "night", actions: [], waitingFor: 3 }));
    expect(screen.getByText("😴 Đêm nay bạn không có hành động")).toBeInTheDocument();
    expect(screen.getByText("⏳ Chờ 3 người")).toBeInTheDocument();
  });

  it("explains that a dead player only watches", async () => {
    await renderRoom(running({ me: { id: 1, name: "alice", alive: false, faction: VILLAGER, ability: { code: "NONE", label: "Không có" } }, actions: [] }));
    expect(screen.getByText("👻 Bạn đã chết, đang theo dõi")).toBeInTheDocument();
  });

  it("waits during the day when there is no vote", async () => {
    await renderRoom(running({ phase: "day", night: 2, actions: [], waitingFor: 0 }));
    expect(screen.getByText("⏳ Đang chờ…")).toBeInTheDocument();
  });
});

describe("Day vote and revenge", () => {
  it("votes for a player", async () => {
    const u = userEvent.setup();
    await renderRoom(running({ phase: "day", actions: [action({ kind: "day", canAbstain: true })] }));
    expect(screen.getByRole("heading", { name: /Treo cổ ai/ })).toBeInTheDocument();
    api.act.mockResolvedValue(envelope(running({ phase: "day", actions: [action({ kind: "day", submitted: true, current: 3, canAbstain: true })] })));
    await u.click(screen.getByRole("button", { name: /^Cường/ }));
    expect(api.act).toHaveBeenCalledWith("ABCDE", 3, "ability");
  });

  it("allows a blank vote", async () => {
    const u = userEvent.setup();
    await renderRoom(running({ phase: "day", actions: [action({ kind: "day", canAbstain: true })] }));
    api.act.mockResolvedValue(envelope(running({ phase: "day", actions: [action({ kind: "day", submitted: true, current: 0, canAbstain: true })] })));
    await u.click(screen.getByRole("button", { name: "Bỏ trắng" }));
    expect(api.act).toHaveBeenCalledWith("ABCDE", 0, "ability");
    expect(await screen.findByText("Bạn bỏ trắng.")).toBeInTheDocument();
  });

  it("lets a dying hunter take someone along", async () => {
    const u = userEvent.setup();
    await renderRoom(running({ phase: "revenge", actions: [action({ kind: "revenge" })] }));
    expect(screen.getByRole("heading", { name: "Kéo theo!" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Kéo theo ai/ })).toBeInTheDocument();
    api.act.mockResolvedValue(envelope(running({ phase: "revenge", actions: [action({ kind: "revenge", submitted: true, current: 2 })] })));
    await u.click(screen.getByRole("button", { name: /^Bình/ }));
    expect(api.act).toHaveBeenCalledWith("ABCDE", 2, "ability");
  });

  it("toasts the server's refusal (wrong phase) and keeps the options", async () => {
    const u = userEvent.setup();
    await renderRoom(running({ actions: [action()] }));
    api.act.mockRejectedValue(new ApiError(400, "Chưa tới lượt hành động", { detail: "Chưa tới lượt hành động" }));
    await u.click(screen.getByRole("button", { name: /^Bình/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chưa tới lượt hành động");
    expect(screen.getByRole("button", { name: /^Bình/ })).toBeEnabled();
  });

  it("ignores an option id that is not a known player", async () => {
    await renderRoom(running({ actions: [action({ options: [2, 99] })] }));
    expect(screen.getAllByRole("button", { name: /còn sống/ })).toHaveLength(1);
  });
});

describe("Host skip", () => {
  it("shows 'Bỏ qua người chưa chọn' to the host and forces the turn", async () => {
    const u = userEvent.setup();
    await renderRoom(running({ waitingFor: 2 }));
    api.force.mockResolvedValue(envelope(running({ waitingFor: 0, phase: "day" })));
    await u.click(screen.getByRole("button", { name: /Bỏ qua người chưa chọn/ }));
    expect(api.force).toHaveBeenCalledWith("ABCDE");
    expect(await screen.findByRole("heading", { name: "Ngày 1" })).toBeInTheDocument();
  });

  it("disables it when nobody is pending", async () => {
    await renderRoom(running({ waitingFor: 0 }));
    expect(screen.getByRole("button", { name: /Bỏ qua người chưa chọn/ })).toBeDisabled();
  });

  it("hides it from guests and after the game", async () => {
    await renderRoom(running({ waitingFor: 2 }, { isHost: false }));
    expect(screen.queryByRole("button", { name: /Bỏ qua/ })).not.toBeInTheDocument();
    pushState(running({ gameOver: true, phase: "over", waitingFor: 2 }, { isHost: true }));
    expect(screen.queryByRole("button", { name: /Bỏ qua/ })).not.toBeInTheDocument();
  });
});

describe("Phase, timer, events, recap", () => {
  it("shows the phase, room title, code and a countdown that runs", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      await renderRoom(running({ timer: { total: 60, secondsLeft: 41.5 } }));
      expect(screen.getByText(/Làng Trăng Máu · 🔑 ABCDE/)).toBeInTheDocument();
      expect(screen.getByRole("timer")).toHaveAccessibleName("Còn 42 giây");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(35_000);
      });
      expect(screen.getByRole("timer")).toHaveClass("ww-urgent");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20_000);
      });
      expect(screen.getByRole("timer")).toHaveAccessibleName("Còn 0 giây");
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows no countdown without a timer or after the game", async () => {
    await renderRoom(running({ timer: { total: 60, secondsLeft: 10 }, gameOver: true, phase: "over", winner: WOLF }));
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
  });

  it("shows the night's event card", async () => {
    await renderRoom(running({ event: { code: "FOG", icon: "🌫️", title: "Sương mù", text: "Không ai thấy gì.", affectsDay: false } }));
    expect(screen.getByRole("region", { name: "Sự kiện: Sương mù. Không ai thấy gì." })).toBeInTheDocument();
  });

  it("shows the dawn card when a new recap arrives (not the one already there), and hides it on click", async () => {
    const u = userEvent.setup();
    const first = { seq: 1, kind: "dawn" as const, round: 1, deaths: [{ id: 2, name: "Bình", cause: "bị giết ban đêm" }] };
    await renderRoom(running({ recap: first }));
    expect(screen.queryByRole("region", { name: /Bình minh/ })).not.toBeInTheDocument();
    const second = {
      seq: 2,
      kind: "dawn" as const,
      round: 2,
      deaths: [{ id: 3, name: "Cường", cause: "bị treo cổ", revealed: { faction: WOLF, ability: { code: "KILL", label: "Giết trực tiếp" } } }],
    };
    pushState(running({ recap: second }));
    const card = await screen.findByRole("region", { name: "Bình minh, Ngày 2" });
    expect(card).toHaveTextContent("Cường đã chết [bị treo cổ]");
    expect(card).toHaveTextContent("Lộ diện: 🐺 Sói · 🗡️ Giết trực tiếp");
    await u.click(within(card).getByRole("button", { name: "Ẩn thẻ tóm tắt" }));
    expect(screen.queryByRole("region", { name: /Bình minh/ })).not.toBeInTheDocument();
  });

  it("shows the dusk card with nobody dead, and removes it after a few seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      await renderRoom(running({ recap: { seq: 1, kind: "dusk", round: 1, deaths: [] } }));
      pushState(running({ recap: { seq: 2, kind: "dusk", round: 2, deaths: [] } }));
      const card = screen.getByRole("region", { name: "Hoàng hôn, Đêm 2" });
      expect(card).toHaveTextContent("Không ai chết.");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6_100);
      });
      expect(screen.queryByRole("region", { name: /Hoàng hôn/ })).not.toBeInTheDocument();
      pushState(running({ recap: { seq: 2, kind: "dusk", round: 2, deaths: [] } })); // same seq: no replay
      expect(screen.queryByRole("region", { name: /Hoàng hôn/ })).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("Players and privacy of what is shown", () => {
  it("shows your role and every player with alive/dead and only the roles the server told us", async () => {
    const players: Player[] = [
      player(1, "alice", { faction: VILLAGER, ability: { code: "SEE_FACTION", label: "Xem nhóm" } }),
      player(2, "Bình", { alive: false, faction: WOLF, ability: { code: "KILL", label: "Giết trực tiếp" } }),
      player(3, "Cường"),
    ];
    await renderRoom(running({ players }));
    const grid = screen.getByRole("region", { name: "Người chơi" });
    expect(within(grid).getByRole("heading", { name: /2\/3 còn sống/ })).toBeInTheDocument();
    expect(within(grid).getByLabelText("alice (bạn), còn sống, phe Người, Xem nhóm")).toBeInTheDocument();
    expect(within(grid).getByLabelText("Bình, đã chết, phe Sói, Giết trực tiếp")).toBeInTheDocument();
    expect(within(grid).getByLabelText("Cường, còn sống")).toBeInTheDocument(); // no faction, no ability: nothing invented
    const role = screen.getByRole("region", { name: "Vai của bạn" });
    expect(role).toHaveTextContent("alice");
    expect(role).toHaveTextContent("🧑 Người · 👁️ Xem nhóm");
  });

  it("marks you as dead in the role card", async () => {
    await renderRoom(running({ me: { id: 1, name: "alice", alive: false, faction: GHOST, ability: { code: "TRANSFORM", label: "Biến hình" } } }));
    expect(screen.getByRole("region", { name: "Vai của bạn" })).toHaveTextContent("💀 Đã chết");
  });
});
