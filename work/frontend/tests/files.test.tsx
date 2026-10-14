import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as sn from "@sn/api";
import FilesPanel from "../app/components/FilesPanel";
import { breadcrumbs, downloadUrl, exportUrl, formatBytes, joinPath, nameProblem, uploadUrl } from "../app/lib/paths";
import { errorText } from "../app/lib/errors";
import { file, fileOf, folder, listing } from "./helpers";

vi.mock("@sn/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@sn/api")>();
  return { ...real, apiFetch: vi.fn(), apiForm: vi.fn(), loadSession: vi.fn() };
});

const fetchMock = vi.mocked(sn.apiFetch);
const formMock = vi.mocked(sn.apiForm);
const apiError = (status: number, detail?: string) =>
  new sn.ApiError(status, "x", detail ? { detail } : undefined);

beforeEach(() => {
  fetchMock.mockReset();
  formMock.mockReset();
});

describe("path helpers", () => {
  it("builds breadcrumbs and joins paths", () => {
    expect(breadcrumbs("/")).toEqual([{ label: "Thư mục gốc", path: "/" }]);
    expect(breadcrumbs("/a/b").map((c) => c.path)).toEqual(["/", "/a", "/a/b"]);
    expect(joinPath("/", "x")).toBe("/x");
    expect(joinPath("/a", "x")).toBe("/a/x");
  });

  it("validates names", () => {
    expect(nameProblem("ok")).toBeNull();
    for (const bad of ["", "  ", ".", "..", "a/b", "a\\b", "x".repeat(101)]) expect(nameProblem(bad)).not.toBeNull();
  });

  it("encodes user text in urls", () => {
    expect(downloadUrl("/a b/ü&x=1#.txt")).toBe(`/api/work/files/download?path=${encodeURIComponent("/a b/ü&x=1#.txt")}`);
    expect(uploadUrl("/a&b")).toContain("%26");
    expect(exportUrl("t&x")).toBe("/api/work/db/export?table=t%26x");
  });

  it("formats sizes", () => {
    expect(formatBytes(5)).toBe("5 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });

  it("maps errors to Vietnamese", () => {
    expect(errorText(apiError(429))).toContain("quá nhanh");
    expect(errorText(apiError(409))).toContain("đã tồn tại");
    expect(errorText(apiError(400, "Lỗi SQL"))).toBe("Lỗi SQL");
    expect(errorText(apiError(500))).toContain("Đã xảy ra lỗi");
    expect(errorText(new Error("boom"), "dự phòng")).toBe("dự phòng");
    for (const s of [401, 403, 404, 413, 422]) expect(errorText(apiError(s))).not.toContain("Đã xảy ra lỗi");
  });
});

describe("FilesPanel", () => {
  it("lists folders first and renders hostile names as text", async () => {
    const hostile = '<img src=x onerror="alert(1)">';
    fetchMock.mockResolvedValue(listing("/", [file("b.txt"), file(hostile), folder("zeta"), folder("alpha")]));
    const { container } = render(<FilesPanel />);
    expect(await screen.findByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    const names = Array.from(container.querySelectorAll("#fileGridView .file-name")).map((n) => n.textContent);
    expect(names).toEqual(["alpha", "zeta", hostile, "b.txt"].sort((x, y) => (x === "alpha" || x === "zeta" ? -1 : 1) - (y === "alpha" || y === "zeta" ? -1 : 1) || x.localeCompare(y, "vi")));
    expect(names.indexOf("alpha")).toBeLessThan(names.indexOf("b.txt"));
    expect(fetchMock).toHaveBeenCalledWith("/api/work/files?path=%2F");
  });

  it("navigates into folders and back with the breadcrumb", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("%2Fdocs") ? listing("/docs", []) : listing("/", [folder("docs")]),
    );
    render(<FilesPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Mở thư mục docs" }));
    expect(await screen.findByText("Thư mục này đang trống.")).toBeInTheDocument();
    expect(screen.getByText("docs", { selector: "[aria-current]" })).toBeInTheDocument();
    expect(screen.getByText("Current Path: /docs")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Thư mục gốc" }));
    expect(await screen.findByRole("button", { name: "Mở thư mục docs" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "📁 docs" })); // the folder tree on the left
    expect(await screen.findByText("Current Path: /docs")).toBeInTheDocument();
  });

  it("shows a load error", async () => {
    fetchMock.mockRejectedValue(apiError(403));
    render(<FilesPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("không có quyền");
  });

  it("controls the grid columns from 1 to 10, clamping and ignoring junk", async () => {
    fetchMock.mockResolvedValue(listing("/", [file("a")]));
    const { container } = render(<FilesPanel />);
    await screen.findByText("a");
    const grid = container.querySelector("#fileGridView") as HTMLElement;
    const input = screen.getByLabelText("Columns:");
    expect(input).toHaveValue(1);
    expect(grid.style.gridTemplateColumns).toBe("repeat(1, 1fr)");
    fireEvent.change(input, { target: { value: "99" } });
    expect(grid.style.gridTemplateColumns).toBe("repeat(10, 1fr)");
    fireEvent.change(input, { target: { value: "0" } });
    expect(grid.style.gridTemplateColumns).toBe("repeat(1, 1fr)");
    fireEvent.change(input, { target: { value: "4" } });
    fireEvent.change(input, { target: { value: "" } }); // mid-edit keeps the last valid value
    expect(grid.style.gridTemplateColumns).toBe("repeat(4, 1fr)");
    fireEvent.blur(input);
    expect(input).toHaveValue(4);
  });

  it("splits Folders and Files like the original (30/70)", async () => {
    fetchMock.mockResolvedValue(listing("/", []));
    const { container } = render(<FilesPanel />);
    await screen.findByText("Thư mục này đang trống.");
    expect(screen.getByRole("heading", { name: "Folders" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Files & Subfolders" })).toBeInTheDocument();
    expect((container.querySelector("#fileSplitter > div:first-child") as HTMLElement).style.width).toBe("30%");
  });

  it("shows usage and warns at 90%", async () => {
    fetchMock.mockResolvedValue(listing("/", [], 95, 100));
    render(<FilesPanel />);
    expect(await screen.findByText(/Sắp hết dung lượng/)).toBeInTheDocument();
    expect(screen.getByText(/Đã dùng 95 B \/ 100 B/)).toBeInTheDocument();
  });

  it("creates a folder, validating the name and depth", async () => {
    fetchMock.mockResolvedValue(listing("/", []));
    render(<FilesPanel />);
    await screen.findByText("Thư mục này đang trống.");
    await userEvent.click(screen.getByRole("button", { name: "Tạo thư mục" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Hãy nhập tên");
    await userEvent.type(screen.getByLabelText("Tên thư mục mới"), "a/b");
    await userEvent.click(screen.getByRole("button", { name: "Tạo thư mục" }));
    expect(screen.getByRole("alert")).toHaveTextContent("không được chứa");
    await userEvent.clear(screen.getByLabelText("Tên thư mục mới"));
    await userEvent.type(screen.getByLabelText("Tên thư mục mới"), "new");
    await userEvent.click(screen.getByRole("button", { name: "Tạo thư mục" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/work/files/folder", {
        method: "POST",
        body: JSON.stringify({ path: "/", name: "new" }),
      }),
    );
    expect(await screen.findByText("Đã tạo thư mục.")).toBeInTheDocument();
  });

  it("refuses folders deeper than 6 levels", async () => {
    let current = "/a/b/c/d/e/f";
    fetchMock.mockImplementation(async (url: string) => {
      const p = decodeURIComponent(url.split("path=")[1]);
      current = p;
      return listing(p, p === "/a/b/c/d/e" ? [folder("f")] : p === "/a/b/c/d" ? [folder("e")] : p === "/a/b/c" ? [folder("d")] : p === "/a/b" ? [folder("c")] : p === "/a" ? [folder("b")] : p === "/" ? [folder("a")] : []);
    });
    render(<FilesPanel />);
    for (const n of ["a", "b", "c", "d", "e", "f"]) await userEvent.click(await screen.findByRole("button", { name: `Mở thư mục ${n}` }));
    await waitFor(() => expect(current).toBe("/a/b/c/d/e/f"));
    await userEvent.type(await screen.findByLabelText("Tên thư mục mới"), "g");
    await userEvent.click(screen.getByRole("button", { name: "Tạo thư mục" }));
    expect(screen.getByRole("alert")).toHaveTextContent("tối đa 6 cấp");
  });

  it("reports a collision when creating a folder", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") throw apiError(409);
      return listing("/", []);
    });
    render(<FilesPanel />);
    await screen.findByText("Thư mục này đang trống.");
    await userEvent.type(screen.getByLabelText("Tên thư mục mới"), "dup");
    await userEvent.click(screen.getByRole("button", { name: "Tạo thư mục" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("đã tồn tại");
  });

  it("uploads files and rejects oversize or over-quota ones client side", async () => {
    fetchMock.mockResolvedValue(listing("/dir", [], 0, 1000));
    formMock.mockResolvedValue({ name: "ok.txt", size: 10 });
    const { container } = render(<FilesPanel />);
    await screen.findByText("Thư mục này đang trống.");
    const input = container.querySelector("#work-upload") as HTMLInputElement;
    await userEvent.upload(input, [fileOf("ok.txt", 10), fileOf("big.bin", 21 * 1024 * 1024), fileOf("quota.bin", 5000)]);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("big.bin: tệp lớn hơn 20 MB");
    expect(alert).toHaveTextContent("quota.bin: không đủ dung lượng");
    expect(formMock).toHaveBeenCalledTimes(1);
    expect(formMock.mock.calls[0][0]).toBe("/api/work/files/upload?path=%2F");
    expect((formMock.mock.calls[0][1] as FormData).get("file")).toBeInstanceOf(File);
    expect(screen.getByText("Đã tải lên 1 tệp.")).toBeInTheDocument();
  });

  it.each([
    [413, "quá lớn"],
    [409, "đã tồn tại"],
    [429, "quá nhanh"],
  ])("maps upload error %i", async (status, text) => {
    fetchMock.mockResolvedValue(listing("/", []));
    formMock.mockRejectedValue(apiError(status));
    const { container } = render(<FilesPanel />);
    await screen.findByText("Thư mục này đang trống.");
    fireEvent.change(container.querySelector("#work-upload") as HTMLInputElement, { target: { files: [fileOf("a.txt", 5)] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.getByRole("button", { name: "Tải tệp lên" })).toBeEnabled();
  });

  it("uploads via drag and drop and ignores empty drops", async () => {
    fetchMock.mockResolvedValue(listing("/", []));
    formMock.mockResolvedValue({ name: "d.txt", size: 1 });
    render(<FilesPanel />);
    await screen.findByText("Thư mục này đang trống.");
    const zone = screen.getByTestId("dropzone");
    fireEvent.dragOver(zone);
    expect(zone).toHaveStyle({ borderStyle: "solid" });
    fireEvent.dragLeave(zone);
    expect(zone).toHaveStyle({ borderStyle: "dashed" });
    fireEvent.drop(zone, { dataTransfer: { files: [] } });
    expect(formMock).not.toHaveBeenCalled();
    fireEvent.drop(zone, { dataTransfer: { files: [fileOf("d.txt", 1)] } });
    await waitFor(() => expect(formMock).toHaveBeenCalledTimes(1));
  });

  it("opens the hidden input from the button", async () => {
    fetchMock.mockResolvedValue(listing("/", []));
    const { container } = render(<FilesPanel />);
    await screen.findByText("Thư mục này đang trống.");
    const click = vi.spyOn(container.querySelector("#work-upload") as HTMLInputElement, "click");
    await userEvent.click(screen.getByRole("button", { name: "Tải tệp lên" }));
    expect(click).toHaveBeenCalled();
  });

  it("renders an encoded download link only for files", async () => {
    fetchMock.mockResolvedValue(listing("/", [file("a&b #1.txt"), folder("d")]));
    render(<FilesPanel />);
    const link = await screen.findByRole("link", { name: "Tải xuống a&b #1.txt" });
    expect(link).toHaveAttribute("href", "/api/work/files/download?path=%2Fa%26b%20%231.txt");
    expect(link).toHaveAttribute("download", "a&b #1.txt");
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("renames an entry, with validation, cancel and conflict handling", async () => {
    let fail = false;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        if (fail) throw apiError(409);
        return undefined;
      }
      return listing("/", [file("old.txt")]);
    });
    render(<FilesPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Đổi tên old.txt" }));
    await userEvent.click(screen.getByRole("button", { name: "Huỷ" }));
    await userEvent.click(screen.getByRole("button", { name: "Đổi tên old.txt" }));
    const box = screen.getByLabelText("Tên mới");
    await userEvent.clear(box);
    await userEvent.type(box, "..");
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(screen.getByRole("alert")).toHaveTextContent("không được chứa");
    await userEvent.clear(box);
    await userEvent.type(box, "dup.txt");
    fail = true;
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText(/đã tồn tại/)).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Đổi tên old.txt" }));
    const box2 = screen.getByLabelText("Tên mới");
    await userEvent.clear(box2);
    await userEvent.type(box2, "new.txt");
    await userEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/work/files/rename", {
        method: "POST",
        body: JSON.stringify({ path: "/old.txt", newName: "new.txt" }),
      }),
    );
    expect(await screen.findByText("Đã đổi tên.")).toBeInTheDocument();
  });

  it("deletes after confirmation and can cancel", async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === "DELETE" ? undefined : listing("/", [folder("a b")]),
    );
    render(<FilesPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Xoá a b" }));
    expect(screen.getByRole("group", { name: "Xác nhận xoá" })).toHaveTextContent("toàn bộ nội dung");
    await userEvent.click(screen.getByRole("button", { name: "Huỷ" }));
    expect(fetchMock).not.toHaveBeenCalledWith(expect.anything(), { method: "DELETE" });
    await userEvent.click(screen.getByRole("button", { name: "Xoá a b" }));
    const group = screen.getByRole("group", { name: "Xác nhận xoá" });
    await userEvent.click(within(group).getByRole("button", { name: "Xác nhận xoá" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/work/files?path=%2Fa%20b", { method: "DELETE" }));
    expect(await screen.findByText("Đã xoá.")).toBeInTheDocument();
  });

  it("shows delete failures", async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") throw apiError(404);
      return listing("/", [file("a")]);
    });
    render(<FilesPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Xoá a" }));
    await userEvent.click(screen.getByRole("button", { name: "Xác nhận xoá" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy");
  });
});
