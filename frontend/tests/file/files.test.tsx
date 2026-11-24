import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as sn from "@sn/api";
import { httpErrorText as errorText } from "@sn/api";
import { breadcrumbs, downloadUrl, formatBytes, joinPath, nameProblem, uploadUrl } from "../../app/file/lib/paths";

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
    expect(breadcrumbs("/")).toEqual([{ label: "data", path: "/" }]);
    expect(breadcrumbs("/a/b").map((c) => c.path)).toEqual(["/", "/a", "/a/b"]);
    expect(joinPath("/", "x")).toBe("/x");
    expect(joinPath("/a", "x")).toBe("/a/x");
  });

  it("validates names", () => {
    expect(nameProblem("ok")).toBeNull();
    for (const bad of ["", "  ", "../chat/work", "../chat", "a/b", "a\\b", "x".repeat(101)]) expect(nameProblem(bad)).not.toBeNull();
  });

  it("encodes user text in urls", () => {
    expect(downloadUrl("/a b/ü&x=1#.txt")).toBe(`/api/file/download?path=${encodeURIComponent("/a b/ü&x=1#.txt")}`);
    expect(uploadUrl("/a&b")).toContain("%26");
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
