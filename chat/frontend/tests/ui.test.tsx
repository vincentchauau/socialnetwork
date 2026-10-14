import { apiFetch, loadSession, refreshSession } from "@sn/api";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPage from "../app/page";
import { PALETTES, THEME_STORAGE_KEY, buildTokens } from "../app/theme";
import { FakeSocket } from "./fakeSocket";

vi.mock("@sn/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sn/api")>()),
  apiFetch: vi.fn(),
  loadSession: vi.fn(),
  refreshSession: vi.fn(),
}));

const ROOMS = [
  { room: "general", users: 3, members: ["alice", "bob", "Carol"] },
  { room: "dev", users: 40, members: ["dave", "erin"] },
  { room: "random", users: 1, members: ["frank"] },
];

const ROOM_INPUT = "Join or filter by room name...";
const USER_INPUT = "Filter by user name...";

beforeEach(() => {
  FakeSocket.reset();
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.mocked(loadSession).mockResolvedValue({ id: 1, username: "alice" });
  vi.mocked(refreshSession).mockResolvedValue(true);
  vi.mocked(apiFetch).mockImplementation(async () => [] as never);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  window.localStorage.clear();
  document.documentElement.removeAttribute("style");
});

async function renderChat() {
  render(<ChatPage />);
  await screen.findByRole("navigation", { name: "Điều hướng" });
  await waitFor(() => expect(FakeSocket.byPath("/ws-lobby")).toHaveLength(1));
  const lobby = FakeSocket.last("/ws-lobby");
  lobby.open();
  lobby.frame({ type: "rooms", rooms: ROOMS });
  return lobby;
}

const roomNames = () =>
  within(screen.getByRole("list", { name: "Danh sách phòng" }))
    .getAllByRole("button", { name: /^(?!Join )/ })
    .map((b) => b.querySelector("span")?.textContent);

describe("filters", () => {
  it("lists everything with empty filters and filters by room name, case-insensitively", async () => {
    await renderChat();
    expect(roomNames()).toEqual(["general", "dev", "random"]);
    await userEvent.type(screen.getByLabelText(ROOM_INPUT), "GEN");
    expect(roomNames()).toEqual(["general"]);
  });

  it("filters by user name through members", async () => {
    await renderChat();
    await userEvent.type(screen.getByLabelText(USER_INPUT), "CAR");
    expect(roomNames()).toEqual(["general"]);
  });

  it("needs both filters to match", async () => {
    await renderChat();
    await userEvent.type(screen.getByLabelText(ROOM_INPUT), "d");
    expect(roomNames()).toEqual(["dev", "random"]);
    await userEvent.type(screen.getByLabelText(USER_INPUT), "erin");
    expect(roomNames()).toEqual(["dev"]);
    await userEvent.clear(screen.getByLabelText(ROOM_INPUT));
    await userEvent.type(screen.getByLabelText(ROOM_INPUT), "random");
    expect(screen.getByText("Không có phòng nào khớp bộ lọc.")).toBeInTheDocument();
  });
});

describe("room rows", () => {
  it("toggles the member list with aria-expanded and shows the cap note", async () => {
    await renderChat();
    const row = screen.getByRole("button", { name: /^dev/ });
    expect(row).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    const members = screen.getByRole("list", { name: "Thành viên dev" });
    expect(within(members).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "dave",
      "erin",
      "+38 người khác",
    ]);
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list", { name: "Thành viên dev" })).toBeNull();
  });

  it("is keyboard operable and does not join on toggle", async () => {
    await renderChat();
    const row = screen.getByRole("button", { name: /^general/ });
    row.focus();
    await userEvent.keyboard("{Enter}");
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(FakeSocket.byPath("/ws/general")).toHaveLength(0);
    expect(screen.getByRole("list", { name: "Thành viên general" })).toHaveTextContent("Carol");
  });
});

describe("Join In / Join Out", () => {
  it("cannot leave until a room is joined", async () => {
    await renderChat();
    expect(screen.getByRole("button", { name: "Join Out" })).toBeDisabled();
    expect(screen.getByRole("heading", { name: "Room:" })).toBeInTheDocument();
  });

  it("validates the room name, shows the hint, then joins and clears the filter", async () => {
    await renderChat();
    const input = screen.getByLabelText(ROOM_INPUT);
    await userEvent.click(screen.getByRole("button", { name: "Join In" })); // empty
    expect(screen.getByRole("alert")).toHaveTextContent("Tên phòng chỉ gồm");
    await userEvent.type(input, "bad name!");
    await userEvent.click(screen.getByRole("button", { name: "Join In" }));
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(FakeSocket.byPath("/ws/bad name!")).toHaveLength(0);

    await userEvent.clear(input);
    await userEvent.type(input, " new-room ");
    await userEvent.click(screen.getByRole("button", { name: "Join In" }));
    expect(await screen.findByRole("heading", { name: "Room: new-room" })).toBeInTheDocument();
    expect(input).toHaveValue("");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(FakeSocket.byPath("/ws/new-room")).toHaveLength(1);
  });

  it("Join on a row joins that room, Join Out leaves and closes the socket", async () => {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: "Join dev" }));
    expect(await screen.findByRole("heading", { name: "Room: dev" })).toBeInTheDocument();
    const ws = FakeSocket.last("/ws/dev");
    const out = screen.getByRole("button", { name: "Join Out" });
    expect(out).toBeEnabled();
    await userEvent.click(out);
    expect(ws.closeCalls).toBe(1);
    expect(screen.getByRole("heading", { name: "Room:" })).toBeInTheDocument();
    expect(out).toBeDisabled();
  });

  it("clears an old join error when joining from the list", async () => {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: "Join In" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Join random" }));
    expect(screen.queryByText(/Tên phòng chỉ gồm/)).toBeNull();
  });
});

