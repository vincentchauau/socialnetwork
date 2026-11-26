import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Leaderboard from "../../app/werewolf/components/Leaderboard";
import { werewolfApi } from "../../app/werewolf/lib/api";

vi.mock("../../app/werewolf/lib/api", async () => (await import("./apiMock")).apiFactory());

beforeEach(() => {
  vi.clearAllMocks();
});

describe("the Werewolf leaderboard", () => {
  it("shows this month first, and asks for all the time when the person picks it", async () => {
    vi.mocked(werewolfApi.leaderboard)
      .mockResolvedValueOnce([{ username: "ann", games: 4, wins: 3 }])
      .mockResolvedValueOnce([]);
    render(<Leaderboard />);

    expect(await screen.findByText("ann")).toBeInTheDocument();
    expect(werewolfApi.leaderboard).toHaveBeenLastCalledWith("month");

    await userEvent.selectOptions(screen.getByRole("combobox"), "all");
    expect(await screen.findByText(/Chưa có ván nào/)).toBeInTheDocument();
    expect(werewolfApi.leaderboard).toHaveBeenLastCalledWith("all");
  });

  it("says when the ranking cannot be loaded", async () => {
    vi.mocked(werewolfApi.leaderboard).mockRejectedValueOnce(new Error("down"));
    render(<Leaderboard />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/Không tải được|Could not load/);
  });
});
