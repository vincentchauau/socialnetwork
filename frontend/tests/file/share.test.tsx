import { ApiError, apiFetch } from "@sn/api";
import { LocaleProvider } from "@sn/lib/i18n";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SearchPanel from "../../app/file/components/SearchPanel";
import ShareSection from "../../app/file/components/ShareSection";
import SharedFilePage from "../../app/file/s/[token]/page";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));
vi.mock("next/navigation", () => ({ useParams: () => ({ token: "abcDEF1234567890" }) }));
const api = vi.mocked(apiFetch);

const inLocale = (ui: React.ReactElement) => render(<LocaleProvider>{ui}</LocaleProvider>);
const share = { token: "tok1234567890abc", path: "/docs/a.txt", page: "/file/s/tok1234567890abc", size: 5, createdAt: 1_780_000_000, expiresAt: null };
const methodOf = (call: unknown[]) => (call[1] as RequestInit | undefined)?.method ?? "GET";

beforeEach(() => api.mockReset());

describe("ShareSection", () => {
  it("makes a link that lasts as long as asked, copies it and takes it back", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    api.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") return share as never;
      if (init?.method === "DELETE") return undefined as never;
      return { shares: [] } as never;
    });
    inLocale(<ShareSection path="/docs/a.txt" name="a.txt" onClose={() => undefined} />);
    await userEvent.selectOptions(await screen.findByRole("combobox"), "7");
    await userEvent.click(screen.getByRole("button", { name: /Tạo liên kết|Make a link/ }));
    const post = api.mock.calls.find((call) => methodOf(call) === "POST");
    expect(post?.[0]).toBe("/api/file/share");
    expect(JSON.parse(String((post?.[1] as RequestInit).body))).toEqual({ path: "/docs/a.txt", days: 7 });
    await userEvent.click(await screen.findByRole("button", { name: /Sao chép liên kết|Copy link/ }));
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/file/s/tok1234567890abc`);
    await userEvent.click(screen.getByRole("button", { name: /Thu hồi liên kết|Take the link back/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Tạo liên kết|Make a link/ })).toBeInTheDocument());
    expect(api.mock.calls.find((call) => methodOf(call) === "DELETE")?.[0]).toBe("/api/file/share/tok1234567890abc");
  });

  it("shows the link the file already has", async () => {
    api.mockResolvedValue({ shares: [share, { ...share, path: "/other.txt", token: "zzz1234567890abc" }] } as never);
    inLocale(<ShareSection path="/docs/a.txt" name="a.txt" onClose={() => undefined} />);
    expect(await screen.findByRole("button", { name: /Sao chép liên kết|Copy link/ })).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("says so when the link could not be made", async () => {
    api.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") throw new ApiError(409, "full", {});
      return { shares: [] } as never;
    });
    inLocale(<ShareSection path="/a.txt" name="a.txt" onClose={() => undefined} />);
    await userEvent.click(await screen.findByRole("button", { name: /Tạo liên kết|Make a link/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("SearchPanel", () => {
  it("looks by name in every folder and opens the folder of a result", async () => {
    api.mockResolvedValue({ entries: [{ name: "holiday.jpg", parent: "/Photos/trip", type: "file", size: 2048 }, { name: "Photos", parent: "/", type: "folder", size: 0 }], more: false } as never);
    const open = vi.fn();
    inLocale(<SearchPanel onOpen={open} />);
    expect(screen.queryByRole("button", { name: /^(Tìm|Find)$/ })).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "p{Enter}");
    expect(api).not.toHaveBeenCalled(); // two letters at least
    await userEvent.type(screen.getByRole("searchbox"), "h{Enter}");
    expect(api).toHaveBeenCalledWith("/api/file/search?q=ph");
    await userEvent.click(await screen.findByRole("button", { name: /holiday\.jpg/ }));
    expect(open).toHaveBeenLastCalledWith("/Photos/trip"); // a file opens the folder it is in
    await userEvent.click(screen.getByRole("button", { name: /^📁 Photos/ }));
    expect(open).toHaveBeenLastCalledWith("/Photos"); // a folder opens itself
  });

  it("says when there is nothing and when there is more", async () => {
    api.mockResolvedValueOnce({ entries: [], more: false } as never);
    inLocale(<SearchPanel onOpen={() => undefined} />);
    await userEvent.type(screen.getByRole("searchbox"), "zz{Enter}");
    expect(await screen.findByText(/Không thấy gì|Nothing found/)).toBeInTheDocument();
  });
});

describe("the page of a shared file", () => {
  it("shows the name and the size, with a download that needs no sign-in", async () => {
    api.mockResolvedValue({ name: "report.txt", size: 2048, modifiedAt: 1_780_000_000, download: "/shared/abcDEF1234567890/download" } as never);
    inLocale(<SharedFilePage />);
    expect(await screen.findByText(/report\.txt/)).toBeInTheDocument();
    expect(api).toHaveBeenCalledWith("/api/file/shared/abcDEF1234567890");
    expect(screen.getByRole("link", { name: /Tải xuống|Download/ })).toHaveAttribute("href", "/api/file/shared/abcDEF1234567890/download");
  });

  it("says the link does not work when it is gone or ran out", async () => {
    api.mockImplementation(async (url: string) => {
      if (String(url).includes("/shared/")) throw new ApiError(404, "gone", {});
      return {} as never;
    });
    inLocale(<SharedFilePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/không còn dùng được|does not work any more/);
  });
});
