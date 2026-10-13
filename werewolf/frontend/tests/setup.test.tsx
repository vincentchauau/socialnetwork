import { ApiError } from "@sn/api";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomeView from "../app/components/HomeView";
import { ROOMS_REFRESH_MS } from "../app/components/RoomList";
import { werewolfApi } from "../app/lib/api";
import type { RoomSummary, SetupSeat } from "../app/lib/types";
import { deal, push, resetApi } from "./mocks";

vi.mock("../app/lib/api", () => ({
  WEREWOLF_API: "/api/werewolf",
  werewolfApi: {
    meta: vi.fn(),
    random: vi.fn(),
    rooms: vi.fn(),
    create: vi.fn(),
    join: vi.fn(),
    history: vi.fn(),
  },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const api = vi.mocked(werewolfApi);
const account = { id: 7, username: "alice" };

async function renderHome() {
  const view = render(<HomeView user={account} />);
  const start = await screen.findByRole("button", { name: /Bắt đầu ngay/ });
  await waitFor(() => expect(start).toBeEnabled());
  return view;
}

const countInput = () => screen.getByLabelText(/Số người chơi/) as HTMLInputElement;
const openSeats = async (u: ReturnType<typeof userEvent.setup>) =>
  u.click(screen.getByRole("button", { name: /Chỉnh phe và chức năng/ }));

beforeEach(() => {
  resetApi(api as never);
  api.create.mockResolvedValue({ id: "ABCDE", state: {} as never });
});

afterEach(() => vi.restoreAllMocks());

describe("SetupForm: seat count and deal", () => {
  it("greets the account (no free-text name) and deals 5 seats at start", async () => {
    await renderHome();
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Tên của bạn|Tên người chơi/)).not.toBeInTheDocument();
    expect(api.random).toHaveBeenCalledWith(5);
    expect(countInput().value).toBe("5");
    expect(screen.getByText(/🐺 1 · 👻 0 · 🧑 4/)).toBeInTheDocument();
  });

  it("re-deals when the count changes with +, − and the quick chips", async () => {
    const u = userEvent.setup();
    await renderHome();
    await u.click(screen.getByRole("button", { name: "Thêm một người" }));
    await waitFor(() => expect(countInput().value).toBe("6"));
    expect(api.random).toHaveBeenLastCalledWith(6);
    expect(screen.getByText(/👻 1/)).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Bớt một người" }));
    await waitFor(() => expect(countInput().value).toBe("5"));
    await u.click(screen.getByRole("button", { name: "12" }));
    await waitFor(() => expect(countInput().value).toBe("12"));
    expect(api.random).toHaveBeenLastCalledWith(12);
    expect(screen.getByRole("button", { name: "12" })).toHaveAttribute("aria-pressed", "true");
  });

  it("cannot go below 5 or above 40", async () => {
    const u = userEvent.setup();
    await renderHome();
    expect(screen.getByRole("button", { name: "Bớt một người" })).toBeDisabled();
    await u.clear(countInput());
    await u.type(countInput(), "99");
    await u.tab();
    await waitFor(() => expect(countInput().value).toBe("40"));
    expect(api.random).toHaveBeenLastCalledWith(40);
    expect(screen.getByRole("button", { name: "Thêm một người" })).toBeDisabled();
  });

  it("applies a typed number straight away and snaps a too-small one back on blur", async () => {
    const u = userEvent.setup();
    await renderHome();
    await u.clear(countInput());
    await u.type(countInput(), "9");
    await waitFor(() => expect(api.random).toHaveBeenLastCalledWith(9));
    await u.clear(countInput());
    await u.type(countInput(), "2");
    await u.tab();
    await waitFor(() => expect(countInput().value).toBe("5"));
    expect(api.random).toHaveBeenLastCalledWith(5);
    await u.clear(countInput());
    await u.tab();
    expect(countInput().value).toBe("5");
    await u.type(countInput(), "ab");
    expect(countInput().value).toBe(""); // letters are dropped
    await u.tab();
    expect(countInput().value).toBe("5");
  });

  it("keeps the newest deal when answers arrive out of order", async () => {
    const u = userEvent.setup();
    await renderHome();
    let first!: (v: { seats: SetupSeat[] }) => void;
    let second!: (v: { seats: SetupSeat[] }) => void;
    api.random.mockImplementationOnce(() => new Promise((r) => (first = r)));
    api.random.mockImplementationOnce(() => new Promise((r) => (second = r)));
    await u.clear(countInput());
    await u.type(countInput(), "9");
    await u.clear(countInput());
    await u.type(countInput(), "15");
    await act(async () => second({ seats: deal(15) }));
    await act(async () => first({ seats: deal(9) }));
    await u.tab();
    await waitFor(() => expect(countInput().value).toBe("15"));
    await u.click(screen.getByRole("button", { name: /Chỉnh phe/ }));
    expect(screen.getAllByRole("radiogroup", { name: /Phe của ghế/ })).toHaveLength(15);
  });

  it("rolls everything with the dice button and reports the split", async () => {
    const u = userEvent.setup();
    vi.spyOn(Math, "random").mockReturnValue(0.999);
    await renderHome();
    await u.click(screen.getByRole("button", { name: /Ngẫu nhiên tất cả/ }));
    expect(await screen.findByRole("status")).toHaveTextContent("Đã xáo 20 người · 🐺 1 · 👻 1 · 🧑 18");
    expect(api.random).toHaveBeenLastCalledWith(20);
  });

  it("toasts a failed roll in Vietnamese", async () => {
    const u = userEvent.setup();
    await renderHome();
    api.random.mockRejectedValueOnce(new ApiError(429, "slow", { detail: "slow" }));
    await u.click(screen.getByRole("button", { name: /Ngẫu nhiên tất cả/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bạn thao tác quá nhanh");
  });

  it("toasts when the rules cannot be loaded", async () => {
    api.meta.mockRejectedValue(new TypeError("offline"));
    render(<HomeView user={account} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
    expect(screen.getByText("Đang tải cấu hình…")).toBeInTheDocument();
  });
});

describe("SetupForm: seat table", () => {
  it("shows the account on seat 1 and bot seats without names", async () => {
    const u = userEvent.setup();
    await renderHome();
    await openSeats(u);
    const table = screen.getByRole("list", { name: "Bảng ghế" });
    expect(within(table).getByText("alice")).toBeInTheDocument();
    expect(within(table).getByText("Bot 2")).toBeInTheDocument();
    expect(within(table).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("offers only abilities valid for the faction and moves the ability with the faction", async () => {
    const u = userEvent.setup();
    await renderHome();
    await openSeats(u);
    // seat 3 is a villager with NONE
    const select = screen.getByLabelText("Chức năng ghế 3") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["NONE", "SEE_FACTION"]);
    await u.click(within(screen.getByRole("radiogroup", { name: "Phe của ghế 3" })).getByRole("radio", { name: /Sói/ }));
    const wolfSelect = screen.getByLabelText("Chức năng ghế 3") as HTMLSelectElement;
    expect([...wolfSelect.options].map((o) => o.value)).toEqual(["SEE_FACTION", "KILL"]);
    expect(wolfSelect.value).toBe("SEE_FACTION"); // NONE is not valid for wolves: first allowed
    await u.selectOptions(wolfSelect, "KILL");
    expect((screen.getByLabelText("Chức năng ghế 3") as HTMLSelectElement).value).toBe("KILL");
  });

  it("locks the single ability of a faction and shows its default chips", async () => {
    const u = userEvent.setup();
    await renderHome();
    await openSeats(u);
    await u.click(within(screen.getByRole("radiogroup", { name: "Phe của ghế 3" })).getByRole("radio", { name: /Ma/ }));
    expect(screen.queryByLabelText("Chức năng ghế 3")).not.toBeInTheDocument();
    expect(screen.getAllByText(/Biến hình \(cố định\)/).length).toBeGreaterThan(0);
    const defaults = screen.getByRole("list", { name: "Mặc định của phe, ghế 1" });
    expect(within(defaults).getByText(/Vote giết/)).toHaveAttribute("title", "Cả bầy vote");
  });

  it("collapses again", async () => {
    const u = userEvent.setup();
    await renderHome();
    await openSeats(u);
    await u.click(screen.getByRole("button", { name: /Thu gọn/ }));
    expect(screen.queryByRole("list", { name: "Bảng ghế" })).not.toBeInTheDocument();
  });
});

describe("SetupForm: creating", () => {
  it("starts right away with the dealt seats, the options and no bot names", async () => {
    const u = userEvent.setup();
    await renderHome();
    await u.click(screen.getByRole("button", { name: /Bắt đầu ngay/ }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/room/ABCDE"));
    expect(api.create).toHaveBeenCalledWith({
      count: 5,
      seats: deal(5),
      start: true,
      timerSeconds: 0,
      events: true,
      deadTalk: true,
      listed: true,
    });
  });

  it("opens a lobby with name, code, timer, switches", async () => {
    const u = userEvent.setup();
    await renderHome();
    await u.type(screen.getByLabelText(/Tên phòng/), "Làng Sói");
    await u.type(screen.getByLabelText(/Mã phòng \(?5|Mã phòng/, { selector: "#ww-room-code" }), "wo1lfs");
    expect(screen.getByLabelText(/Mã phòng/, { selector: "#ww-room-code" })).toHaveValue("WOLFS");
    await u.click(screen.getByRole("radio", { name: "60s" }));
    expect(screen.getByRole("radio", { name: "60s" })).toHaveAttribute("aria-checked", "true");
    await u.click(screen.getByRole("checkbox", { name: /Thẻ sự kiện/ }));
    await u.click(screen.getByRole("checkbox", { name: /Người chết chat chung/ }));
    await u.click(screen.getByRole("checkbox", { name: /danh sách phòng công khai/ }));
    await u.click(screen.getByRole("button", { name: /Tạo phòng chờ người khác vào/ }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(api.create).toHaveBeenCalledWith(
      expect.objectContaining({ start: false, roomName: "Làng Sói", roomCode: "WOLFS", timerSeconds: 60, events: false, deadTalk: false, listed: false }),
    );
  });

  it("offers the timer choices Tắt/30/60/90 from the rules", async () => {
    await renderHome();
    const group = screen.getByRole("radiogroup", { name: "Thời gian mỗi lượt" });
    expect(within(group).getAllByRole("radio").map((r) => r.textContent)).toEqual(["Tắt", "30s", "60s", "90s"]);
    expect(within(group).getByRole("radio", { name: "Tắt" })).toHaveAttribute("aria-checked", "true");
  });

  it("refuses a table with no wolf and explains why", async () => {
    const u = userEvent.setup();
    await renderHome();
    await openSeats(u);
    await u.click(within(screen.getByRole("radiogroup", { name: "Phe của ghế 1" })).getByRole("radio", { name: /Người/ }));
    await u.click(screen.getByRole("button", { name: /Bắt đầu ngay/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cần ít nhất 1 Sói.");
    expect(api.create).not.toHaveBeenCalled();
  });

  it("refuses a short room code", async () => {
    const u = userEvent.setup();
    await renderHome();
    await u.type(screen.getByLabelText(/Mã phòng/, { selector: "#ww-room-code" }), "AB");
    await u.click(screen.getByRole("button", { name: /Bắt đầu ngay/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mã phòng gồm đúng 5 chữ cái");
    expect(api.create).not.toHaveBeenCalled();
  });

  it("clears the problem after a valid submit", async () => {
    const u = userEvent.setup();
    await renderHome();
    await u.type(screen.getByLabelText(/Mã phòng/, { selector: "#ww-room-code" }), "AB");
    await u.click(screen.getByRole("button", { name: /Bắt đầu ngay/ }));
    await screen.findByRole("alert");
    await u.type(screen.getByLabelText(/Mã phòng/, { selector: "#ww-room-code" }), "CDE");
    await u.click(screen.getByRole("button", { name: /Bắt đầu ngay/ }));
    await waitFor(() => expect(api.create).toHaveBeenCalled());
  });

  it("maps a server refusal to a toast and re-enables the buttons", async () => {
    const u = userEvent.setup();
    await renderHome();
    api.create.mockRejectedValueOnce(new ApiError(409, "Mã phòng đã có người dùng", { detail: "Mã phòng đã có người dùng" }));
    await u.click(screen.getByRole("button", { name: /Bắt đầu ngay/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Mã phòng đã có người dùng");
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Bắt đầu ngay/ })).toBeEnabled();
    await u.click(screen.getByRole("button", { name: "Đóng thông báo" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Join by code and public rooms", () => {
  const rooms: RoomSummary[] = [
    { id: "WOLFS", title: "Làng Sói", host: "bob", players: 2, seats: 6, open_seats: 4, max_players: 40, timer: 30, events: true },
    { id: "ABCDE", title: "Làng Ma", host: "cat", players: 1, seats: 5, open_seats: 4, max_players: 40, timer: 0, events: false },
  ];

  it("enables the join button only for 5 letters and joins", async () => {
    const u = userEvent.setup();
    api.join.mockResolvedValue({ id: "QWERT", state: {} as never });
    await renderHome();
    const join = screen.getByRole("button", { name: "Vào phòng" });
    expect(join).toBeDisabled();
    await u.type(screen.getByLabelText(/^Mã phòng/, { selector: "#ww-join-code" }), "qw3ert");
    expect(screen.getByLabelText(/^Mã phòng/, { selector: "#ww-join-code" })).toHaveValue("QWERT");
    await u.click(join);
    expect(api.join).toHaveBeenCalledWith("QWERT");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/room/QWERT"));
  });

  it("submits on Enter, and not when the code is incomplete", async () => {
    const u = userEvent.setup();
    api.join.mockResolvedValue({ id: "QWERT", state: {} as never });
    await renderHome();
    const input = screen.getByLabelText(/^Mã phòng/, { selector: "#ww-join-code" });
    await u.type(input, "QW{Enter}");
    expect(api.join).not.toHaveBeenCalled();
    await u.type(input, "ERT{Enter}");
    expect(api.join).toHaveBeenCalledWith("QWERT");
  });

  it("shows a joining error such as a full room", async () => {
    const u = userEvent.setup();
    api.join.mockRejectedValue(new ApiError(409, "Phòng đã đầy", { detail: "Phòng đã đầy" }));
    await renderHome();
    await u.type(screen.getByLabelText(/^Mã phòng/, { selector: "#ww-join-code" }), "QWERT");
    await u.click(screen.getByRole("button", { name: "Vào phòng" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Phòng đã đầy");
  });

  it("lists open rooms and joins one", async () => {
    const u = userEvent.setup();
    api.rooms.mockResolvedValue(rooms);
    api.join.mockResolvedValue({ id: "WOLFS", state: {} as never });
    await renderHome();
    const list = await screen.findByRole("region", { name: /Phòng đang mở/ });
    expect(await within(list).findByText("Làng Sói")).toBeInTheDocument();
    expect(within(list).getByText(/👑 bob · 👥 2\/6 · còn 4 ghế · ⏱ 30s · 🎴/)).toBeInTheDocument();
    await u.click(within(list).getByRole("button", { name: /Vào phòng Làng Sói \(WOLFS\)/ }));
    expect(api.join).toHaveBeenCalledWith("WOLFS");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/room/WOLFS"));
  });

  it("says when there is no public room, and when loading fails", async () => {
    await renderHome();
    expect(await screen.findByText(/Chưa có phòng công khai nào/)).toBeInTheDocument();
    api.rooms.mockRejectedValueOnce(new ApiError(503, "x"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Làm mới danh sách phòng" }));
    expect(await screen.findByText("Máy chủ đang đầy phòng, thử lại sau.")).toBeInTheDocument();
  });

  it("refreshes the list on a timer and stops when unmounted", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const view = await renderHome();
      const calls = api.rooms.mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ROOMS_REFRESH_MS);
      });
      expect(api.rooms.mock.calls.length).toBe(calls + 1);
      view.unmount();
      await vi.advanceTimersByTimeAsync(ROOMS_REFRESH_MS * 2);
      expect(api.rooms.mock.calls.length).toBe(calls + 1);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("Home chrome", () => {
  it("links to history and opens the rules sheet from the loaded meta", async () => {
    const u = userEvent.setup();
    await renderHome();
    expect(screen.getByRole("link", { name: /Lịch sử ván chơi/ })).toHaveAttribute("href", "/history");
    await u.click(screen.getByRole("button", { name: /Luật/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Phe nào hết đối thủ thì thắng.")).toBeInTheDocument();
    expect(within(dialog).getByText("Giết một người")).toBeInTheDocument();
    expect(within(dialog).getByText("Không thấy gì.")).toBeInTheDocument();
    expect(api.meta).toHaveBeenCalledTimes(1); // shared with the form, no second fetch
  });
});
