import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../app/chat/dock/PageDock", () => ({
  default: ({ app, except, children }: { app: string; except?: string[]; children: React.ReactNode }) => (
    <div data-testid="page-dock" data-app={app} data-except={(except ?? []).join(",")}>{children}</div>
  ),
}));
vi.mock("@sn/complex/SiteBar", () => ({ default: () => null }));
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

const layouts: Array<[string, () => Promise<{ default: (p: { children: React.ReactNode }) => React.ReactElement }>, string, string]> = [
  ["center", () => import("../../app/center/layout"), "center", ""],
  ["chat", () => import("../../app/chat/layout"), "chat", "/chat"],
  ["database", () => import("../../app/database/layout"), "database", ""],
  ["face", () => import("../../app/face/layout"), "face", ""],
  ["file", () => import("../../app/file/layout"), "file", ""],
  ["job", () => import("../../app/job/layout"), "jobs", "/job/job/"],
  ["market", () => import("../../app/market/layout"), "market", "/market/products/"],
  ["roulette", () => import("../../app/roulette/layout"), "roulette", ""],
  ["werewolf", () => import("../../app/werewolf/layout"), "werewolf", "/werewolf"],
];

describe("every app layout wraps its pages in PageDock", () => {
  it.each(layouts)("%s", async (_name, load, app, except) => {
    const Layout = (await load()).default;
    render(<Layout><p>the page</p></Layout>);
    const dock = screen.getByTestId("page-dock");
    expect(dock).toHaveAttribute("data-app", app);
    expect(dock).toHaveAttribute("data-except", except);
    expect(dock).toHaveTextContent("the page");
  });
});
