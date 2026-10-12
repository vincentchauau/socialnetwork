export type Phase = "lobby" | "night" | "day" | "vote" | "finished";
export type Role = "villager" | "werewolf" | "seer" | "doctor";
export type PendingAction = "kill" | "inspect" | "protect" | "vote";
export type ChatScope = "all" | "wolves";

export interface PlayerView {
  id: number;
  username: string;
  alive: boolean;
  left: boolean;
  is_host: boolean;
  role: Role | null;
}

export interface EventView {
  day: number;
  kind: string;
  player: string | null;
  role: Role | null;
}

export interface YouView {
  id: number;
  role: Role | null;
  alive: boolean;
  pending: PendingAction | null;
  target: number | null;
  chat: ChatScope | null;
  inspections?: { id: number; is_werewolf: boolean }[];
  blocked_target?: number | null;
}

export interface GameState {
  version: number;
  phase: Phase;
  day: number;
  host_id: number;
  winner: "village" | "wolves" | null;
  players: PlayerView[];
  events: EventView[];
  you: YouView | null;
}

export interface RoomSummary {
  id: string;
  host: string;
  players: number;
  max_players: number;
}

export interface HistoryEntry {
  room_id: string;
  finished_at: string;
  winner: string;
  days: number;
  your_role: string;
  won: boolean;
  players: { username: string; role: string; survived: boolean }[];
}

export interface ChatLine {
  key: number;
  scope: ChatScope;
  username: string;
  content: string;
}

export type ServerEvent =
  | { type: "state"; state: GameState }
  | { type: "chat"; scope: ChatScope; username: string; content: string }
  | { type: "error"; error: string };

export const MIN_PLAYERS = 5;
export const MAX_CHAT_LENGTH = 500;
export const MAX_CHAT_LINES = 200;

const ROLE_LABELS: Record<Role, string> = {
  villager: "Villager",
  werewolf: "Werewolf",
  seer: "Seer",
  doctor: "Doctor",
};

const ROLE_HINTS: Record<Role, string> = {
  villager: "Find the werewolves and vote them out in the day.",
  werewolf: "Each night, agree with the other wolves on a victim. Avoid suspicion by day.",
  seer: "Each night, learn whether one player is a werewolf.",
  doctor: "Each night, protect one player from the wolves. Not the same one twice in a row.",
};

const PHASE_LABELS: Record<Phase, string> = {
  lobby: "Lobby",
  night: "Night",
  day: "Day: discussion",
  vote: "Day: vote",
  finished: "Game over",
};

const ACTION_LABELS: Record<PendingAction, string> = {
  kill: "Attack",
  inspect: "Inspect",
  protect: "Protect",
  vote: "Vote",
};

export const roleLabel = (role: Role | null): string => (role ? ROLE_LABELS[role] : "Unknown");
export const roleHint = (role: Role | null): string => (role ? ROLE_HINTS[role] : "");
/** Keep the newer of two snapshots: broadcasts can arrive out of order, so older versions are dropped. */
export function newerState(current: GameState | null, incoming: GameState): GameState {
  return current !== null && incoming.version < current.version ? current : incoming;
}

export const phaseLabel = (phase: Phase): string => PHASE_LABELS[phase];
export const actionLabel = (action: PendingAction): string => ACTION_LABELS[action];

/** Whether the "target" button next to this player should be enabled for the viewer. */
export function canTarget(state: GameState, player: PlayerView): boolean {
  const you = state.you;
  if (!you || !you.alive || !you.pending || !player.alive || player.left) return false;
  if (player.id === you.id) {
    return you.pending === "protect";
  }
  if (you.pending === "kill") return player.role !== "werewolf";
  if (you.pending === "protect" && player.id === you.blocked_target) return false;
  return true;
}

export function describeEvent(event: EventView): string {
  const who = event.player ?? "Someone";
  const role = event.role ? ` (${roleLabel(event.role)})` : "";
  switch (event.kind) {
    case "night_death":
      return `Night ${event.day}: ${who}${role} was killed.`;
    case "peaceful_night":
      return `Night ${event.day}: nobody died.`;
    case "lynch":
      return `Day ${event.day}: ${who}${role} was voted out.`;
    case "no_lynch":
      return `Day ${event.day}: no one was voted out.`;
    case "left":
      return `${who}${role} left the game.`;
    case "game_over":
      return "The game is over.";
    default:
      return "";
  }
}

export function winnerLabel(winner: GameState["winner"]): string {
  if (winner === "village") return "The village wins!";
  if (winner === "wolves") return "The werewolves win!";
  return "";
}

/** Everyone who is not a wolf you know of, for the night-kill prompt. */
export function statusLine(state: GameState): string {
  const you = state.you;
  if (!you) return "";
  if (state.phase === "finished") return winnerLabel(state.winner);
  if (!you.alive) return "You are dead. You can watch, but not act or speak.";
  if (you.pending && state.phase === "night") {
    return `Choose a player to ${actionLabel(you.pending).toLowerCase()}.`;
  }
  if (you.pending === "vote") return "Cast your vote, or abstain.";
  if (state.phase === "night") return "Night falls. Wait for the others.";
  if (state.phase === "vote") return "Waiting for the other votes.";
  if (state.phase === "day") return "Discuss who might be a werewolf.";
  return "";
}

/** Parse a server frame; null when it is not one of the known shapes. */
export function parseServerEvent(raw: string): ServerEvent | null {
  try {
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null || !("type" in data)) return null;
    if (data.type === "state" && "state" in data) return data as ServerEvent;
    if (data.type === "chat" && "content" in data && "username" in data) return data as ServerEvent;
    if (data.type === "error" && "error" in data && typeof data.error === "string") {
      return data as ServerEvent;
    }
  } catch {
    // not JSON
  }
  return null;
}

/** Append a chat line, keeping only the newest MAX_CHAT_LINES. */
export function appendChat(lines: readonly ChatLine[], line: ChatLine): ChatLine[] {
  return [...lines, line].slice(-MAX_CHAT_LINES);
}
