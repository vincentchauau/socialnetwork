import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, me, mockFetch } from "../center/helpers";

import ChatDock from "../../app/chat/dock/ChatDock";
import { LocaleProvider } from "@sn/lib/i18n";

type ChatProps = { userId: number; panels: Record<string, boolean>; onPanels?: (next: Record<string, boolean>) => void; onRoom?: (room: unknown) => void };
const chat = vi.hoisted(() => ({ props: [] as ChatProps[] }));
vi.mock("../../app/chat/components/EmbedChat", () => ({
  default: (props: ChatProps) => {
    chat.props.push(props);
    return <div data-testid="chat">chat</div>;
  },
}));

const show = (app = "market") =>
  render(
    <LocaleProvider>
      <ChatDock app={app} page={<p>the page</p>} />
    </LocaleProvider>,
  );

const serve = (signedIn: boolean) =>
  mockFetch((url) => (url.includes("/auth/me") ? (signedIn ? jsonResponse(me) : jsonResponse({ detail: "Not authenticated" }, 401)) : jsonResponse({}, 404)));

const pressed = (name: string) => screen.getByRole("button", { name }).getAttribute("aria-pressed");

beforeEach(() => {
  localStorage.clear();
  chat.props = [];
});

describe("the chat room under the page of an app", () => {
  it("splits the page and the chat, with a button for each, both on", async () => {
    serve(true);
    show();
    await screen.findByTestId("chat");
    expect(screen.getByText("the page")).toBeInTheDocument();
    expect(["Trang", "Chat"].map(pressed)).toEqual(["true", "true"]);
  });

  it("shows only the page to a person who is not signed in", async () => {
    serve(false);
    show();
    expect(await screen.findByText("the page")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Chat" })).not.toBeInTheDocument());
    expect(screen.queryByTestId("chat")).not.toBeInTheDocument();
  });

  it("gives the chat the parts that are on, and takes what its buttons say: Messages on, the other two off at first", async () => {
    serve(true);
    show("jobs");
    expect(await screen.findByTestId("chat")).toBeInTheDocument();
    expect(chat.props.at(-1)?.panels).toEqual({ rooms: false, members: false, messages: true });
    act(() => chat.props.at(-1)?.onPanels?.({ rooms: false, members: true, messages: true }));
    await waitFor(() => expect(chat.props.at(-1)?.panels).toEqual({ rooms: false, members: true, messages: true }));
  });

  it("takes the chat away with its button, and the page with its own, remembering both", async () => {
    serve(true);
    const user = userEvent.setup();
    const first = show("photos");
    await screen.findByTestId("chat");
    await user.click(screen.getByRole("button", { name: "Chat" }));
    expect(screen.queryByTestId("chat")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Trang" }));
    expect(JSON.parse(localStorage.getItem("sn_dock_photos_split") ?? "{}")).toEqual({ page: false, chat: false });
    first.unmount();
    show("photos");
    await waitFor(() => expect(pressed("Chat")).toBe("false"));
    expect(pressed("Trang")).toBe("false");
  });

  it("remembers the parts of the chat of each app apart", async () => {
    serve(true);
    const first = show("photos");
    await screen.findByTestId("chat");
    act(() => chat.props.at(-1)?.onPanels?.({ rooms: true, members: false, messages: true }));
    expect(JSON.parse(localStorage.getItem("sn_dock_photos") ?? "{}")).toEqual({ rooms: true, members: false, messages: true });
    first.unmount();
    chat.props = [];
    show("photos");
    await waitFor(() => expect(chat.props.at(-1)?.panels.rooms).toBe(true));
    document.body.innerHTML = "";
    chat.props = [];
    show("market");
    await waitFor(() => expect(chat.props.at(-1)?.panels.rooms).toBe(false));
  });

  it("tells the page which room is open", async () => {
    serve(true);
    const told = vi.fn();
    render(
      <LocaleProvider>
        <ChatDock app="werewolf" onRoom={told} page={<p>the page</p>} />
      </LocaleProvider>,
    );
    await screen.findByTestId("chat");
    act(() => chat.props.at(-1)?.onRoom?.({ slug: "village", members: 4 }));
    expect(told).toHaveBeenCalledWith({ slug: "village", members: 4 });
  });
});
