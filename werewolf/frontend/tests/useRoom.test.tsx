import { ApiError } from "@sn/api";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRoom } from "../app/hooks/useRoom";
import { werewolfApi } from "../app/lib/api";
import type { ChatMessage } from "../app/lib/types";
import { FakeSocket, installFakeSocket, makeGame, makeRoom, member, VILLAGER, WOLF } from "./helpers";

vi.mock("../app/lib/api", () => ({ WEREWOLF_API: "/api/werewolf", werewolfApi: { room: vi.fn() } }));

const roomMock = vi.mocked(werewolfApi.room);
const envelope = (state = makeRoom()) => ({ id: state.code, state });

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function mount(code = "ABCDE") {
  const hook = renderHook(() => useRoom(code));
  await flush();
  return hook;
}

const chat = (seq: number): ChatMessage => ({
  seq,
  round: "Ngày 1",
  channel: "public",
  text: `m${seq}`,
  target: 0,
  dead: false,
  author: { id: 2, name: "Bình" },
});

beforeEach(() => {
  vi.useFakeTimers();
  installFakeSocket();
  roomMock.mockReset();
  roomMock.mockResolvedValue(envelope());
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useRoom: loading and frames", () => {
  it("loads the room over REST, then connects the same-origin socket", async () => {
    const { result } = await mount();
    expect(roomMock).toHaveBeenCalledWith("ABCDE");
    expect(result.current.room?.code).toBe("ABCDE");
    expect(FakeSocket.instances).toHaveLength(1);
    expect(FakeSocket.last().url).toMatch(/\/api\/werewolf\/ws\/ABCDE$/);
    expect(result.current.status).toBe("connecting");
    act(() => FakeSocket.last().open());
    expect(result.current.status).toBe("open");
  });

  it("does not open a socket for a non-member previewing a lobby", async () => {
    roomMock.mockResolvedValue(envelope(makeRoom({ you: null })));
    const { result } = await mount();
    expect(result.current.room?.you).toBeNull();
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("replaces the state on a state frame and strips other members' roles", async () => {
    const { result } = await mount();
    const next = makeRoom({
      title: "Mới",
      members: [member(1, "alice", { faction: WOLF }), member(2, "Bình", { faction: VILLAGER })],
    });
    act(() => FakeSocket.last().push({ type: "state", state: next }));
    expect(result.current.room?.title).toBe("Mới");
    expect(result.current.room?.members[1].faction).toBeNull();
    expect(result.current.room?.members[0].faction).toEqual(WOLF);
  });

  it("appends chat frames without treating them as a state push, deduped by seq", async () => {
    roomMock.mockResolvedValue(envelope(makeRoom({ started: true, game: makeGame() })));
    const { result } = await mount();
    act(() => FakeSocket.last().push({ type: "chat", message: chat(1) }));
    act(() => FakeSocket.last().push({ type: "chat", message: chat(1) }));
    act(() => FakeSocket.last().push({ type: "chat", message: chat(2) }));
    expect(result.current.room?.game?.chat.map((m) => m.seq)).toEqual([1, 2]);
  });

  it("surfaces error frames and ignores garbage", async () => {
    const { result } = await mount();
    act(() => FakeSocket.last().push("garbage"));
    act(() => FakeSocket.last().push({ type: "nope" }));
    expect(result.current.frameError).toBeNull();
    act(() => FakeSocket.last().push({ type: "error", error: "Chưa tới lượt" }));
    expect(result.current.frameError).toEqual({ id: 1, text: "Chưa tới lượt" });
    act(() => FakeSocket.last().push({ type: "error", error: "Chưa tới lượt" }));
    expect(result.current.frameError?.id).toBe(2);
  });

  it("ignores chat frames arriving before any state", async () => {
    roomMock.mockResolvedValue(envelope(makeRoom({ started: true, game: makeGame() })));
    const { result } = await mount();
    act(() => result.current.applyChat(chat(7)));
    expect(result.current.room?.game?.chat).toHaveLength(1);
  });

  it("applies REST envelopes", async () => {
    const { result } = await mount();
    act(() => result.current.applyEnvelope(envelope(makeRoom({ title: "Từ REST" }))));
    expect(result.current.room?.title).toBe("Từ REST");
  });

  it("closes the socket on unmount and does not reconnect", async () => {
    const { unmount } = await mount();
    const socket = FakeSocket.last();
    unmount();
    expect(socket.closed).toBe(true);
    socket.drop(1006);
    await advance(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("does not close an already closed socket on unmount", async () => {
    const { unmount } = await mount();
    const socket = FakeSocket.last();
    socket.readyState = 3;
    unmount();
    expect(socket.closed).toBe(false);
  });
});

describe("useRoom: failures", () => {
  it("reports a missing room as fatal", async () => {
    roomMock.mockRejectedValue(new ApiError(404, "Không tìm thấy phòng", { detail: "Không tìm thấy phòng" }));
    const { result } = await mount();
    expect(result.current.fatal).toBe("Không tìm thấy phòng");
    expect(result.current.status).toBe("closed");
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("keeps loading on a network error (no fatal)", async () => {
    roomMock.mockRejectedValue(new TypeError("offline"));
    const { result } = await mount();
    expect(result.current.fatal).toBeNull();
    expect(result.current.room).toBeNull();
  });

  it("treats 1001 as room deleted", async () => {
    const { result } = await mount();
    act(() => FakeSocket.last().open());
    act(() => FakeSocket.last().drop(1001));
    await flush();
    expect(result.current.fatal).toBe("Phòng đã bị xoá.");
    expect(result.current.status).toBe("closed");
  });
});

describe("useRoom: reconnect", () => {
  it("re-fetches and reconnects with backoff after a drop, and re-fetches again once back", async () => {
    const { result } = await mount();
    act(() => FakeSocket.last().open());
    expect(roomMock).toHaveBeenCalledTimes(1);

    act(() => FakeSocket.last().drop(1006));
    await flush();
    expect(result.current.status).toBe("reconnecting");
    expect(roomMock).toHaveBeenCalledTimes(2); // state re-fetched while down
    expect(FakeSocket.instances).toHaveLength(1);

    await advance(999);
    expect(FakeSocket.instances).toHaveLength(1);
    await advance(1);
    expect(FakeSocket.instances).toHaveLength(2);
    expect(result.current.status).toBe("reconnecting");

    act(() => FakeSocket.last().open());
    await flush();
    expect(result.current.status).toBe("open");
    expect(roomMock).toHaveBeenCalledTimes(3); // and once more on the new connection
  });

  it("doubles the delay while the socket keeps failing and resets after a success", async () => {
    await mount();
    act(() => FakeSocket.last().open());

    act(() => FakeSocket.last().drop(1006));
    await flush();
    await advance(1000);
    expect(FakeSocket.instances).toHaveLength(2);

    act(() => FakeSocket.last().drop(1006)); // never opened
    await flush();
    await advance(1999);
    expect(FakeSocket.instances).toHaveLength(2);
    await advance(1);
    expect(FakeSocket.instances).toHaveLength(3);

    act(() => FakeSocket.last().open());
    await flush();
    act(() => FakeSocket.last().drop(1006));
    await flush();
    await advance(1000); // back to the first step
    expect(FakeSocket.instances).toHaveLength(4);
  });

  it("gives up after repeated immediate 1008 refusals", async () => {
    const { result } = await mount();
    act(() => FakeSocket.last().drop(1008));
    await flush();
    expect(result.current.fatal).toBeNull();
    await advance(1000);
    act(() => FakeSocket.last().drop(1008));
    await flush();
    expect(result.current.fatal).toMatch(/từ chối/);
    expect(result.current.status).toBe("closed");
  });

  it("reconnects after a 1008 that came after a long healthy connection (token refresh)", async () => {
    const { result } = await mount();
    act(() => FakeSocket.last().open());
    await advance(10_000);
    act(() => FakeSocket.last().drop(1008));
    await flush();
    expect(result.current.fatal).toBeNull();
    await advance(1000);
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it("stops when the re-fetch says the session or room is gone", async () => {
    const { result } = await mount();
    act(() => FakeSocket.last().open());
    roomMock.mockRejectedValue(new ApiError(403, "Bạn không ngồi trong phòng", { detail: "Bạn không ngồi trong phòng" }));
    act(() => FakeSocket.last().drop(1006));
    await flush();
    expect(result.current.fatal).toBe("Bạn không ngồi trong phòng");
    await advance(30_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("keeps the last known state while offline", async () => {
    const { result } = await mount();
    act(() => FakeSocket.last().open());
    roomMock.mockRejectedValue(new TypeError("offline"));
    act(() => FakeSocket.last().drop(1006));
    await flush();
    expect(result.current.room?.code).toBe("ABCDE");
    expect(result.current.fatal).toBeNull();
    await advance(1000);
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it("ignores events of a replaced socket", async () => {
    const { result } = await mount();
    const first = FakeSocket.last();
    act(() => first.open());
    act(() => first.drop(1006));
    await flush();
    await advance(1000);
    act(() => first.drop(1006)); // stale close of the old socket
    await flush();
    expect(result.current.status).toBe("reconnecting");
    expect(FakeSocket.instances).toHaveLength(2);
  });
});
