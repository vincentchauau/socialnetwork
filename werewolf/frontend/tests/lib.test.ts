import { ApiError } from "@sn/api";
import { describe, expect, it } from "vitest";

import { errorText, frameErrorText } from "../app/lib/errors";
import { groupLog } from "../app/lib/log";
import {
  CHAT_KEEP,
  MAX_RETRY_DELAY_MS,
  mergeChat,
  parseFrame,
  retryDelay,
  sanitizeRoom,
  socketUrl,
} from "../app/lib/roomSocket";
import {
  abilitiesFor,
  buildCreateBody,
  clampCount,
  isValidCode,
  normalizeCode,
  pickAbility,
  pickFaction,
  tally,
  TIMER_LABEL,
  toDrafts,
  validateSeats,
  validateSetup,
} from "../app/lib/setup";
import { abilityIcon, animalFor, PHASE_INFO } from "../app/lib/theme";
import type { ChatMessage, SetupSeat } from "../app/lib/types";
import { makeGame, makeRoom, member, META, VILLAGER, WOLF } from "./helpers";

const err = (status: number, detail?: unknown) =>
  new ApiError(status, typeof detail === "string" ? detail : `Request failed (${status})`, detail === undefined ? undefined : { detail });

describe("errorText", () => {
  it("shows the server's Vietnamese detail for rule errors", () => {
    expect(errorText(err(400, "Chưa tới lượt"))).toBe("Chưa tới lượt");
    expect(errorText(err(409, "Phòng đã đầy"))).toBe("Phòng đã đầy");
    expect(errorText(err(422, "Cần ít nhất 1 Sói"))).toBe("Cần ít nhất 1 Sói");
  });

  it("uses fixed wording for 401, 429 and 503 whatever the detail", () => {
    expect(errorText(err(401, "Not authenticated"))).toBe("Bạn cần đăng nhập lại.");
    expect(errorText(err(429, "Too many"))).toBe("Bạn thao tác quá nhanh, hãy chờ một chút.");
    expect(errorText(err(503, "full"))).toBe("Máy chủ đang đầy phòng, thử lại sau.");
  });

  it("maps the origin refusal", () => {
    expect(errorText(err(403, "Origin not allowed"))).toBe("Nguồn truy cập không được phép.");
  });

  it("falls back per status when there is no string detail", () => {
    expect(errorText(err(400))).toBe("Hành động không hợp lệ lúc này.");
    expect(errorText(err(403))).toBe("Bạn không có quyền làm việc này.");
    expect(errorText(err(404))).toBe("Không tìm thấy phòng.");
    expect(errorText(err(409))).toBe("Phòng không ở trạng thái phù hợp.");
    expect(errorText(new ApiError(422, "x", { detail: [{ msg: "bad" }] }))).toBe("Dữ liệu chưa hợp lệ, hãy kiểm tra lại.");
    expect(errorText(err(500))).toBe("Có lỗi xảy ra.");
  });

  it("maps network failures and unknown values", () => {
    expect(errorText(new TypeError("Failed to fetch"))).toBe("Không kết nối được máy chủ. Hãy thử lại.");
    expect(errorText("boom")).toBe("Có lỗi xảy ra.");
  });

  it("maps websocket error frames", () => {
    expect(frameErrorText("Invalid message")).toBe("Tin nhắn không hợp lệ.");
    expect(frameErrorText("Chưa tới lượt")).toBe("Chưa tới lượt");
    expect(frameErrorText("")).toBe("Có lỗi xảy ra.");
  });
});

