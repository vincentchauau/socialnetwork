import { ApiError, apiFetch, apiForm } from "@sn/api";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CardMessage, { parseCard } from "../../../app/chat/components/CardMessage";
import AddVirtual from "../../../app/chat/components/AddVirtual";
import type { ChatMessage } from "../../../app/chat/protocol";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn(), apiForm: vi.fn() }));
const fetchMock = vi.mocked(apiFetch);

const message = (card: unknown, extra: Partial<ChatMessage> = {}): ChatMessage => ({
  id: 9, user_id: 500, username: "Virt_0", kind: "card", content: typeof card === "string" ? card : JSON.stringify(card),
  reply_to_id: null, pinned_at: null, edited_at: null, created_at: "2026-01-01T00:00:00Z", ...extra,
});

beforeEach(() => {
  fetchMock.mockReset();
});

describe("a card in the conversation", () => {
  it("lists what was found and links only to addresses of this site", () => {
    const card = { type: "list", title: "Market: lamp", items: [{ title: "Lamp", subtitle: "12.00 · bob", href: "/market" }, { title: "Evil", href: "javascript:alert(1)" }] };
    render(<CardMessage message={message(card)} slug="r" myId={1} />);
    const group = screen.getByRole("group", { name: "Market: lamp" });
    expect(within(group).getByRole("link", { name: "Lamp" })).toHaveAttribute("href", "/market");
    expect(within(group).queryByRole("link", { name: "Evil" })).toBeNull();
    expect(within(group).getByText("Evil")).toBeInTheDocument();
  });

  it("says when nothing was found", () => {
    render(<CardMessage message={message({ type: "list", title: "Jobs: x", items: [] })} slug="r" myId={1} />);
    expect(screen.getByText("Không tìm thấy gì.")).toBeInTheDocument();
  });

  it("asks the person it is for, who confirms once and the buttons follow", async () => {
    fetchMock.mockResolvedValue(undefined as never);
    const user = userEvent.setup();
    const card = { type: "confirm", tool: "market.sell", args: {}, summary: "List Desk for sale at 50.00", status: "pending", for: 1 };
    render(<CardMessage message={message(card)} slug="r" myId={1} />);
    await user.click(screen.getByRole("button", { name: "Xác nhận" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/rooms\/r\/cards\/9\/confirm$/);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST" });
  });

  it("can be skipped, and shows nothing to do to anybody else", async () => {
    fetchMock.mockResolvedValue(undefined as never);
    const user = userEvent.setup();
    const card = { type: "confirm", summary: "Apply to job #3", status: "pending", for: 1 };
    const { unmount } = render(<CardMessage message={message(card)} slug="r" myId={2} />);
    expect(screen.queryByRole("button", { name: "Xác nhận" })).toBeNull();
    expect(screen.getByText("Đang chờ người được hỏi trả lời.")).toBeInTheDocument();
    unmount();
    render(<CardMessage message={message(card)} slug="r" myId={1} />);
    await user.click(screen.getByRole("button", { name: "Bỏ qua" }));
    await waitFor(() => expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/cards\/9\/cancel$/));
  });

  it("shows an answered question as such, what was done, and why something failed", () => {
    const { rerender } = render(<CardMessage message={message({ type: "confirm", summary: "Q", status: "done", for: 1 })} slug="r" myId={1} />);
    expect(screen.getByText("Đã thực hiện.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xác nhận" })).toBeNull();
    rerender(<CardMessage message={message({ type: "done", summary: "Listed Desk", href: "/market" })} slug="r" myId={1} />);
    expect(screen.getByRole("status")).toHaveTextContent("Listed Desk");
    expect(screen.getByRole("link", { name: "Mở" })).toHaveAttribute("href", "/market");
    rerender(<CardMessage message={message({ type: "error", summary: "It was refused" })} slug="r" myId={1} />);
    expect(screen.getByRole("alert")).toHaveTextContent("It was refused");
  });

  it("shows a message that is not a card this page knows as plain text", () => {
    expect(parseCard("not json")).toBeNull();
    expect(parseCard(JSON.stringify({ type: "other" }))).toBeNull();
    render(<CardMessage message={message("just words")} slug="r" myId={1} />);
    expect(screen.getByText("just words")).toBeInTheDocument();
  });

  it("tells when the answer could not be given", async () => {
    fetchMock.mockImplementation((async () => { throw new ApiError(500, "boom", {}); }) as never);
    const user = userEvent.setup();
    render(<CardMessage message={message({ type: "confirm", summary: "Q", status: "pending", for: 1 })} slug="r" myId={1} />);
    await user.click(screen.getByRole("button", { name: "Xác nhận" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không xử lý được yêu cầu này.");
  });
});

describe("forms, details and buttons in a card", () => {
  const FORM = {
    type: "form", title: "Post a job", submit: "Post the job", status: "pending", for: 1,
    fields: [{ name: "title", label: "Job title", kind: "text", required: true }, { name: "remote", label: "Remote", kind: "checkbox" }],
  };

  it("shows a form to the person it is for and sends what they filled in", async () => {
    fetchMock.mockResolvedValue(undefined as never);
    const user = userEvent.setup();
    render(<CardMessage message={message(FORM)} slug="r" myId={1} />);
    await user.type(screen.getByLabelText("Job title"), "Python dev");
    await user.click(screen.getByLabelText("Remote"));
    await user.click(screen.getByRole("button", { name: "Post the job" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/rooms\/r\/cards\/9\/submit$/);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ values: { title: "Python dev", remote: true } });
  });

  it("refuses to send a form with a missing required field, and shows the reason the last try failed", async () => {
    const user = userEvent.setup();
    render(<CardMessage message={message({ ...FORM, error: "title: too short" })} slug="r" myId={1} />);
    expect(screen.getByRole("alert")).toHaveTextContent("title: too short");
    await user.click(screen.getByRole("button", { name: "Post the job" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cần điền: Job title");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("gives a form to nobody else and closes it once it is sent", () => {
    const { rerender } = render(<CardMessage message={message(FORM)} slug="r" myId={2} />);
    expect(screen.queryByLabelText("Job title")).toBeNull();
    expect(screen.getByText("Đang chờ người được hỏi trả lời.")).toBeInTheDocument();
    rerender(<CardMessage message={message({ ...FORM, status: "done" })} slug="r" myId={1} />);
    expect(screen.queryByLabelText("Job title")).toBeNull();
    expect(screen.getByText("Đã thực hiện.")).toBeInTheDocument();
  });

  it("puts the buttons of a list on their rows, only for the person it is for, and says which row was pressed", async () => {
    fetchMock.mockResolvedValue(undefined as never);
    const user = userEvent.setup();
    const card = { type: "list", title: "Applicants", for: 1, items: [{ title: "bob", actions: [{ label: "Hire" }, { label: "Reject" }] }, { title: "eve", actions: [{ label: "Hire" }] }] };
    const { unmount } = render(<CardMessage message={message(card)} slug="r" myId={2} />);
    expect(screen.queryByRole("button", { name: "Hire" })).toBeNull();
    unmount();
    render(<CardMessage message={message(card)} slug="r" myId={1} />);
    await user.click(screen.getAllByRole("button", { name: "Hire" })[1]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/cards\/9\/act$/);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ item: 1, action: 0 });
  });

  it("shows a detail with its lines, a picture of this site only, and its button", async () => {
    fetchMock.mockResolvedValue(undefined as never);
    const user = userEvent.setup();
    const card = { type: "detail", title: "Lamp", for: 1, lines: ["12.00 USD", "Seller: bob"], image: "/api/art/files/lamp.png", actions: [{ label: "Add to cart" }] };
    const { container, rerender } = render(<CardMessage message={message(card)} slug="r" myId={1} />);
    expect(screen.getByText("Seller: bob")).toBeInTheDocument();
    expect(container.querySelector("img")).toHaveAttribute("src", "/api/art/files/lamp.png");
    await user.click(screen.getByRole("button", { name: "Add to cart" }));
    await waitFor(() => expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ action: 0 }));
    rerender(<CardMessage message={message({ ...card, image: "https://evil.example/x.png" })} slug="r" myId={1} />);
    expect(container.querySelector("img")).toBeNull();
    rerender(<CardMessage message={message({ ...card, image: "//evil.example/x.png" })} slug="r" myId={1} />);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("a form with a file, a thumbnail and a video", () => {
  const UPLOAD = {
    type: "form", title: "Share a photo", submit: "Share", status: "pending", for: 1,
    fields: [{ name: "file", label: "Photo", kind: "file", required: true }, { name: "caption", label: "Caption", kind: "text" }],
    upload: { steps: [{ path: "/api/file/upload", kind: "multipart", fields: ["file", "caption"], capture: { photo_id: "id" } }], send: ["photo_id"] },
  };

  it("uploads the file as the person and then tells the chat only what was made", async () => {
    vi.mocked(apiForm).mockResolvedValue({ id: 5 } as never);
    fetchMock.mockResolvedValue(undefined as never);
    const user = userEvent.setup();
    render(<CardMessage message={message(UPLOAD)} slug="r" myId={1} />);
    await user.upload(screen.getByLabelText("Photo"), new File(["x"], "a.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Share" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(vi.mocked(apiForm).mock.calls[0][0]).toBe("/api/file/upload");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/cards\/9\/submit$/);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ values: { photo_id: 5 } });
  });

  it("shows what the service said when the upload fails, and does not tell the chat", async () => {
    vi.mocked(apiForm).mockImplementation((async () => { throw new Error("Photo limit reached"); }) as never);
    const user = userEvent.setup();
    render(<CardMessage message={message(UPLOAD)} slug="r" myId={1} />);
    await user.upload(screen.getByLabelText("Photo"), new File(["x"], "a.png"));
    await user.click(screen.getByRole("button", { name: "Share" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Photo limit reached");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a thumbnail on a row and a video in a detail, from this site only", () => {
    const list = { type: "list", title: "Photos", items: [{ title: "Sunset", image: "/api/file/files/5/thumb" }, { title: "Evil", image: "https://evil.example/a.png" }] };
    const { container, rerender } = render(<CardMessage message={message(list)} slug="r" myId={1} />);
    expect(container.querySelectorAll("img")).toHaveLength(1);
    expect(container.querySelector("img")).toHaveAttribute("src", "/api/file/files/5/thumb");
    rerender(<CardMessage message={message({ type: "detail", title: "Cat", lines: [], video: "/api/watch/videos/7/stream" })} slug="r" myId={1} />);
    expect(container.querySelector("video")).toHaveAttribute("src", "/api/watch/videos/7/stream");
    rerender(<CardMessage message={message({ type: "detail", title: "Cat", lines: [], video: "https://evil.example/v.mp4" })} slug="r" myId={1} />);
    expect(container.querySelector("video")).toBeNull();
  });
});

describe("adding virtual people to a room", () => {
  it("adds the number of virtual people that was chosen, with no message about how many came", async () => {
    const onAdded = vi.fn();
    fetchMock.mockResolvedValue({ added: [{ user_id: 7, username: "Virt_7", display_name: "Virt 7" }], wanted: 4, why: "The room has as many virtual people as allowed" } as never);
    const user = userEvent.setup();
    render(<AddVirtual slug="party" onAdded={onAdded} />);
    await user.selectOptions(screen.getByLabelText("Số người ảo"), "4");
    await user.click(screen.getByRole("button", { name: "Thêm người ảo" }));
    const call = fetchMock.mock.calls.find(([path]) => String(path).endsWith("/virtual"));
    expect(call?.[0]).toBe("/api/chat/rooms/party/virtual");
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ count: 4 });
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("tells the page the people of the room changed, so the game of the room follows", async () => {
    fetchMock.mockResolvedValue({ added: [], wanted: 1, why: null } as never);
    const heard = vi.fn();
    window.addEventListener("sn:room-members-changed", heard);
    const user = userEvent.setup();
    render(<AddVirtual slug="party" />);
    await user.click(screen.getByRole("button", { name: "Thêm người ảo" }));
    await waitFor(() => expect(heard).toHaveBeenCalled());
    window.removeEventListener("sn:room-members-changed", heard);
  });

  it("shows why it could not add", async () => {
    fetchMock.mockRejectedValue(new ApiError(403, "Not a member"));
    const user = userEvent.setup();
    render(<AddVirtual slug="party" />);
    await user.click(screen.getByRole("button", { name: "Thêm người ảo" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
