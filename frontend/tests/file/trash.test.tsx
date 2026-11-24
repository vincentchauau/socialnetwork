import { apiFetch } from "@sn/api";
import { LocaleProvider } from "@sn/lib/i18n";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TrashPanel from "../../app/file/components/TrashPanel";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));
const api = vi.mocked(apiFetch);

const item = (id: string, name: string, extra: object = {}) => ({ id, name, parent: "/docs", type: "file", size: 2048, deletedAt: 1_780_000_000, ...extra });
const methodOf = (call: unknown[]) => (call[1] as RequestInit | undefined)?.method ?? "GET";

let trash: ReturnType<typeof item>[] = [];

beforeEach(() => {
  api.mockReset();
  trash = [item("a".repeat(16), "report.txt"), item("b".repeat(16), "photos", { type: "folder" })];
  api.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const id = JSON.parse(String(init.body)).id as string;
      const gone = trash.find((entry) => entry.id === id)!;
      trash = trash.filter((entry) => entry.id !== id);
      return { name: gone.name, path: gone.parent } as never;
    }
    if (init?.method === "DELETE") {
      const id = new URL(url, "http://x").searchParams.get("id");
      trash = id ? trash.filter((entry) => entry.id !== id) : [];
      return undefined as never;
    }
    return { entries: trash, keepDays: 30 } as never;
  });
});

const show = (onRestored = vi.fn()) => {
  render(<LocaleProvider><TrashPanel onRestored={onRestored} /></LocaleProvider>);
  return onRestored;
};

describe("TrashPanel", () => {
  it("lists what was deleted with where it was, and says how long it stays", async () => {
    show();
    expect(await screen.findByText("report.txt")).toBeInTheDocument();
    expect(screen.getByText("photos")).toBeInTheDocument();
    expect(screen.getAllByText(/\/docs/)).toHaveLength(2);
    expect(screen.getByText(/30/)).toBeInTheDocument();
  });

  it("puts an item back, says where, and tells the files to read the folder again", async () => {
    const restored = show();
    const row = (await screen.findByText("report.txt")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: /Khôi phục|Restore/ }));
    await waitFor(() => expect(screen.queryByText("report.txt")).toBeNull());
    expect(restored).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent(/report\.txt/);
    expect(api.mock.calls.some((call) => methodOf(call) === "POST" && String(call[0]).endsWith("/trash/restore"))).toBe(true);
  });

  it("asks before it erases an item or the whole trash for good", async () => {
    show();
    const row = (await screen.findByText("photos")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: /Xóa vĩnh viễn|Delete for good/ }));
    expect(api.mock.calls.some((call) => methodOf(call) === "DELETE")).toBe(false);
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: /Xóa vĩnh viễn|Delete for good/ }));
    await waitFor(() => expect(screen.queryByText("photos")).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: /Dọn sạch thùng rác|Empty the trash/ }));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: /Xóa vĩnh viễn|Delete for good/ }));
    expect(await screen.findByText(/Thùng rác trống|The trash is empty/)).toBeInTheDocument();
  });

  it("shows the problem when an item cannot be put back", async () => {
    api.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") throw new Error("Vượt quá dung lượng 100 MB");
      return { entries: trash, keepDays: 30 } as never;
    });
    show();
    const row = (await screen.findByText("report.txt")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: /Khôi phục|Restore/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("report.txt")).toBeInTheDocument();
  });
});
