import { vi } from "vitest";

/** Factory for vi.mock("../app/lib/api", ...): every call is a vi.fn the test controls. */
export const apiFactory = () => ({
  WEREWOLF_API: "/api/werewolf",
  werewolfApi: {
    meta: vi.fn(),
    random: vi.fn(),
    rooms: vi.fn(),
    room: vi.fn(),
    create: vi.fn(),
    join: vi.fn(),
    leave: vi.fn(),
    start: vi.fn(),
    addBots: vi.fn(),
    act: vi.fn(),
    chat: vi.fn(),
    force: vi.fn(),
    rematch: vi.fn(),
    reset: vi.fn(),
    perspective: vi.fn(),
    history: vi.fn(),
  },
});
