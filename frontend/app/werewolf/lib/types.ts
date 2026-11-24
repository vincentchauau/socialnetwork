/** Types of the werewolf contract (see werewolf/API.md). */

export type FactionCode = "VILLAGER" | "WOLF" | "GHOST";
export type Phase = "night" | "revenge" | "day" | "settle" | "over";
export type ChatChannel = "public" | "wolf" | "dead";
export type ActionKind = "night" | "wolf" | "day" | "revenge";

interface Coded<C extends string = string> {
  code: C;
  label: string;
}
export type Faction = Coded<FactionCode>;
export type Ability = Coded;

export interface Member {
  seat: number;
  name: string;
  isBot: boolean;
  /** For a seat the machine plays: who it is for: a virtual person of the room, a person of the room who has not sat yet, or nobody (a filler). */
  origin?: "virtual" | "human" | "";
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

/** The role set for one seat before the game (only the host is told), as the server words it. */
export interface SeatRole {
  faction: { code: FactionCode; label: string };
  ability: { code: string; label: string };
}

/** One seat of the setup, as it is sent. */
export interface SetupSeat {
  faction: FactionCode;
  ability: string;
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
  /** For the host before the game: the role set for each seat (null where it is left to be dealt at the start). */
  setup?: (SeatRole | null)[];
  game: Game | null;
}

export interface RoomEnvelope {
  id: string;
  state: RoomState;
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
  /** The abilities a random deal can be told to leave out. */
  bannable?: string[];
  help: {
    rules: { icon: string; title: string; text: string }[];
    events: { code: string; icon: string; title: string; text: string; affectsDay: boolean }[];
  };
  timerOptions: number[];
  timerRange: [number, number];
  chat: { maxLength: number; minIntervalSeconds: number; keep: number };
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

/** A person of the ranking: the games they played and won. */
export interface LeaderEntry {
  username: string;
  games: number;
  wins: number;
}
