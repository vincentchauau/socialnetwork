import { vi } from "vitest";

import type { SetupSeat } from "../app/lib/types";
import { META } from "./helpers";

export const push = vi.fn();

export function deal(count: number): SetupSeat[] {
  return Array.from({ length: count }, (_, i) =>
    i === 0 ? { faction: "WOLF", ability: "KILL" } : i === 1 && count > 5 ? { faction: "GHOST", ability: "TRANSFORM" } : { faction: "VILLAGER", ability: "NONE" },
  );
}

/** Default behaviour of every werewolfApi call; tests override single calls. */
export function resetApi(api: Record<string, ReturnType<typeof vi.fn>>) {
  for (const fn of Object.values(api)) fn.mockReset();
  api.meta.mockResolvedValue(META);
  api.random.mockImplementation(async (count: number) => ({ seats: deal(count) }));
  api.rooms.mockResolvedValue([]);
  api.history.mockResolvedValue([]);
  push.mockReset();
}
