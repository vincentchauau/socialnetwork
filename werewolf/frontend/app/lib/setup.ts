import type { AbilityMeta, CreateBody, FactionCode, SeatDraft, SetupMeta, SetupSeat } from "./types";

export const ROOM_CODE_LENGTH = 5;
export const ROOM_NAME_MAX = 30;
export const DEFAULT_COUNT = 5;
export const QUICK_COUNTS = [5, 9, 12, 15, 20, 30, 40];
/** Timer choices the UI offers; the labels come from here, the values from `meta.timerOptions`. */
export const TIMER_LABEL = (seconds: number): string => (seconds === 0 ? "Tắt" : `${seconds}s`);

/** Abilities a faction may have (mirror of the server's allowedFactions). */
export function abilitiesFor(meta: SetupMeta, faction: FactionCode): AbilityMeta[] {
  return meta.abilities.filter((ability) => ability.allowedFactions.includes(faction));
}

/** Changes a seat's faction; keeps the ability if it is still allowed, else the first allowed one. */
export function pickFaction(meta: SetupMeta, seat: SetupSeat, faction: FactionCode): SetupSeat {
  if (faction === seat.faction) return seat;
  const allowed = abilitiesFor(meta, faction);
  const keep = allowed.some((ability) => ability.code === seat.ability);
  return { faction, ability: keep ? seat.ability : (allowed[0]?.code ?? "NONE") };
}

export function pickAbility(meta: SetupMeta, seat: SetupSeat, ability: string): SetupSeat {
  return abilitiesFor(meta, seat.faction).some((a) => a.code === ability) ? { ...seat, ability } : seat;
}

export function clampCount(meta: Pick<SetupMeta, "minPlayers" | "maxPlayers">, value: number): number {
  if (!Number.isFinite(value)) return meta.minPlayers;
  return Math.min(meta.maxPlayers, Math.max(meta.minPlayers, Math.trunc(value)));
}

/** Takes a fresh deal from /setup/random (seats only), nothing else is kept per seat. */
export function toDrafts(seats: SetupSeat[]): SeatDraft[] {
  return seats.map((seat) => ({ ...seat, name: "" }));
}

export function tally(seats: SetupSeat[], faction: FactionCode): number {
  return seats.filter((seat) => seat.faction === faction).length;
}

/** Normalises a room code typed by a person: upper-case letters only, at most 5. */
export function normalizeCode(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z]/g, "").slice(0, ROOM_CODE_LENGTH);
}

export function isValidCode(code: string): boolean {
  return /^[A-Z]{5}$/.test(code);
}

/** The first problem with the seat table (Vietnamese), or null when it can be sent. */
export function validateSeats(meta: SetupMeta, seats: SetupSeat[]): string | null {
  if (seats.length < meta.minPlayers || seats.length > meta.maxPlayers) {
    return `Số người chơi phải từ ${meta.minPlayers} đến ${meta.maxPlayers}.`;
  }
  if (tally(seats, "WOLF") < 1) return "Cần ít nhất 1 Sói.";
  if (tally(seats, "VILLAGER") < 1) return "Cần ít nhất 1 Người.";
  const bad = seats.findIndex((seat) => !abilitiesFor(meta, seat.faction).some((a) => a.code === seat.ability));
  if (bad >= 0) return `Chức năng của ghế #${bad + 1} không hợp lệ với phe đã chọn.`;
  return null;
}

export interface SetupOptions {
  seats: SetupSeat[];
  roomName: string;
  roomCode: string;
  timerSeconds: number;
  events: boolean;
  deadTalk: boolean;
  listed: boolean;
}

/** First problem of the whole form, or null. */
export function validateSetup(meta: SetupMeta, options: SetupOptions): string | null {
  if (options.roomCode && !isValidCode(options.roomCode)) {
    return "Mã phòng gồm đúng 5 chữ cái (hoặc để trống để hệ thống tự tạo).";
  }
  if (options.roomName.length > ROOM_NAME_MAX) return `Tên phòng tối đa ${ROOM_NAME_MAX} ký tự.`;
  if (!meta.timerOptions.includes(options.timerSeconds)) return "Thời gian mỗi lượt không hợp lệ.";
  return validateSeats(meta, options.seats);
}

export function buildCreateBody(options: SetupOptions, start: boolean): CreateBody {
  const body: CreateBody = {
    count: options.seats.length,
    seats: options.seats.map(({ faction, ability }) => ({ faction, ability })),
    start,
    timerSeconds: options.timerSeconds,
    events: options.events,
    deadTalk: options.deadTalk,
    listed: options.listed,
  };
  const roomName = options.roomName.trim();
  if (roomName) body.roomName = roomName;
  if (options.roomCode) body.roomCode = options.roomCode;
  return body;
}
