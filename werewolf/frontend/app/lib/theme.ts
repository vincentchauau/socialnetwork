import type { FactionCode } from "./types";

export const FACTION_ICON: Record<FactionCode, string> = { VILLAGER: "🧑", WOLF: "🐺", GHOST: "👻" };

const ABILITY_ICON: Record<string, string> = {
  NONE: "⚪",
  KILL: "🗡️",
  KILL_ON_DEATH: "🏹",
  BLOCK_EFFECTS: "🛡️",
  REVERSE_EFFECTS: "🔁",
  BLOCK_ABILITY: "🚫",
  REVERSE_ABILITY: "🔄",
  SEE_FACTION: "👁️",
  SEE_ABILITY: "🔍",
  REVEAL_ON_DEATH: "📢",
  TRANSFORM: "✨",
};

export function abilityIcon(code: string): string {
  return ABILITY_ICON[code] ?? "❔";
}

const ANIMALS = [
  "🦊", "🐻", "🐼", "🐨", "🐯", "🦁", "🐸", "🐵", "🐔", "🐧",
  "🦉", "🦄", "🐙", "🐰", "🐶", "🐱", "🐹", "🐷", "🦝", "🦔",
];

/** The same name always gets the same animal. */
export function animalFor(name: string): string {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + (ch.codePointAt(0) ?? 0)) >>> 0;
  return ANIMALS[hash % ANIMALS.length];
}

export interface PhaseInfo {
  icon: string;
  title: (night: number) => string;
  tone: "night" | "day" | "revenge" | "settle" | "over";
}

export const PHASE_INFO: Record<string, PhaseInfo> = {
  night: { icon: "🌙", title: (n) => `Đêm ${n}`, tone: "night" },
  day: { icon: "☀️", title: (n) => `Ngày ${n}`, tone: "day" },
  revenge: { icon: "🏹", title: () => "Kéo theo!", tone: "revenge" },
  settle: { icon: "⏳", title: () => "…", tone: "settle" },
  over: { icon: "🏆", title: () => "Kết thúc", tone: "over" },
};
