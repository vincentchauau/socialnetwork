export { errorText } from "@sn/api";

export const API = "/api/roulette";

export type BetKind = "straight" | "split" | "street" | "corner" | "line" | "red" | "black" | "odd" | "even" | "low" | "high" | "dozen" | "column";

interface Bet {
  kind: BetKind;
  pick: number | null;
  amount: number;
}

export interface BetResult extends Bet {
  payout: number;
}

export interface SpinResult {
  id: number;
  number: number;
  colour: "red" | "black" | "green";
  bets: BetResult[];
  stake: number;
  payout: number;
  balance_after: number;
  created_at: string;
}

export interface Wallet {
  chips: number;
  max_bet: number;
  max_bets: number;
}

export interface Leader {
  username: string;
  chips: number;
}

export const CHIP_VALUES = [1, 5, 25, 100] as const;

const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);

export function colourOf(number: number): "red" | "black" | "green" {
  if (number === 0) return "green";
  return RED.has(number) ? "red" : "black";
}

/** Does the bet win when the ball stops at `number`? (the rules of the server, to show the winning places) */
export function hits(kind: BetKind, pick: number | null, number: number): boolean {
  if (number === 0) return (kind === "straight" && pick === 0) || (kind === "split" && pick !== null && pick < 100);
  const at = pick ?? 0;
  switch (kind) {
    case "straight": return at === number;
    case "split": return Math.floor(at / 100) === number || at % 100 === number;
    case "street": return number >= at && number <= at + 2;
    case "corner": return [at, at + 1, at + 3, at + 4].includes(number);
    case "line": return number >= at && number <= at + 5;
    case "red": case "black": return colourOf(number) === kind;
    case "odd": return number % 2 === 1;
    case "even": return number % 2 === 0;
    case "low": return number <= 18;
    case "high": return number >= 19;
    case "dozen": return Math.floor((number - 1) / 12) + 1 === at;
    default: return ((number - 1) % 3) + 1 === at;
  }
}

/** The pick of a split between two numbers: the low one times 100 plus the high one (0 and 3 is 3). */
export function splitPick(a: number, b: number): number {
  return Math.min(a, b) * 100 + Math.max(a, b);
}

/** One key for each place on the table a chip can lie: `straight:17`, `red`, `dozen:2`. */
export function betKey(kind: BetKind, pick: number | null): string {
  return pick === null ? kind : `${kind}:${pick}`;
}

export function parseKey(key: string): { kind: BetKind; pick: number | null } {
  const [kind, pick] = key.split(":");
  return { kind: kind as BetKind, pick: pick === undefined ? null : Number(pick) };
}

/** The chips on the table (key -> amount) as the bets the server takes. */
export function toBets(placed: Readonly<Record<string, number>>): Bet[] {
  return Object.entries(placed).map(([key, amount]) => ({ ...parseKey(key), amount }));
}

export function totalOf(placed: Readonly<Record<string, number>>): number {
  return Object.values(placed).reduce((sum, amount) => sum + amount, 0);
}

/** `placed` with `value` more on a place, never above the limit of a bet and never above what the person has left. */
export function addChip(placed: Readonly<Record<string, number>>, key: string, value: number, maxBet: number, chips: number): Record<string, number> {
  const room = Math.min(maxBet - (placed[key] ?? 0), chips - totalOf(placed));
  const add = Math.min(value, room);
  return add > 0 ? { ...placed, [key]: (placed[key] ?? 0) + add } : { ...placed };
}

export interface NumberCount {
  number: number;
  colour: "red" | "black" | "green";
  count: number;
}

export interface Stats {
  spins: number;
  hot: NumberCount[];
  cold: NumberCount[];
}

/** The chips of `bets` on the table again (the same places and amounts), cut down to the limit of a bet and to the chips that are left. */
export function placedFrom(bets: readonly Bet[], maxBet: number, chips: number): Record<string, number> {
  let placed: Record<string, number> = {};
  for (const bet of bets) placed = addChip(placed, betKey(bet.kind, bet.pick), bet.amount, maxBet, chips);
  return placed;
}

/** Every bet on the table with as many chips again, cut down in the same way. */
export function doubled(placed: Readonly<Record<string, number>>, maxBet: number, chips: number): Record<string, number> {
  return placedFrom(toBets(placed).map((bet) => ({ ...bet, amount: bet.amount * 2 })), maxBet, chips);
}
