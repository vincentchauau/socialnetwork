import { ApiError } from "@sn/api";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CHAT_MAX_LENGTH } from "../app/components/ChatPanel";
import type { ChatMessage, Game } from "../app/lib/types";
import { FakeSocket, makeGame, makeRoom, player, WOLF } from "./helpers";
import { api, push, pushState, renderRoom, resetRoomTest } from "./roomHarness";

vi.mock("../app/lib/api", async () => (await import("./apiMock")).apiFactory());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: (path: string) => push(path) }) }));

beforeEach(resetRoomTest);

const msg = (seq: number, extra: Partial<ChatMessage> = {}): ChatMessage => ({
  seq,
  round: "Ngày 1",
  channel: "public",
  text: `tin ${seq}`,
  target: 0,
  dead: false,
  author: { id: 2, name: "Bình" },
  ...extra,
});

const day = (game: Partial<Game> = {}) =>
  makeRoom({ started: true, game: makeGame({ phase: "day", chatChannel: "public", ...game }) });

const box = () => screen.getByRole("textbox", { name: "Tin nhắn" });

describe("Chat channels", () => {
  it("shows the public channel by day with its history", async () => {
    await renderRoom(day({ chat: [msg(1), msg(2, { author: { id: 1, name: "alice" } })] }));
    expect(screen.getByRole("heading", { name: /Thảo luận/ })).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Tin nhắn" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(list).toHaveTextContent("tin 1");
  });

  it("shows the wolf channel title at night for wolves", async () => {
    await renderRoom(day({ phase: "night", chatChannel: "wolf", chat: [msg(1, { channel: "wolf", round: "Đêm 1" })] }));
    expect(screen.getByRole("heading", { name: /Chat riêng của Sói/ })).toBeInTheDocument();
  });

  it("shows the dead channel without the 'Nghi ai?' picker", async () => {
    await renderRoom(
      day({ me: { id: 1, name: "alice", alive: false, faction: WOLF, ability: { code: "KILL", label: "x" } }, chatChannel: "dead", chat: [msg(1, { channel: "dead", dead: true })] }),
    );
    expect(screen.getByRole("heading", { name: /Chat người chết/ })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Nghi ai?" })).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Tin nhắn" })).toHaveTextContent("💀 Bình");
  });

  it("offers no form when you cannot chat now (night, not a wolf)", async () => {
    await renderRoom(day({ phase: "night", chatChannel: null }));
    expect(screen.queryByRole("textbox", { name: "Tin nhắn" })).not.toBeInTheDocument();
    expect(screen.getByText(/Ban ngày mới chat công khai/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /chưa tới lượt chat/ })).toBeInTheDocument();
  });

  it("tells when there are no messages", async () => {
    await renderRoom(day());
    expect(screen.getByText("Chưa có tin nhắn nào.")).toBeInTheDocument();
  });
});

