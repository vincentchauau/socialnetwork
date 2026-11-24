import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as sn from "@sn/api";
import { AuthGate } from "@sn/compounds/AuthGate";
import Page from "../_pages/file";
import DatabasePage from "../../app/database/page";
import { fileOf, listing } from "../file/helpers";

vi.mock("@sn/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@sn/api")>();
  return { ...real, apiFetch: vi.fn(), apiForm: vi.fn(), loadSession: vi.fn() };
});

const fetchMock = vi.mocked(sn.apiFetch);
const formMock = vi.mocked(sn.apiForm);
const sessionMock = vi.mocked(sn.loadSession);
const apiError = (status: number, detail?: string) =>
  new sn.ApiError(status, "x", detail ? { detail } : undefined);

const tablesBody = [{ name: "people", rows: 3 }];
const page = (n: number, total = 120) => ({ columns: ["id", "name"], rows: [[n, "<b>x</b>"], [null, true]], total, page: n, pageSize: 50 });

function route(handlers: Record<string, (url: string, init?: RequestInit) => unknown>) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const key = Object.keys(handlers).find((k) => url.startsWith(k));
    if (!key) throw new Error(`unrouted ${url}`);
    const out = handlers[key](url, init);
    if (out instanceof Error) throw out;
    return out;
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  formMock.mockReset();
  sessionMock.mockReset();
});
afterEach(() => vi.useRealTimers());

describe("the pages of File and Database", () => {
  const user = { id: 1, username: "a", group: "user" } as never;
  const admin = { id: 1, username: "a", group: "admin" } as never;

  beforeEach(() => {
    sessionMock.mockResolvedValue(user);
    route({
      "/api/file/entries": () => listing("/", []),
      "/api/database/tables": () => [],
    });
  });

  it("shows the file area on the page of File and the database area on the page of Database", async () => {
    const files = render(<Page />);
    expect(await screen.findByText(/^0 mục/)).toBeInTheDocument();
    expect(screen.queryByText(/Chưa có bảng nào/)).toBeNull();
    files.unmount();
    render(<DatabasePage />);
    expect((await screen.findAllByText("—")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/^0 mục/)).toBeNull();
  });

  it("has no Calls button, for an admin either", async () => {
    const first = render(<Page />);
    await screen.findByText(/^0 mục/);
    expect(screen.queryByRole("button", { name: "Calls" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Điều hướng" })).toBeNull();
    first.unmount();
    sessionMock.mockResolvedValue(admin);
    render(<Page />);
    await screen.findByText(/^0 mục/);
    expect(screen.queryByRole("button", { name: "Calls" })).toBeNull();
  });

  it("derives admin from the session role", async () => {
    sessionMock.mockResolvedValue({ id: 1, username: "a", group: "admin" } as never);
    const first = render(<Page />);
    await screen.findByText(/^0 mục/);
    first.unmount();
    sessionMock.mockResolvedValue({ id: 2, username: "b" });
    render(<Page />);
    await screen.findByText(/^0 mục/);
    expect(screen.queryByRole("button", { name: "Calls" })).toBeNull();
  });

  it("covers the AuthGate states", async () => {
    sessionMock.mockResolvedValue(null);
    const a = render(<AuthGate title="T">{() => <p>in</p>}</AuthGate>);
    expect(screen.getByText("Đang tải…")).toBeInTheDocument();
    expect(await screen.findByText("đăng nhập")).toBeInTheDocument();
    a.unmount();
    sessionMock.mockRejectedValue(new Error("down"));
    render(<AuthGate title="T">{() => <p>in</p>}</AuthGate>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối");
  });
});
