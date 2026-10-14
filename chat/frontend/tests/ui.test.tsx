import { apiFetch, loadSession, refreshSession } from "@sn/api";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPage from "../app/page";
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
  document.head.querySelectorAll("style").forEach((el) => el.remove());
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
    .getAllByRole("button")
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
  it("click expands the member names (aria-expanded) and also enters the room, like the original", async () => {
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
    expect(await screen.findByRole("heading", { name: "Room: dev" })).toBeInTheDocument();
    expect(FakeSocket.byPath("/ws/dev")).toHaveLength(1);
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list", { name: "Thành viên dev" })).toBeNull();
  });

  it("is keyboard operable with Enter and Space", async () => {
    await renderChat();
    const row = screen.getByRole("button", { name: /^general/ });
    row.focus();
    await userEvent.keyboard("{Enter}");
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("list", { name: "Thành viên general" })).toHaveTextContent("Carol");
    await userEvent.keyboard("a"); // other keys do nothing
    expect(row).toHaveAttribute("aria-expanded", "true");
    await userEvent.keyboard(" ");
    expect(row).toHaveAttribute("aria-expanded", "false");
  });

  it("marks the current room as selected", async () => {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: /^dev/ }));
    expect(screen.getByRole("button", { name: /^dev/ }).closest("li")).toHaveClass("selected");
  });
});

describe("Join In / Join Out", () => {
  it("cannot leave until a room is joined", async () => {
    await renderChat();
    expect(screen.getByRole("button", { name: "Join Out" })).toBeDisabled();
    expect(screen.getByRole("heading", { name: "Room:" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter message...")).toBeDisabled();
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

  it("Enter in the room box joins like Join In", async () => {
    await renderChat();
    await userEvent.type(screen.getByLabelText(ROOM_INPUT), "quick{Enter}");
    expect(await screen.findByRole("heading", { name: "Room: quick" })).toBeInTheDocument();
  });

  it("Join Out leaves and closes the socket", async () => {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: /^dev/ }));
    expect(await screen.findByRole("heading", { name: "Room: dev" })).toBeInTheDocument();
    const ws = FakeSocket.last("/ws/dev");
    const out = screen.getByRole("button", { name: "Join Out" });
    expect(out).toBeEnabled();
    await userEvent.click(out);
    expect(ws.closeCalls).toBe(1);
    expect(screen.getByRole("heading", { name: "Room:" })).toBeInTheDocument();
    expect(out).toBeDisabled();
  });

  it("clears an old join error when entering a room from the list", async () => {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: "Join In" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^random/ }));
    expect(screen.queryByText(/Tên phòng chỉ gồm/)).toBeNull();
  });
});

