import { apiFetch } from "@sn/api";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SearchPage from "../_pages/job";

vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 1, username: "alice", group: "user" } }) }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);
const job = (id: number, title: string) => ({ id, title, company: "Acme", location: "Hà Nội", remote: false, employment_type: "full_time", salary_min: null, salary_max: null, salary_currency: null, tags: ["python"], snippet: "", status: "open", expired: false, applied: false, saved: false, owner_username: "bob", created_at: "2025-01-01T00:00:00Z" });

beforeEach(() => {
  window.localStorage.clear();
  api.mockReset();
  api.mockImplementation(async (url: string) => {
    if (url.endsWith("/alerts")) return [];
    if (url.endsWith("/facets")) return { types: [{ name: "full_time", count: 2 }], locations: [{ name: "Hà Nội", count: 2 }, { name: "Huế", count: 1 }] };
    return { items: [job(1, "Python dev"), job(2, "Tester")], next_cursor: null };
  });
});

describe("the search of jobs", () => {
  it("shows the postings as cards beside trees of the types and the places", async () => {
    render(<SearchPage />);
    expect(await screen.findByRole("link", { name: "Python dev" })).toHaveAttribute("href", "/job/job/1");
    expect(await screen.findByRole("button", { name: /Huế \(1\)/ })).toBeInTheDocument();
  });

  it("asks again with the place when one is picked", async () => {
    render(<SearchPage />);
    await userEvent.click(await screen.findByRole("button", { name: /Huế \(1\)/ }));
    await waitFor(() => expect(api.mock.calls.some(([url]) => decodeURIComponent(String(url)).includes("location=Huế"))).toBe(true));
  });
});
