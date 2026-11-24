import { apiFetch, apiForm } from "@sn/api";
import { LocaleProvider } from "@sn/lib/i18n";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VersionsSection from "../../app/file/components/VersionsSection";
import { uploadFile } from "../../app/file/lib/api";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn(), apiForm: vi.fn() }));
const api = vi.mocked(apiFetch);
const form = vi.mocked(apiForm);

let kept: { id: string; size: number; savedAt: number }[] = [];
const methodOf = (call: unknown[]) => (call[1] as RequestInit | undefined)?.method ?? "GET";

beforeEach(() => {
  api.mockReset();
  form.mockReset();
  kept = [{ id: "a".repeat(16), size: 2048, savedAt: 1_780_000_100 }, { id: "b".repeat(16), size: 1024, savedAt: 1_780_000_000 }];
  api.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      kept = kept.filter((item) => item.id !== JSON.parse(String(init.body)).id);
      return { name: "a.txt", path: "/" } as never;
    }
    if (init?.method === "DELETE") {
      kept = kept.filter((item) => item.id !== new URL(url, "http://x").searchParams.get("id"));
      return undefined as never;
    }
    return { versions: kept, keepDays: 90 } as never;
  });
});

const show = (onRestored = vi.fn()) => {
  render(<LocaleProvider><VersionsSection path="/docs/a.txt" name="a.txt" onRestored={onRestored} onClose={() => undefined} /></LocaleProvider>);
  return onRestored;
};

describe("VersionsSection", () => {
  it("lists the earlier versions of one file with their size", async () => {
    show();
    expect(await screen.findAllByRole("button", { name: /Khôi phục|Restore/ })).toHaveLength(2);
    expect(screen.getByText(/2 KB|2,0 KB|2.0 KB/)).toBeInTheDocument();
    expect(api.mock.calls[0][0]).toBe("/api/file/versions?path=%2Fdocs%2Fa.txt");
    expect(screen.getByText(/90/)).toBeInTheDocument();
  });

  it("puts a version back and tells the files to read the folder again", async () => {
    const restored = show();
    const [first] = await screen.findAllByRole("button", { name: /Khôi phục|Restore/ });
    await userEvent.click(first);
    await waitFor(() => expect(restored).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(api.mock.calls.some((call) => methodOf(call) === "POST" && String(call[0]).endsWith("/versions/restore"))).toBe(true);
  });

  it("drops a version, and says when there are none", async () => {
    show();
    for (const _ of [0, 1]) await userEvent.click((await screen.findAllByRole("button", { name: /Xóa vĩnh viễn|Delete for good/ }))[0]);
    expect(await screen.findByText(/Chưa có phiên bản cũ|No earlier version/)).toBeInTheDocument();
    expect(within(document.body).queryAllByRole("button", { name: /Khôi phục|Restore/ })).toHaveLength(0);
  });
});

describe("uploading to replace", () => {
  it("asks the server to replace only when told to", async () => {
    form.mockResolvedValue({ name: "a.txt", size: 1 } as never);
    const file = new File(["x"], "a.txt");
    await uploadFile("/", file, "mine");
    await uploadFile("/", file, "mine", true);
    expect(String(form.mock.calls[0][0])).not.toContain("replace");
    expect(String(form.mock.calls[1][0])).toContain("&replace=true");
  });
});