describe("columns and layout", () => {
  async function openRoom() {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: "Join dev" }));
    await screen.findByRole("heading", { name: "Room: dev" });
  }

  it("defaults to one column and sets the grid from 1 to 6, clamping and ignoring junk", async () => {
    await openRoom();
    const log = screen.getByRole("log");
    const input = screen.getByLabelText("Columns:");
    expect(input).toHaveValue(1);
    expect(log).toHaveStyle({ gridTemplateColumns: "repeat(1, 1fr)" });

    fireEvent.change(input, { target: { value: "3" } });
    expect(log).toHaveStyle({ gridTemplateColumns: "repeat(3, 1fr)" });
    fireEvent.change(input, { target: { value: "99" } });
    expect(log).toHaveStyle({ gridTemplateColumns: "repeat(6, 1fr)" });
    fireEvent.change(input, { target: { value: "0" } });
    expect(log).toHaveStyle({ gridTemplateColumns: "repeat(1, 1fr)" });
    fireEvent.change(input, { target: { value: "4" } });
    fireEvent.change(input, { target: { value: "" } }); // mid-edit: keeps the last valid value
    expect(log).toHaveStyle({ gridTemplateColumns: "repeat(4, 1fr)" });
    fireEvent.blur(input);
    expect(input).toHaveValue(4);
  });

  it("keeps the composer above the messages and the heading above both", async () => {
    await openRoom();
    const heading = screen.getByRole("heading", { name: "Room: dev" });
    const box = screen.getByPlaceholderText("Enter message...");
    const log = screen.getByRole("log");
    const after = Node.DOCUMENT_POSITION_FOLLOWING;
    expect(heading.compareDocumentPosition(box) & after).toBeTruthy();
    expect(box.compareDocumentPosition(log) & after).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });
});

describe("Show / Hide", () => {
  it("flips the label and hides the header block", async () => {
    await renderChat();
    const toggle = screen.getByRole("button", { name: "Hide" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("heading", { name: "Chat" })).toBeVisible();
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Show" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("heading", { name: "Chat" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(screen.getByRole("heading", { name: "Chat" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Hide" })).toBeInTheDocument();
  });

  it("collapses the room column for small screens", async () => {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: "Ẩn danh sách phòng" }));
    const toggle = screen.getByRole("button", { name: "Hiện danh sách phòng" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.getElementById("rooms-body")).toHaveAttribute("data-open", "false");
  });
});

describe("nav bar", () => {
  it("shows the user and the links", async () => {
    await renderChat();
    const nav = screen.getByRole("navigation", { name: "Điều hướng" });
    expect(within(nav).getByText("alice")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Đổi tài khoản" })).toHaveAttribute("href", "/login");
    expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(within(nav).getByRole("link", { name: "File" })).toHaveAttribute("href", "/work");
    expect(within(nav).getByRole("link", { name: "Database" })).toHaveAttribute("href", "/work");
    expect(within(nav).getByRole("button", { name: "Theme" })).toBeInTheDocument();
  });

  it("opens the help dialog, traps focus, closes on Escape and returns focus", async () => {
    await renderChat();
    const opener = screen.getByRole("button", { name: "Trợ giúp" });
    await userEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Trợ giúp" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const close = within(dialog).getByRole("button", { name: "Đóng" });
    expect(close).toHaveFocus();
    await userEvent.tab();
    expect(close).toHaveFocus(); // single focusable: trapped
    await userEvent.tab({ shift: true });
    expect(close).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });

  it("wraps Tab between first and last focusable and closes by button or backdrop", async () => {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: "Trợ giúp" }));
    const dialog = screen.getByRole("dialog");
    const extra = document.createElement("a");
    extra.href = "#x";
    extra.textContent = "x";
    dialog.prepend(extra);
    const close = within(dialog).getByRole("button", { name: "Đóng" });
    close.focus();
    await userEvent.tab();
    expect(extra).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(close).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "a" });
    await userEvent.click(close);
    expect(screen.queryByRole("dialog")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Trợ giúp" }));
    fireEvent.mouseDown(screen.getByRole("dialog")); // inside: stays open
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("dialog").parentElement!);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("Theme button", () => {
  it("applies a palette through CSS variables and remembers it", async () => {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: "Theme" }));
    expect(document.documentElement.style.getPropertyValue("--bg")).toMatch(/^#[0-9a-f]{6}$/);
    const stored = JSON.parse(window.localStorage.getItem(THEME_STORAGE_KEY)!);
    expect(stored.palette).toBeGreaterThanOrEqual(0);
    expect(["dark", "light"]).toContain(stored.variant);
  });

  it("restores the stored theme on load", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify({ palette: 4, variant: "light" }));
    await renderChat();
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe(buildTokens(PALETTES[4], "light").bg);
  });

  it("renders with the default theme when localStorage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    await renderChat();
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe("");
  });
});

describe("plain text", () => {
  it("shows member names as text, never as markup", async () => {
    const lobby = await renderChat();
    const evil = "<img src=x onerror=alert(1)>";
    lobby.frame({ type: "rooms", rooms: [{ room: "g", users: 1, members: [evil] }] });
    await userEvent.click(screen.getByRole("button", { name: /^g/ }));
    const list = screen.getByRole("list", { name: "Thành viên g" });
    expect(within(list).getByText(evil)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    await act(async () => {});
  });
});
