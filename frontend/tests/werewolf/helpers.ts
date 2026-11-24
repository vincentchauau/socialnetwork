import { vi } from "vitest";

import type { Game, Member, Player, RoomState, SetupMeta } from "../../app/werewolf/lib/types";

export const VILLAGER = { code: "VILLAGER", label: "Người" } as const;
export const WOLF = { code: "WOLF", label: "Sói" } as const;
export const GHOST = { code: "GHOST", label: "Ma" } as const;

export const META: SetupMeta = {
  minPlayers: 5,
  maxPlayers: 40,
  maxRoomsPerUser: 3,
  defaults: {
    VILLAGER: [{ icon: "🗳", label: "Vote ban ngày", hint: "Mọi người đều vote" }],
    WOLF: [{ icon: "🐺", label: "Vote giết", hint: "Cả bầy vote" }],
    GHOST: [],
  },
  factions: [VILLAGER, WOLF, GHOST],
  abilities: [
    { code: "NONE", label: "Không có", help: "Không làm gì", allowedFactions: ["VILLAGER"] },
    { code: "SEE_FACTION", label: "Xem nhóm", help: "Xem phe", allowedFactions: ["VILLAGER", "WOLF"] },
    { code: "KILL", label: "Giết trực tiếp", help: "Giết một người", allowedFactions: ["WOLF"] },
    { code: "TRANSFORM", label: "Biến hình", help: "Thành Ma", allowedFactions: ["GHOST"] },
  ],
  help: {
    rules: [{ icon: "📜", title: "Mục tiêu", text: "Phe nào hết đối thủ thì thắng." }],
    events: [{ code: "FOG", icon: "🌫️", title: "Sương mù", text: "Không thấy gì.", affectsDay: false }],
  },
  timerOptions: [0, 30, 60, 90],
  timerRange: [5, 600],
  chat: { maxLength: 140, minIntervalSeconds: 0.8, keep: 400 },
};

export function player(id: number, name: string, extra: Partial<Player> = {}): Player {
  return { id, name, alive: true, isBot: id !== 1, faction: null, ability: null, ...extra };
}

export function makeGame(extra: Partial<Game> = {}): Game {
  return {
    phase: "night",
    night: 1,
    gameOver: false,
    winner: null,
    me: { id: 1, name: "alice", alive: true, faction: VILLAGER, ability: { code: "SEE_FACTION", label: "Xem nhóm" } },
    players: [player(1, "alice"), player(2, "Bình"), player(3, "Cường")],
    actions: [],
    waitingFor: 0,
    log: [],
    event: null,
    recap: null,
    timer: null,
    chat: [],
    chatChannel: null,
    ...extra,
  };
}

export function member(seat: number, name: string, extra: Partial<Member> = {}): Member {
  return { seat, name, isBot: seat !== 1, isHost: seat === 1, isYou: seat === 1, faction: null, ability: null, ...extra };
}

export function makeRoom(extra: Partial<RoomState> = {}): RoomState {
  return {
    code: "ABCDE",
    title: "Làng Trăng Máu",
    isHost: true,
    you: { username: "alice", seat: 1 },
    minPlayers: 5,
    maxPlayers: 40,
    members: [member(1, "alice"), member(2, "Bình"), member(3, "Cường"), member(4, "Dũng"), member(5, "Em")],
    timer: 0,
    events: true,
    deadTalk: true,
    listed: true,
    history: { games: 0, VILLAGER: 0, WOLF: 0, GHOST: 0, draw: 0 },
    started: false,
    game: null,
    ...extra,
  };
}

/** Minimal controllable WebSocket for tests. */
export class FakeSocket {
  static instances: FakeSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.closed = true;
    this.readyState = 3;
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  push(frame: unknown) {
    this.onmessage?.({ data: typeof frame === "string" ? frame : JSON.stringify(frame) });
  }

  drop(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code });
  }

  static reset() {
    FakeSocket.instances = [];
  }

  static last(): FakeSocket {
    return FakeSocket.instances[FakeSocket.instances.length - 1];
  }
}

export function installFakeSocket() {
  FakeSocket.reset();
  vi.stubGlobal("WebSocket", FakeSocket);
}