describe("Sending", () => {
  it("sends typed text and clears the draft, applying the returned message (deduped with the push)", async () => {
    const u = userEvent.setup();
    await renderRoom(day());
    api.chat.mockResolvedValue({ id: "ABCDE", message: msg(1, { text: "xin chào", author: { id: 1, name: "alice" } }) });
    await u.type(box(), "xin chào");
    await u.click(screen.getByRole("button", { name: "Gửi" }));
    expect(api.chat).toHaveBeenCalledWith("ABCDE", "xin chào", 0);
    await waitFor(() => expect(box()).toHaveValue(""));
    expect(screen.getByRole("list", { name: "Tin nhắn" })).toHaveTextContent("xin chào");
    act(() => FakeSocket.last().push({ type: "chat", message: msg(1, { text: "xin chào", author: { id: 1, name: "alice" } }) }));
    expect(within(screen.getByRole("list", { name: "Tin nhắn" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("sends with Enter", async () => {
    const u = userEvent.setup();
    await renderRoom(day());
    api.chat.mockResolvedValue({ id: "ABCDE", message: msg(1) });
    await u.type(box(), "ok{Enter}");
    expect(api.chat).toHaveBeenCalledWith("ABCDE", "ok", 0);
  });

  it("trims, and refuses blank text", async () => {
    const u = userEvent.setup();
    await renderRoom(day());
    const send = screen.getByRole("button", { name: "Gửi" });
    expect(send).toBeDisabled();
    await u.type(box(), "   ");
    expect(send).toBeDisabled();
    await u.type(box(), "{Enter}");
    expect(api.chat).not.toHaveBeenCalled();
    api.chat.mockResolvedValue({ id: "ABCDE", message: msg(1) });
    await u.type(box(), "  hi  {Enter}");
    expect(api.chat).toHaveBeenCalledWith("ABCDE", "hi", 0);
  });

  it("limits a message to 140 characters and counts them", async () => {
    const u = userEvent.setup();
    await renderRoom(day());
    expect(box()).toHaveAttribute("maxlength", String(CHAT_MAX_LENGTH));
    await u.click(box());
    await u.paste("x".repeat(200));
    expect((box() as HTMLInputElement).value).toHaveLength(140);
    expect(screen.getByText("140/140")).toBeInTheDocument();
  });

  it("sends a quick reaction at once without touching the draft", async () => {
    const u = userEvent.setup();
    await renderRoom(day());
    api.chat.mockResolvedValue({ id: "ABCDE", message: msg(1, { text: "🤔" }) });
    await u.type(box(), "bản nháp");
    await u.click(screen.getByRole("button", { name: "Gửi 🤔" }));
    expect(api.chat).toHaveBeenCalledWith("ABCDE", "🤔", 0);
    expect(box()).toHaveValue("bản nháp");
  });

  it("attaches the suspect picked with 'Nghi ai?' and resets it after sending", async () => {
    const u = userEvent.setup();
    await renderRoom(day());
    const group = screen.getByRole("group", { name: "Nghi ai?" });
    expect(within(group).getByRole("button", { name: /Nghi ai\?/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(group).queryByRole("button", { name: "alice" })).not.toBeInTheDocument(); // not yourself
    await u.click(within(group).getByRole("button", { name: "Cường" }));
    expect(within(group).getByRole("button", { name: "Cường" })).toHaveAttribute("aria-pressed", "true");
    api.chat.mockResolvedValue({ id: "ABCDE", message: msg(1, { text: "hmm", target: 3 }) });
    await u.type(box(), "hmm{Enter}");
    expect(api.chat).toHaveBeenCalledWith("ABCDE", "hmm", 3);
    await waitFor(() => expect(within(group).getByRole("button", { name: /Nghi ai\?/ })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("list", { name: "Tin nhắn" })).toHaveTextContent("→ Cường");
    await u.click(within(group).getByRole("button", { name: "Cường" }));
    await u.click(within(group).getByRole("button", { name: /Nghi ai\?/ }));
    expect(within(group).getByRole("button", { name: "Cường" })).toHaveAttribute("aria-pressed", "false");
  });

  it("does not offer dead players as suspects", async () => {
    await renderRoom(day({ players: [player(1, "alice"), player(2, "Bình", { alive: false }), player(3, "Cường")] }));
    const group = screen.getByRole("group", { name: "Nghi ai?" });
    expect(within(group).queryByRole("button", { name: "Bình" })).not.toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Cường" })).toBeInTheDocument();
  });

  it("keeps the text and toasts the server's refusal (too fast)", async () => {
    const u = userEvent.setup();
    await renderRoom(day());
    api.chat.mockRejectedValue(new ApiError(400, "Bạn nhắn quá nhanh", { detail: "Bạn nhắn quá nhanh" }));
    await u.type(box(), "nhanh{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Bạn nhắn quá nhanh");
    expect(box()).toHaveValue("nhanh");
    expect(screen.getByRole("button", { name: "Gửi" })).toBeEnabled();
  });

  it("maps a rate limit to Vietnamese", async () => {
    const u = userEvent.setup();
    await renderRoom(day());
    api.chat.mockRejectedValue(new ApiError(429, "Too Many Requests"));
    await u.type(box(), "a{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Bạn thao tác quá nhanh");
  });
});

describe("Messages are plain text", () => {
  it("renders markup as text and never as HTML", async () => {
    const hostile = '<img src=x onerror="alert(1)"><script>alert(2)</script><b>bold</b>';
    await renderRoom(day({ chat: [msg(1, { text: hostile, author: { id: 2, name: "<i>Bình</i>" } })] }));
    const item = within(screen.getByRole("list", { name: "Tin nhắn" })).getByRole("listitem");
    expect(item).toHaveTextContent(hostile);
    expect(item.querySelector("img, script, b, i")).toBeNull();
  });

  it("shows pushed chat live", async () => {
    await renderRoom(day());
    act(() => FakeSocket.last().push({ type: "chat", message: msg(5, { text: "từ socket" }) }));
    expect(await screen.findByText("từ socket")).toBeInTheDocument();
  });

  it("keeps the chat when a state snapshot arrives", async () => {
    await renderRoom(day());
    pushState(day({ chat: [msg(1), msg(2)] }));
    expect(within(screen.getByRole("list", { name: "Tin nhắn" })).getAllByRole("listitem")).toHaveLength(2);
  });

  it("shows '?' for a target that is not in the player list", async () => {
    await renderRoom(day({ chat: [msg(1, { target: 99 })] }));
    expect(screen.getByRole("list", { name: "Tin nhắn" })).toHaveTextContent("→ ?");
  });
});
