import { apiFetch } from "@sn/api";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import JobLibrary from "../../app/job/JobLibrary";

vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 1, username: "a", group: "user" } }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/job" }));
vi.mock("next/link", () => ({ default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => <a href={href} {...rest}>{children}</a> }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);

beforeEach(() => {
  api.mockReset();
  api.mockImplementation(async (url: string) => {
    if (url.includes("/ai/provider")) return { name: "dummy", is_dummy: true };
    if (/\/jobs(\?|$)/.test(url)) return { items: [], next_cursor: null };
    if (url.endsWith("/facets")) return { types: [], categories: [], skills: [], locations: [] };
    return [];
  });
});

describe("/job", () => {
  it("is a job site: search, saved jobs, applications and what the person posts, as tabs", async () => {
    render(<JobLibrary />);
    const tabs = await screen.findAllByRole("link");
    expect(tabs).toHaveLength(6);
    // The tabs: CRUD descriptions, saved descriptions, create application, update, approve, my applications; the page opens on create application.
    expect(tabs[2]).toHaveAttribute("aria-current", "page");
  });
});
