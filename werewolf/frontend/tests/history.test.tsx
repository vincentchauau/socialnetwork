import { ApiError } from "@sn/api";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HistoryView from "../app/components/HistoryView";
import { werewolfApi } from "../app/lib/api";
import type { HistoryEntry } from "../app/lib/types";
import { META } from "./helpers";
import { resetApi } from "./mocks";

vi.mock("../app/lib/api", async () => (await import("./apiMock")).apiFactory());

const api = vi.mocked(werewolfApi);

const entry = (extra: Partial<HistoryEntry> = {}): HistoryEntry => ({
  game_id: 17,
  room_id: "ABCDE",
  finished_at: "2026-10-13T08:00:00Z",
  winner: "WOLF",
  days: 4,
  size: 12,
  your_faction: "WOLF",
  your_ability: "KILL",
  your_outcome: "won",
  won: true,
  survived: false,
  days_survived: 3,
  players: [
    { username: "alice", faction: "WOLF", ability: "KILL", outcome: "won", survived: false },
    { username: "bob", faction: "VILLAGER", ability: "NONE", outcome: "lost", survived: true },
  ],
  ...extra,
});

beforeEach(() => resetApi(api as never));

describe("HistoryView", () => {
  it("lists games with faction, ability (Vietnamese label) and outcome", async () => {
    api.history.mockResolvedValue([entry(), entry({ game_id: 16, your_outcome: "lost", won: false, survived: true, winner: "VILLAGER", your_faction: "VILLAGER", your_ability: "NONE" })]);
    render(<HistoryView />);
    const items = await screen.findAllByRole("listitem", {}, { timeout: 2000 });
    const games = items.filter((i) => i.className.includes("ww-history"));
    expect(games).toHaveLength(2);
    expect(games[0]).toHaveTextContent("🏆 Thắng");
    expect(games[0]).toHaveTextContent("🐺 Sói");
    await screen.findByText("Giết trực tiếp");
    expect(games[0]).toHaveTextContent("Phòng ABCDE · 12 người · 4 đêm · chết sau 3 đêm · phe Sói thắng");
    expect(games[1]).toHaveTextContent("💔 Thua");
    expect(games[1]).toHaveTextContent("còn sống");
    expect(screen.getByText("2 ván gần nhất · thắng 1")).toBeInTheDocument();
    expect(api.history).toHaveBeenCalledTimes(1);
    expect(api.meta).toHaveBeenCalled();
  });

  it("falls back to a readable ability name when the rules are unavailable", async () => {
    api.meta.mockRejectedValue(new TypeError("offline"));
    api.history.mockResolvedValue([entry({ your_ability: "KILL_ON_DEATH" })]);
    render(<HistoryView />);
    expect(await screen.findByText("kill on death")).toBeInTheDocument();
  });

  it("shows a draw and the participants", async () => {
    const u = userEvent.setup();
    api.history.mockResolvedValue([entry({ winner: "DRAW", your_outcome: "draw", won: false })]);
    render(<HistoryView />);
    expect(await screen.findByText("🤝 Hòa")).toBeInTheDocument();
    expect(screen.getByText(/· hòa/)).toBeInTheDocument();
    await u.click(screen.getByText("Người chơi (2)"));
    const players = screen.getByText(/bob/).closest("ul") as HTMLElement;
    expect(within(players).getAllByRole("listitem")).toHaveLength(2);
    expect(players).toHaveTextContent("alice 🐺 🗡️ · 🏆 Thắng · 💀");
  });

  it("keeps an unparsable date as is", async () => {
    api.history.mockResolvedValue([entry({ finished_at: "hôm qua" })]);
    render(<HistoryView />);
    expect(await screen.findByText("hôm qua")).toBeInTheDocument();
  });

  it("formats a valid date for Vietnam", async () => {
    api.history.mockResolvedValue([entry()]);
    render(<HistoryView />);
    expect(await screen.findByText(/2026/)).toBeInTheDocument();
  });

  it("says when there is nothing yet", async () => {
    render(<HistoryView />);
    expect(await screen.findByText("Bạn chưa chơi ván nào.")).toBeInTheDocument();
  });

  it("shows a Vietnamese error when it cannot load", async () => {
    api.history.mockRejectedValue(new ApiError(429, "Too many"));
    render(<HistoryView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Bạn thao tác quá nhanh");
    expect(screen.queryByText("Đang tải…")).not.toBeInTheDocument();
  });

  it("links back and loads with the rules label map", async () => {
    api.meta.mockResolvedValue(META);
    api.history.mockResolvedValue([]);
    render(<HistoryView />);
    expect(screen.getByText("Đang tải…")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Quay lại/ })).toHaveAttribute("href", "/");
    await screen.findByText("Bạn chưa chơi ván nào.");
  });
});
