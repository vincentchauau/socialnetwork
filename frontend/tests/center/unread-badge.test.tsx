import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, me, mockFetch } from "./helpers";

import { LocaleProvider } from "@sn/lib/i18n";
import SiteBar from "@sn/complex/SiteBar";

const SUMMARY_URL = "/api/chat/inbox/summary";

const show = () =>
  render(
    <LocaleProvider>
      <SiteBar name="Chat" href="/chat" />
    </LocaleProvider>,
  );

beforeEach(() => {
  localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
});

/** A server: the session answers `signedIn`, the summary answers `summary` (a status when it is a number). */
function serve(signedIn: boolean, summary: unknown) {
  return mockFetch((url) => {
    if (url.includes("/auth/me")) return signedIn ? jsonResponse(me) : jsonResponse({ detail: "Not authenticated" }, 401);
    if (url.includes(SUMMARY_URL)) return typeof summary === "number" ? jsonResponse({ detail: "x" }, summary) : jsonResponse(summary);
    return jsonResponse({}, 404);
  });
}

describe("the number of what waits in the chat, in the bar of every app", () => {
  it("adds up the unread messages, the requests to write and the notices, and leads to the chat", async () => {
    serve(true, { messages: 3, requests: 1, notices: 2 });
    show();
    const link = await screen.findByRole("link", { name: /6/ });
    expect(link).toHaveAttribute("href", "/chat");
    expect(link).toHaveTextContent("6");
    expect(link.getAttribute("aria-label")).toContain("Hộp thư");
  });

  it("shows 99+ for a great many", async () => {
    serve(true, { messages: 150, requests: 0, notices: 0 });
    show();
    expect(await screen.findByRole("link", { name: /150/ })).toHaveTextContent("99+");
  });

  it("shows nothing when nothing waits", async () => {
    const fetcher = serve(true, { messages: 0, requests: 0, notices: 0 });
    show();
    await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes(SUMMARY_URL))).toBe(true));
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("asks nothing of the chat while nobody is signed in", async () => {
    const fetcher = serve(false, { messages: 9, requests: 9, notices: 9 });
    show();
    await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes("/auth/me"))).toBe(true));
    expect(fetcher.mock.calls.some(([url]) => String(url).includes(SUMMARY_URL))).toBe(false);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows no number, and breaks nothing, when the chat does not answer", async () => {
    const fetcher = serve(true, 503);
    show();
    await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes(SUMMARY_URL))).toBe(true));
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("looks again when the page is looked at again", async () => {
    let waiting = 1;
    const fetcher = mockFetch((url) => {
      if (url.includes("/auth/me")) return jsonResponse(me);
      return jsonResponse({ messages: waiting, requests: 0, notices: 0 });
    });
    show();
    expect(await screen.findByRole("link", { name: /1/ })).toHaveTextContent("1");
    waiting = 4;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(screen.getByRole("link")).toHaveTextContent("4"));
    expect(fetcher.mock.calls.filter(([url]) => String(url).includes(SUMMARY_URL)).length).toBeGreaterThanOrEqual(2);
  });
});