describe("setup rules", () => {
  it("lists only abilities valid for the faction", () => {
    expect(abilitiesFor(META, "WOLF").map((a) => a.code)).toEqual(["SEE_FACTION", "KILL"]);
    expect(abilitiesFor(META, "GHOST").map((a) => a.code)).toEqual(["TRANSFORM"]);
    expect(abilitiesFor(META, "VILLAGER").map((a) => a.code)).toEqual(["NONE", "SEE_FACTION"]);
  });

  it("keeps the ability when the new faction allows it, else takes the first allowed", () => {
    expect(pickFaction(META, { faction: "VILLAGER", ability: "SEE_FACTION" }, "WOLF")).toEqual({ faction: "WOLF", ability: "SEE_FACTION" });
    expect(pickFaction(META, { faction: "WOLF", ability: "KILL" }, "VILLAGER")).toEqual({ faction: "VILLAGER", ability: "NONE" });
    expect(pickFaction(META, { faction: "WOLF", ability: "KILL" }, "GHOST")).toEqual({ faction: "GHOST", ability: "TRANSFORM" });
    const same = { faction: "WOLF", ability: "KILL" } as const;
    expect(pickFaction(META, same, "WOLF")).toBe(same);
  });

  it("falls back to NONE when a faction has no ability at all", () => {
    const bare = { ...META, abilities: [] };
    expect(pickFaction(bare, { faction: "WOLF", ability: "KILL" }, "GHOST").ability).toBe("NONE");
  });

  it("refuses an ability that is not allowed for the faction", () => {
    const seat: SetupSeat = { faction: "VILLAGER", ability: "NONE" };
    expect(pickAbility(META, seat, "KILL")).toBe(seat);
    expect(pickAbility(META, seat, "SEE_FACTION")).toEqual({ faction: "VILLAGER", ability: "SEE_FACTION" });
  });

  it("clamps the seat count into the allowed range", () => {
    expect(clampCount(META, 1)).toBe(5);
    expect(clampCount(META, 99)).toBe(40);
    expect(clampCount(META, 12.7)).toBe(12);
    expect(clampCount(META, Number.NaN)).toBe(5);
  });

  it("normalises and validates room codes", () => {
    expect(normalizeCode("ab-c1dEfg")).toBe("ABCDE");
    expect(isValidCode("ABCDE")).toBe(true);
    expect(isValidCode("ABCD")).toBe(false);
    expect(isValidCode("abcde")).toBe(false);
  });

  const seats = (...factions: SetupSeat["faction"][]): SetupSeat[] =>
    factions.map((faction) => ({ faction, ability: faction === "WOLF" ? "KILL" : faction === "GHOST" ? "TRANSFORM" : "NONE" }));

  it("validates the seat table", () => {
    const ok = seats("WOLF", "VILLAGER", "VILLAGER", "VILLAGER", "VILLAGER");
    expect(validateSeats(META, ok)).toBeNull();
    expect(validateSeats(META, ok.slice(0, 4))).toMatch(/từ 5 đến 40/);
    expect(validateSeats(META, [...ok, ...Array(40)].slice(0, 41) as SetupSeat[])).toMatch(/từ 5 đến 40/);
    expect(validateSeats(META, seats("VILLAGER", "VILLAGER", "VILLAGER", "VILLAGER", "VILLAGER"))).toBe("Cần ít nhất 1 Sói.");
    expect(validateSeats(META, seats("WOLF", "WOLF", "WOLF", "GHOST", "GHOST"))).toBe("Cần ít nhất 1 Người.");
    const wrong = ok.map((s, i) => (i === 1 ? { ...s, ability: "KILL" } : s));
    expect(validateSeats(META, wrong)).toBe("Chức năng của ghế #2 không hợp lệ với phe đã chọn.");
  });

  const base = {
    seats: seats("WOLF", "VILLAGER", "VILLAGER", "VILLAGER", "VILLAGER"),
    roomName: "",
    roomCode: "",
    timerSeconds: 0,
    events: true,
    deadTalk: true,
    listed: true,
  };

  it("validates the whole form", () => {
    expect(validateSetup(META, base)).toBeNull();
    expect(validateSetup(META, { ...base, roomCode: "AB" })).toMatch(/5 chữ cái/);
    expect(validateSetup(META, { ...base, roomName: "x".repeat(31) })).toMatch(/30 ký tự/);
    expect(validateSetup(META, { ...base, timerSeconds: 45 })).toMatch(/không hợp lệ/);
  });

  it("builds the create body without names and with optional fields only when set", () => {
    const body = buildCreateBody({ ...base, roomName: "  Làng  ", roomCode: "WOLFS", timerSeconds: 60, listed: false }, true);
    expect(body).toEqual({
      count: 5,
      seats: base.seats,
      start: true,
      timerSeconds: 60,
      events: true,
      deadTalk: true,
      listed: false,
      roomName: "Làng",
      roomCode: "WOLFS",
    });
    const bare = buildCreateBody(base, false);
    expect(bare).not.toHaveProperty("roomName");
    expect(bare).not.toHaveProperty("roomCode");
    expect(bare.start).toBe(false);
  });

  it("counts factions, labels timers and drafts seats", () => {
    expect(tally(base.seats, "WOLF")).toBe(1);
    expect(TIMER_LABEL(0)).toBe("Tắt");
    expect(TIMER_LABEL(30)).toBe("30s");
    expect(toDrafts(base.seats)[0]).toEqual({ faction: "WOLF", ability: "KILL", name: "" });
  });
});