describe("columns and layout", () => {
  async function openRoom() {
    await renderChat();
    await userEvent.click(screen.getByRole("button", { name: /^dev/ }));
    await screen.findByRole("heading", { name: "Room: dev" });
    FakeSocket.last("/ws/dev").open();
  }
  const grid = () => document.querySelector(".maxGridContainer") as HTMLElement;

  it("defaults to one column and sets the member grid from 1 to 10, clamping and ignoring junk", async () => {
    await openRoom();
    const input = screen.getByLabelText("Columns:");
    expect(input).toHaveValue(1);
    expect(grid()).toHaveStyle({ gridTemplateColumns: "repeat(1, 1fr)" });

    fireEvent.change(input, { target: { value: "3" } });
    expect(grid()).toHaveStyle({ gridTemplateColumns: "repeat(3, 1fr)" });
    fireEvent.change(input, { target: { value: "99" } });
    expect(grid()).toHaveStyle({ gridTemplateColumns: "repeat(10, 1fr)" });
    fireEvent.change(input, { target: { value: "0" } });
    expect(grid()).toHaveStyle({ gridTemplateColumns: "repeat(1, 1fr)" });
    fireEvent.change(input, { target: { value: "4" } });
    fireEvent.change(input, { target: { value: "" } }); // mid-edit: keeps the last valid value
    expect(grid()).toHaveStyle({ gridTemplateColumns: "repeat(4, 1fr)" });
    fireEvent.blur(input);
    expect(input).toHaveValue(4);
  });

  it("keeps Columns on top, then the composer, the heading and the messages", async () => {
    await openRoom();
    const columns = screen.getByLabelText("Columns:");
    const box = screen.getByPlaceholderText("Enter message...");
    const heading = screen.getByRole("heading", { name: "Room: dev" });
    const log = screen.getByRole("log");
    const after = Node.DOCUMENT_POSITION_FOLLOWING;
    expect(columns.compareDocumentPosition(box) & after).toBeTruthy();
    expect(box.compareDocumentPosition(heading) & after).toBeTruthy();
    expect(heading.compareDocumentPosition(log) & after).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  it("shows the room members as tiles in the grid", async () => {
    await openRoom();
    FakeSocket.last("/ws/dev").frame({
      type: "presence",
      total: 3,
      members: [
        { userId: 1, username: "alice" },
        { userId: 2, username: "bob" },
      ],
    });
    const tiles = [...grid().querySelectorAll(".file-name")].map((n) => n.textContent);
    expect(tiles).toEqual(["alice", "bob", "+1 người khác"]);
  });
});

describe("splitters", () => {
  const rect = (width: number, height: number) =>
    ({ left: 0, top: 0, width, height, right: width, bottom: height, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;

  it("start at 30/70 and 60/40 like the original", async () => {
    await renderChat();
    const left = document.querySelector("#roomSplitter > div:first-child") as HTMLElement;
    const right = document.querySelector("#roomSplitter > div:last-child") as HTMLElement;
    expect(left.style.width).toBe("30%");
    expect(right.style.width).toBe("70%");
    const top = document.querySelector("#messageSplitter > div:first-child") as HTMLElement;
    expect(top.style.height).toBe("60%");
  });

  it("dragging the bar resizes the panels and stops on mouse-up; the edges are protected", async () => {
    await renderChat();
    const container = document.getElementById("roomSplitter")!;
    vi.spyOn(container, "getBoundingClientRect").mockReturnValue(rect(1000, 500));
    const left = container.firstElementChild as HTMLElement;
    fireEvent.mouseDown(screen.getByTestId("roomSplitter-bar"));
    fireEvent.mouseMove(document, { clientX: 400 });
    expect(left.style.width).toBe("40%");
    fireEvent.mouseMove(document, { clientX: 2 }); // too close to the edge: ignored
    expect(left.style.width).toBe("40%");
    fireEvent.mouseUp(document);
    fireEvent.mouseMove(document, { clientX: 700 });
    expect(left.style.width).toBe("40%");
  });

  it("the vertical bar resizes by height", async () => {
    await renderChat();
    const container = document.getElementById("messageSplitter")!;
    vi.spyOn(container, "getBoundingClientRect").mockReturnValue(rect(700, 400));
    fireEvent.mouseDown(screen.getByTestId("messageSplitter-bar"));
    fireEvent.mouseMove(document, { clientY: 100 });
    expect((container.firstElementChild as HTMLElement).style.height).toBe("25%");
    fireEvent.mouseUp(document);
  });
});

describe("Show / Hide", () => {
  it("starts hidden like the original and toggles the header and footer together", async () => {
    await renderChat();
    expect(document.getElementById("page-header")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(document.getElementById("page-header")).not.toBeNull();
    expect(document.getElementById("page-footer")).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(document.getElementById("page-header")).toBeNull();
    expect(document.getElementById("page-footer")).toBeNull();
  });
});

describe("nav bar", () => {
  it("shows the user, avatar initial and the buttons", async () => {
    await renderChat();
    const nav = screen.getByRole("navigation", { name: "Điều hướng" });
    expect(within(nav).getByRole("button", { name: "alice" })).toBeInTheDocument();
    expect(nav.querySelector("#signin_avatar")).toHaveTextContent("A");
    for (const name of ["Show", "Theme", "Home", "File", "Database"]) {
      expect(within(nav).getByRole("button", { name })).toBeInTheDocument();
    }
  });

  it("navigates with Home, File, Database and the account button", async () => {
    await renderChat();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    for (const [name, path] of [
      ["Home", "/"],
      ["File", "/work"],
      ["Database", "/work"],
      ["alice", "/login"],
    ]) {
      await userEvent.click(screen.getByRole("button", { name }));
      expect(assign).toHaveBeenLastCalledWith(path);
    }
  });
});

describe("Theme button", () => {
  const sheetRule = (selector: string) =>
    [...document.styleSheets]
      .flatMap((sheet) => [...sheet.cssRules] as CSSStyleRule[])
      .find((rule) => rule.selectorText === selector);

  it("picks a random theme on load, as the original does", async () => {
    await renderChat();
    expect(sheetRule("*")?.style.color).toMatch(/^rgb\(/);
  });

  it("repaints on click", async () => {
    await renderChat();
    vi.spyOn(Math, "random").mockReturnValueOnce(0).mockReturnValueOnce(0.1); // ramp 0, dark
    await userEvent.click(screen.getByRole("button", { name: "Theme" }));
    expect(sheetRule("*")?.style.background).toContain("rgb(32, 0, 0)");
    expect(sheetRule("*")?.style.color).toBe("rgb(255, 204, 204)");
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
