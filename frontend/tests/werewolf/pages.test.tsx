import { loadSession } from "@sn/api";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "@sn/compounds/AuthGate";
import HistoryPage from "../_pages/werewolf-history";
import WerewolfPage from "../_pages/werewolf";
import RoomPage from "../_pages/werewolf-room";
import { werewolfApi } from "../../app/werewolf/lib/api";
import { resetApi } from "./mocks";
import { makeRoom } from "./helpers";
import { installFakeSocket } from "./helpers";

vi.mock("../../app/werewolf/lib/api", async () => (await import("./apiMock")).apiFactory());
const redirect = vi.hoisted(() =>
  vi.fn((path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  }),
);
vi.mock("next/navigation", () => ({
  redirect,
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({ id: "abcde" }),
}));
vi.mock("@sn/api", async (original) => ({ ...(await original<typeof import("@sn/api")>()), loadSession: vi.fn() }));

const session = vi.mocked(loadSession);
const api = vi.mocked(werewolfApi);

beforeEach(() => {
  resetApi(api as never);
  installFakeSocket();
  session.mockReset();
});

describe("AuthGate", () => {
  it("shows loading, then the signed-in content", async () => {
    session.mockResolvedValue({ id: 1, username: "alice" });
    render(<AuthGate title="T">{(user) => <p>chào {user.username}</p>}</AuthGate>);
    expect(screen.getByText("Đang tải…")).toBeInTheDocument();
    expect(await screen.findByText("chào alice")).toBeInTheDocument();
  });

  it("asks anonymous visitors to sign in", async () => {
    session.mockResolvedValue(null);
    render(<AuthGate title="Ma Sói">{() => <p>secret</p>}</AuthGate>);
    expect(await screen.findByRole("link", { name: "đăng nhập" })).toHaveAttribute("href", "/user");
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("reports a server problem", async () => {
    session.mockRejectedValue(new Error("down"));
    render(<AuthGate title="Ma Sói">{() => <p>secret</p>}</AuthGate>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });
});

describe("pages", () => {
  it("history requires a session and then loads", async () => {
    session.mockResolvedValue({ id: 1, username: "alice" });
    render(<HistoryPage />);
    expect(await screen.findByText("Bạn chưa chơi ván nào.")).toBeInTheDocument();
    expect(api.history).toHaveBeenCalled();
  });

  it("room page upper-cases the code from the url", async () => {
    session.mockResolvedValue({ id: 1, username: "alice" });
    api.room.mockResolvedValue({ id: "ABCDE", state: makeRoom() });
    render(<RoomPage />);
    expect(await screen.findByRole("button", { name: /Bắt đầu/ })).toBeInTheDocument();
    expect(api.room).toHaveBeenCalledWith("ABCDE");
  });
});