describe("socket helpers", () => {
  it("builds the same-origin websocket url", () => {
    expect(socketUrl("ABCDE", { protocol: "https:", host: "x.test" })).toBe("wss://x.test/api/werewolf/ws/ABCDE");
    expect(socketUrl("ABCDE", { protocol: "http:", host: "localhost:3000" })).toBe("ws://localhost:3000/api/werewolf/ws/ABCDE");
    expect(socketUrl("ABCDE")).toBe("ws://localhost:3000/api/werewolf/ws/ABCDE");
  });

  it("backs off exponentially up to the cap", () => {
    expect([0, 1, 2, 3].map(retryDelay)).toEqual([1000, 2000, 4000, 8000]);
    expect(retryDelay(10)).toBe(MAX_RETRY_DELAY_MS);
    expect(retryDelay(-3)).toBe(1000);
  });

  it("parses well-formed frames only", () => {
    const state = makeRoom();
    expect(parseFrame(JSON.stringify({ type: "state", state }))?.type).toBe("state");
    const chat: ChatMessage = { seq: 1, round: "Ngày 1", channel: "public", text: "hi", target: 0, dead: false, author: { id: 2, name: "B" } };
    expect(parseFrame(JSON.stringify({ type: "chat", message: chat }))).toEqual({ type: "chat", message: chat });
    expect(parseFrame(JSON.stringify({ type: "error", error: "Sai" }))).toEqual({ type: "error", error: "Sai" });
  });

  it("ignores malformed frames", () => {
    expect(parseFrame(42)).toBeNull();
    expect(parseFrame("not json")).toBeNull();
    expect(parseFrame("123")).toBeNull();
    expect(parseFrame(JSON.stringify({ type: "state", state: {} }))).toBeNull();
    expect(parseFrame(JSON.stringify({ type: "chat", message: { text: "x" } }))).toBeNull();
    expect(parseFrame(JSON.stringify({ type: "error", error: 4 }))).toBeNull();
    expect(parseFrame(JSON.stringify({ type: "other" }))).toBeNull();
  });

  it("never keeps another member's role in the lobby, even if the server sent it", () => {
    const leaky = makeRoom({
      members: [
        member(1, "alice", { faction: WOLF, ability: { code: "KILL", label: "Giết" } }),
        member(2, "Bình", { faction: VILLAGER, ability: { code: "NONE", label: "x" } }),
      ],
    });
    const clean = sanitizeRoom(leaky);
    expect(clean.members[0].faction).toEqual(WOLF);
    expect(clean.members[1].faction).toBeNull();
    expect(clean.members[1].ability).toBeNull();
    const parsed = parseFrame(JSON.stringify({ type: "state", state: leaky }));
    expect(parsed?.type === "state" && parsed.state.members[1].faction).toBeNull();
  });

  it("leaves a running game untouched", () => {
    const running = makeRoom({ game: makeGame(), started: true });
    expect(sanitizeRoom(running)).toBe(running);
  });

  const msg = (seq: number): ChatMessage => ({ seq, round: "Ngày 1", channel: "public", text: `m${seq}`, target: 0, dead: false, author: { id: 2, name: "B" } });

  it("merges pushed chat by seq, sorted, deduped and bounded", () => {
    const room = makeRoom({ game: makeGame({ chat: [msg(2)] }) });
    const merged = mergeChat(room, msg(1));
    expect(merged.game?.chat.map((m) => m.seq)).toEqual([1, 2]);
    expect(mergeChat(merged, msg(2))).toBe(merged);
    expect(room.game?.chat).toHaveLength(1); // not mutated
    let big = makeRoom({ game: makeGame() });
    for (let i = 1; i <= CHAT_KEEP + 5; i += 1) big = mergeChat(big, msg(i));
    expect(big.game?.chat).toHaveLength(CHAT_KEEP);
    expect(big.game?.chat[0].seq).toBe(6);
  });

  it("ignores chat without a game", () => {
    const lobby = makeRoom();
    expect(mergeChat(lobby, msg(1))).toBe(lobby);
  });
});

describe("log and theme", () => {
  it("groups by round, newest group first, lines in order", () => {
    const groups = groupLog([
      { round: "Đêm 1", text: "a" },
      { round: "Đêm 1", text: "b" },
      { round: "Ngày 1", text: "c" },
    ]);
    expect(groups).toEqual([
      { round: "Ngày 1", lines: ["c"] },
      { round: "Đêm 1", lines: ["a", "b"] },
    ]);
  });

  it("keeps only the latest 12 rounds", () => {
    const log = Array.from({ length: 20 }, (_, i) => ({ round: `Đêm ${i}`, text: "x" }));
    expect(groupLog(log)).toHaveLength(12);
  });

  it("has icons, a stable animal per name and phase titles", () => {
    expect(abilityIcon("KILL")).toBe("🗡️");
    expect(abilityIcon("???")).toBe("❔");
    expect(animalFor("An")).toBe(animalFor("An"));
    expect(PHASE_INFO.night.title(2)).toBe("Đêm 2");
    expect(PHASE_INFO.day.title(3)).toBe("Ngày 3");
    expect(PHASE_INFO.revenge.title(1)).toBe("Kéo theo!");
    expect(PHASE_INFO.settle.title(1)).toBe("…");
    expect(PHASE_INFO.over.title(1)).toBe("Kết thúc");
  });
});
