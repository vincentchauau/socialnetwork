import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SiteBar from "@sn/complex/SiteBar";
import DatabasePage from "../../app/database/page";
import FilePage from "../_pages/file";
import { listing } from "../file/helpers";

const path = vi.hoisted(() => ({ current: "/chat" }));
vi.mock("next/navigation", () => ({ usePathname: () => path.current }));

const session = vi.hoisted(() => ({ loadSession: vi.fn() }));
vi.mock("@sn/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sn/api")>()),
  apiFetch: vi.fn(async (url: string) => (url.includes("/entries") ? listing("/", []) : [])),
  loadSession: session.loadSession,
  refreshSession: vi.fn(),
}));

beforeEach(() => {
  path.current = "/chat";
  session.loadSession.mockReset();
  session.loadSession.mockResolvedValue(null); // the greeting of the bar asks for the session
});

describe("the chat bar (the shared site bar)", () => {
  it("has no menu button: the name of the page and the tools are right in the bar", async () => {
    render(<SiteBar name="Chat" href="/chat" />);
    const bar = screen.getByRole("navigation", { name: "Điều hướng chính" });
    expect(within(bar).queryByRole("button", { name: /Menu|Thực đơn/i })).not.toBeInTheDocument();
    expect(within(bar).queryByRole("button", { name: /Cá nhân và dữ liệu/ })).not.toBeInTheDocument();
    expect(await within(bar).findByRole("combobox", { name: /Ngôn ngữ|Language/ })).toBeInTheDocument(); // the language, beside the name
  });
});

describe("the work pages", () => {
  it("ask an anonymous visitor to sign in", async () => {
    session.loadSession.mockResolvedValue(null);
    render(<FilePage />);
    expect(await screen.findByText("đăng nhập")).toBeInTheDocument();
  });

  it("show the file area and the database area, with no Calls button for anyone (an admin included)", async () => {
    session.loadSession.mockResolvedValue({ id: 1, username: "root", group: "admin" });
    const file = render(<FilePage />);
    expect(await screen.findByText(/^0 mục/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Calls" })).toBeNull();
    file.unmount();
    const database = render(<DatabasePage />);
    expect((await screen.findAllByText("—")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Calls" })).toBeNull();
    database.unmount();
  });
});
