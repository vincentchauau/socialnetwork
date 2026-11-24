import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@sn/lib/i18n";
import Leaderboard from "../../app/werewolf/components/Leaderboard";
import { werewolfApi } from "../../app/werewolf/lib/api";

vi.mock("../../app/werewolf/lib/api", () => ({ werewolfApi: { leaderboard: vi.fn() }, WEREWOLF_API: "/api/werewolf" }));
const api = vi.mocked(werewolfApi);

beforeEach(() => api.leaderboard.mockReset());
const show = () => render(<LocaleProvider><Leaderboard /></LocaleProvider>);

describe("Leaderboard", () => {
  it("lists the people in the order the server gave, with their wins and games", async () => {
    api.leaderboard.mockResolvedValue([{ username: "alice", games: 4, wins: 3 }, { username: "bob", games: 2, wins: 1 }]);
    show();
    const items = await screen.findAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([expect.stringContaining("alice"), expect.stringContaining("bob")]);
    expect(items[0]).toHaveTextContent(/3.*4/);
  });

  it("asks for the season of this month first and for all games when the person picks All", async () => {
    api.leaderboard.mockResolvedValue([]);
    show();
    expect(await screen.findByText(/Chưa có ai thắng/)).toBeInTheDocument();
    expect(api.leaderboard).toHaveBeenLastCalledWith("month");
    await userEvent.click(screen.getByRole("button", { name: "Tất cả" }));
    await vi.waitFor(() => expect(api.leaderboard).toHaveBeenLastCalledWith("all"));
  });

  it("shows the empty season note when the answer is no list", async () => {
    api.leaderboard.mockResolvedValue(undefined as never); // an answer that is no list at all
    show();
    expect(await screen.findByText(/Chưa có ai thắng/)).toBeInTheDocument();
  });
});
