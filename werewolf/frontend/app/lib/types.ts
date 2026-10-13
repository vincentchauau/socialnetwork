/** Types of the werewolf contract (see werewolf/API.md). */

export type FactionCode = "VILLAGER" | "WOLF" | "GHOST";
export type Phase = "night" | "revenge" | "day" | "settle" | "over";
export type ChatChannel = "public" | "wolf" | "dead";
export type ActionKind = "night" | "wolf" | "day" | "revenge";

export interface Coded<C extends string = string> {
  code: C;
  label: string;
}
export type Faction = Coded<FactionCode>;
export type Ability = Coded;

export interface Member {
  seat: number;
  name: string;
  isBot: boolean;
  isHost: boolean;
  isYou: boolean;
  faction: Faction | null;
  ability: Ability | null;
}

export interface Player {
  id: number;
  name: string;
  alive: boolean;
  isBot: boolean;
  faction: Faction | null;
  ability: Ability | null;
}

export interface Me {
  id: number;
  name: string;
  alive: boolean;
  faction: Faction;
  ability: Ability;
}

export interface GameAction {
  kind: ActionKind;
  options: number[];
  submitted: boolean;
  current: number | null;
  canAbstain: boolean;
}

export interface LogEntry {
  round: string;
  text: string;
}

export interface NightEvent {
  code: string;
  icon: string;
  title: string;
  text: string;
  affectsDay: boolean;
}

export interface Death {
  id: number;
  name: string;
  cause: string;
  revealed?: { faction: Faction; ability: Ability } | null;
}

export interface Recap {
  seq: number;
  kind: "dawn" | "dusk";
  round: number;
  deaths: Death[];
}

export interface ChatMessage {
  seq: number;
  round: string;
  channel: ChatChannel;
  text: string;
  target: number;
  dead: boolean;
  author: { id: number; name: string };
}

export interface Game {
  phase: Phase;
  night: number;
  gameOver: boolean;
  winner: Faction | null;
  me: Me;
  players: Player[];
  actions: GameAction[];
  waitingFor: number;
  log: LogEntry[];
  event: NightEvent | null;
  recap: Recap | null;
  timer: { total: number; secondsLeft: number } | null;
  chat: ChatMessage[];
  chatChannel: ChatChannel | null;
}

export interface RoomHistory {
  games: number;
  VILLAGER: number;
  WOLF: number;
  GHOST: number;
  draw: number;
}

export interface RoomState {
  code: string;
  title: string;
  isHost: boolean;
  you: { username: string; seat: number } | null;
  minPlayers: number;
  maxPlayers: number;
  members: Member[];
  timer: number;
  events: boolean;
  deadTalk: boolean;
  listed: boolean;
  history: RoomHistory;
  started: boolean;
  game: Game | null;
}

export interface RoomEnvelope {
  id: string;
  state: RoomState;
}

export interface RoomSummary {
  id: string;
  title: string;
  host: string;
  players: number;
  seats: number;
  open_seats: number;
  max_players: number;
  timer: number;
  events: boolean;
}

export interface SetupSeat {
  faction: FactionCode;
  ability: string;
}

export interface SeatDraft extends SetupSeat {
  name: string;
}

export interface DefaultChip {
  icon: string;
  label: string;
  hint: string;
}

export interface AbilityMeta {
  code: string;
  label: string;
  help: string;
  allowedFactions: FactionCode[];
}

export interface SetupMeta {
  minPlayers: number;
  maxPlayers: number;
  maxRoomsPerUser: number;
  defaults: Record<FactionCode, DefaultChip[]>;
  factions: Faction[];
  abilities: AbilityMeta[];
  help: {
    rules: { icon: string; title: string; text: string }[];
    events: { code: string; icon: string; title: string; text: string; affectsDay: boolean }[];
  };
  timerOptions: number[];
  timerRange: [number, number];
  chat: { maxLength: number; minIntervalSeconds: number; keep: number };
}

export interface CreateBody {
  count?: number;
  seats?: SetupSeat[];
  roomName?: string;
  roomCode?: string;
  start?: boolean;
  timerSeconds?: number;
  events?: boolean;
  deadTalk?: boolean;
  listed?: boolean;
}

export interface HistoryPlayer {
  username: string;
  faction: FactionCode;
  ability: string;
  outcome: "won" | "draw" | "lost";
  survived: boolean;
}

export interface HistoryEntry {
  game_id: number;
  room_id: string;
  finished_at: string;
  winner: FactionCode | "DRAW";
  days: number;
  size: number;
  your_faction: FactionCode;
  your_ability: string;
  your_outcome: "won" | "draw" | "lost";
  won: boolean;
  survived: boolean;
  days_survived: number;
  players: HistoryPlayer[];
}

export type ServerFrame =
  | { type: "state"; state: RoomState }
  | { type: "chat"; message: ChatMessage }
  | { type: "error"; error: string };
