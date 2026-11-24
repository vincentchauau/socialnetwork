import { vi } from "vitest";

import { META } from "./helpers";

export const push = vi.fn();

/** Default behaviour of every werewolfApi call; tests override single calls. */
export function resetApi(api: Record<string, ReturnType<typeof vi.fn>>) {
  for (const fn of Object.values(api)) fn.mockReset();
  api.meta.mockResolvedValue(META);
  api.history.mockResolvedValue([]);
  push.mockReset();
}
