import { apiFetch } from "@sn/api";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoulettePage from "../_pages/roulette";
import { addChip, betKey, colourOf, doubled, hits, parseKey, placedFrom, splitPick, toBets, totalOf } from "../../app/roulette/lib";

vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 1, username: "alice", group: "user" } }) }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);
const outcome = { id: 7, number: 17, colour: "black", bets: [{ kind: "black", pick: null, amount: 5, payout: 10 }], stake: 5, payout: 10, balance_after: 1005, created_at: "2025-01-01T00:00:00Z" };

beforeEach(() => {
  api.mockReset();
  api.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/wallet")) return { chips: 1000, max_bet: 500, max_bets: 20 };
    if (url.endsWith("/board")) return [{ username: "alice", chips: 1000 }];
    if (url.endsWith("/stats")) return { spins: 3, hot: [{ number: 17, colour: "black", count: 2 }], cold: [{ number: 1, colour: "red", count: 0 }] };
    if (url.endsWith("/spins")) return [outcome];
    if (url.endsWith("/spin") && init?.method === "POST") return outcome;
    return [];
  });
});

describe("the helpers of the table", () => {
  it("knows the colours of the wheel", () => {
    expect([0, 1, 2, 36].map(colourOf)).toEqual(["green", "red", "black", "red"]);
  });

  it("keeps a place as a key and back", () => {
    expect(betKey("straight", 17)).toBe("straight:17");
    expect(betKey("red", null)).toBe("red");
    expect(parseKey("dozen:2")).toEqual({ kind: "dozen", pick: 2 });
    expect(parseKey("odd")).toEqual({ kind: "odd", pick: null });
  });

  it("puts chips on places, never above the limit of a bet or the chips that are left", () => {
    let placed = addChip({}, "red", 100, 150, 1000);
    placed = addChip(placed, "red", 100, 150, 1000);
    expect(placed).toEqual({ red: 150 });
    expect(addChip({ red: 90 }, "black", 25, 500, 100)).toEqual({ red: 90, black: 10 });
    expect(addChip({ red: 100 }, "black", 25, 500, 100)).toEqual({ red: 100 });
    expect(totalOf({ a: 1, b: 2 })).toBe(3);
    expect(toBets({ "straight:3": 5, red: 2 })).toEqual([{ kind: "straight", pick: 3, amount: 5 }, { kind: "red", pick: null, amount: 2 }]);
  });
});

describe("rebet and double", () => {
  it("puts an earlier spin on the table again, cut down to the chips that are left", () => {
    const bets = [{ kind: "red" as const, pick: null, amount: 300 }, { kind: "straight" as const, pick: 7, amount: 300 }];
    expect(placedFrom(bets, 500, 1000)).toEqual({ red: 300, "straight:7": 300 });
    expect(placedFrom(bets, 500, 400)).toEqual({ red: 300, "straight:7": 100 });
  });

  it("doubles every bet, never above the limit of a bet or the chips", () => {
    expect(doubled({ red: 100, "straight:3": 5 }, 500, 1000)).toEqual({ red: 200, "straight:3": 10 });
    expect(doubled({ red: 300 }, 500, 1000)).toEqual({ red: 500 });
    expect(doubled({ red: 100, black: 100 }, 500, 300)).toEqual({ red: 200, black: 100 });
  });
});

describe("the bets on more than one number", () => {
  it("names a split by its two numbers", () => {
    expect(splitPick(8, 5)).toBe(508);
    expect(splitPick(3, 0)).toBe(3);
  });

  it("wins on the numbers that it covers", () => {
    expect([5, 8, 9].map((n) => hits("split", 508, n))).toEqual([true, true, false]);
    expect(hits("split", 1, 0)).toBe(true); // 0 and 1
    expect(hits("street", 4, 6)).toBe(true);
    expect(hits("corner", 5, 9)).toBe(true);
    expect(hits("corner", 5, 7)).toBe(false);
    expect(hits("line", 4, 9)).toBe(true);
    expect(hits("red", null, 0)).toBe(false);
  });
});

describe("the roulette page", () => {
  it("shows the chips, and spin waits for a bet", async () => {
    render(<RoulettePage />);
    expect(await screen.findByText(/Chip: 1000/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Quay" })).toBeDisabled();
  });

  it("places a chip, spins, and shows the number and what was won", async () => {
    const user = userEvent.setup();
    render(<RoulettePage />);
    await screen.findByText(/Chip: 1000/);
    await user.click(screen.getByRole("button", { name: /Đặt vào Đen/ }));
    expect(screen.getByRole("button", { name: /Đặt vào Đen \(5\)/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Quay" }));
    const status = await screen.findByRole("status", {}, { timeout: 4000 });
    expect(status).toHaveTextContent("17");
    expect(status).toHaveTextContent("Bạn thắng 5");
    const call = api.mock.calls.find(([url]) => String(url).endsWith("/spin"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ bets: [{ kind: "black", pick: null, amount: 5 }] });
    await waitFor(() => expect(screen.getByRole("button", { name: "Quay" })).toBeDisabled()); // the table is clear again
  });

  it("shows the bets of an earlier spin and the hot and cold numbers", async () => {
    const user = userEvent.setup();
    render(<RoulettePage />);
    await user.click(await screen.findByText(/Cược \(1\)/));
    expect(screen.getByText(/Đen · 5/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Gần đây" })).toHaveTextContent("17");
    expect(screen.getByRole("listitem", { name: "17 (2 lần)" })).toBeInTheDocument(); // hot
    expect(screen.getByRole("list", { name: "Số lạnh" })).toHaveTextContent("1");
  });

  it("rebets the last spin, then doubles what is on the table", async () => {
    const user = userEvent.setup();
    render(<RoulettePage />);
    await screen.findByText(/Chip: 1000/);
    await user.click(screen.getByRole("button", { name: "Đặt lại" }));
    expect(screen.getByRole("button", { name: /Đặt vào Đen \(5\)/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Nhân đôi" }));
    expect(screen.getByRole("button", { name: /Đặt vào Đen \(10\)/ })).toBeInTheDocument();
  });

  it("offers new chips when there are none left", async () => {
    api.mockImplementation(async (url: string) => (url.endsWith("/wallet") ? { chips: 0, max_bet: 500, max_bets: 20 } : url.endsWith("/stats") ? { spins: 0, hot: [], cold: [] } : []));
    render(<RoulettePage />);
    expect(await screen.findByRole("button", { name: "Nhận 1000 chip" })).toBeInTheDocument();
  });

  it("puts a chip on a split between two numbers and sends it", async () => {
    const user = userEvent.setup();
    render(<RoulettePage />);
    await screen.findByText(/Chip: 1000/);
    await user.click(screen.getByRole("button", { name: /Đặt vào Chia đôi 5\/6/ }));
    await user.click(screen.getByRole("button", { name: "Quay" }));
    await screen.findByRole("status", {}, { timeout: 4000 });
    const call = api.mock.calls.find(([url]) => String(url).endsWith("/spin"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ bets: [{ kind: "split", pick: 506, amount: 5 }] });
  });
});
