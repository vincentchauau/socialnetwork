import { act, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import RoomView from "../../app/werewolf/components/RoomView";
import { werewolfApi } from "../../app/werewolf/lib/api";
import type { RoomState } from "../../app/werewolf/lib/types";
import { FakeSocket, installFakeSocket, META } from "./helpers";
import { push, resetApi } from "./mocks";

export const api = vi.mocked(werewolfApi);
export const envelope = (state: RoomState) => ({ id: state.code, state });

export function resetRoomTest() {
  resetApi(api as never);
  api.meta.mockResolvedValue(META);
  installFakeSocket();
}

/** Renders the room page for `state` and opens the socket like a browser would. */
export async function renderRoom(state: RoomState, { open = true }: { open?: boolean } = {}) {
  api.room.mockResolvedValue(envelope(state));
  const view = render(<RoomView code={state.code} onExit={() => push("/")} />);
  await screen.findByText(/./, { selector: "h1, h2, p" });
  await act(async () => {
    await Promise.resolve();
  });
  if (open && FakeSocket.instances.length > 0) act(() => FakeSocket.last().open());
  return view;
}

export function pushState(state: RoomState) {
  act(() => FakeSocket.last().push({ type: "state", state }));
}

export { push };
