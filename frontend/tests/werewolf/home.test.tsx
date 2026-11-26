import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Room } from "../../app/chat/protocol";
import WerewolfHome from "../../app/werewolf/components/WerewolfHome";
import { werewolfApi } from "../../app/werewolf/lib/api";
import { META } from "./helpers";

const dock = vi.hoisted(() => ({ onRoom: null as null | ((room: unknown) => void), props: null as null | Record<string, unknown> }));
vi.mock("../../app/chat/dock/ChatDock", () => ({
  default: (props: { onRoom?: (room: unknown) => void; page?: React.ReactNode }) => {
    dock.onRoom = props.onRoom ?? null;
    dock.props = props as Record<string, unknown>;
    return <><div data-testid="dock" />{props.page}</>;
  },
}));
const prepare = vi.hoisted(() => vi.fn());
vi.mock("../../app/chat/werewolf", () => ({ prepareGame: prepare }));
vi.mock("../../app/werewolf/components/RoomView", () => ({
  default: ({ code, onExit }: { code: string; onExit: () => void }) => (
    <div data-testid="game">
      game {code}
      <button type="button" onClick={onExit}>leave</button>
    </div>
  ),
}));
vi.mock("../../app/werewolf/lib/api", async () => (await import("./apiMock")).apiFactory());

const room = (extra: Partial<Room> = {}) =>
  ({ slug: "village", title: "Làng Trăng", state: "open", me: { status: "joined", role: "member" }, ...extra }) as unknown as Room;
const user = { id: 1, username: "alice" } as never;

beforeEach(() => {
  vi.mocked(werewolfApi.meta).mockResolvedValue(META);
  prepare.mockReset();
  dock.onRoom = null;
  dock.props = null;
});

describe("the Werewolf page: the game of the room that is open in the chat below", () => {
  it("has the chat of the app under it, with Rooms and Messages open the first time, and asks for a room first", async () => {
    render(<WerewolfHome user={user} />);
    expect(screen.getByTestId("dock")).toBeInTheDocument();
    expect(dock.props).toMatchObject({ app: "werewolf", start: { rooms: true, members: true, messages: true } });
    expect(screen.getByText(/Chọn hoặc tạo một phòng/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Lịch sử/ })).toBeInTheDocument(); // history is one of the three tabs: Game, History, Leaderboard
    expect(screen.getByRole("link", { name: /Bảng xếp hạng/ })).toBeInTheDocument();
    expect(screen.queryByText(/Xin chào/)).toBeNull();
  });

  it("starts the game of the room that is open when the person asks, and shows it on the page", async () => {
    prepare.mockResolvedValue({ code: "ABCDE", href: "/werewolf/room/ABCDE" });
    const person = userEvent.setup();
    render(<WerewolfHome user={user} />);
    await waitFor(() => expect(dock.onRoom).not.toBeNull());
    dock.onRoom?.(room());
    await person.click(await screen.findByRole("button", { name: /Chơi Ma Sói ở phòng này/ }));
    expect(prepare).toHaveBeenCalledWith("village");
    expect(await screen.findByTestId("game")).toHaveTextContent("game ABCDE");
    await person.click(screen.getByRole("button", { name: "leave" }));
    expect(await screen.findByRole("button", { name: /Chơi Ma Sói ở phòng này/ })).toBeInTheDocument();
  });

  it("asks a person who is not in the room to join it first, and shows why a game cannot be made", async () => {
    const person = userEvent.setup();
    render(<WerewolfHome user={user} />);
    await waitFor(() => expect(dock.onRoom).not.toBeNull());
    dock.onRoom?.(room({ me: null } as Partial<Room>));
    expect(await screen.findByText(/Hãy vào phòng này/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Chơi Ma Sói ở phòng này/ })).toBeNull();
    prepare.mockRejectedValue(new Error("The game is full"));
    dock.onRoom?.(room());
    await person.click(await screen.findByRole("button", { name: /Chơi Ma Sói ở phòng này/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("the game follows the room", () => {
  it("asks for the game of the room again when virtual people come into it, so its seats take their names", async () => {
    prepare.mockResolvedValue({ code: "ABCDE", href: "/werewolf/room/ABCDE" });
    const person = userEvent.setup();
    render(<WerewolfHome user={user} />);
    await waitFor(() => expect(dock.onRoom).not.toBeNull());
    dock.onRoom?.(room());
    await person.click(await screen.findByRole("button", { name: /Chơi Ma Sói ở phòng này/ }));
    await screen.findByTestId("game");
    expect(prepare).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new CustomEvent("sn:room-members-changed", { detail: { slug: "village" } }));
    await waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));
    window.dispatchEvent(new CustomEvent("sn:room-members-changed", { detail: { slug: "another-room" } }));
    expect(prepare).toHaveBeenCalledTimes(2);
  });

  it("moves to the new game when the room has one (somebody was sent away: the code changes)", async () => {
    prepare.mockResolvedValueOnce({ code: "ABCDE", href: "/werewolf/room/ABCDE" });
    const person = userEvent.setup();
    render(<WerewolfHome user={user} />);
    await waitFor(() => expect(dock.onRoom).not.toBeNull());
    dock.onRoom?.(room());
    await person.click(await screen.findByRole("button", { name: /Chơi Ma Sói ở phòng này/ }));
    await screen.findByTestId("game");
    expect(screen.getByTestId("game")).toHaveTextContent("ABCDE");
    prepare.mockResolvedValueOnce({ code: "FGHIJ", href: "/werewolf/room/FGHIJ" });
    window.dispatchEvent(new CustomEvent("sn:room-members-changed", { detail: { slug: "village" } }));
    await waitFor(() => expect(screen.getByTestId("game")).toHaveTextContent("FGHIJ"));
    expect(prepare).toHaveBeenLastCalledWith("village", true); // it only follows: nobody is added to fill the seats
  });
});
