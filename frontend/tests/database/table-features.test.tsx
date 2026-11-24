import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ColumnInfo, TableInfo } from "@sn/compounds/crudModel";
import { apiFetch, apiForm } from "@sn/api";

import TableEditor from "../../app/database/components/table/TableEditor";
import { filesFor, folderPlan, kindOfFile, titleColumn } from "@sn/compounds/recordModel";
import { filesOfCell } from "../../app/database/components/table/tableImport";

vi.mock("@sn/api", () => ({ apiFetch: vi.fn(), apiForm: vi.fn() }));
const api = vi.mocked(apiFetch);
const form = vi.mocked(apiForm);

const picture: ColumnInfo = { name: "image", type: "string", nullable: true, readonly: false, secret: false, media: { kind: "image", preview: "files/image" } };
const table: TableInfo = {
  name: "market_products", label: "Products", pk: ["id"], writable: true,
  columns: [
    { name: "id", type: "integer", nullable: false, readonly: true, secret: false },
    { name: "name", type: "string", nullable: false, readonly: false, secret: false },
    picture,
  ],
} as unknown as TableInfo;

const file = (name: string) => new File(["x"], name, { type: "image/png" });

beforeEach(() => {
  api.mockReset();
  form.mockReset();
  api.mockResolvedValue({ rows: [{ id: 3, name: "Lamp", image: null }], total: 1 });
});

describe("folder and file rules", () => {
  it("makes one row per sub-folder, named after it, and one row for a folder with no sub-folder", () => {
    const nested = folderPlan([
      { path: "catalog/lamp/a.png", file: file("a.png") },
      { path: "catalog/lamp/b.png", file: file("b.png") },
      { path: "catalog/chair/c.png", file: file("c.png") },
    ]);
    expect(nested.rows.map((row) => [row.title, row.files.length])).toEqual([["lamp", 2], ["chair", 1]]);
    const flat = folderPlan([{ path: "lamp/a.png", file: file("a.png") }]);
    expect(flat.rows.map((row) => row.title)).toEqual(["lamp"]);
  });

  it("keeps only the files of the kind a column holds", () => {
    const { keep, skipped } = filesFor(picture, [file("a.png"), new File(["x"], "b.mp3")]);
    expect(keep.map((f) => f.name)).toEqual(["a.png"]);
    expect(skipped.map((f) => f.name)).toEqual(["b.mp3"]);
    expect(kindOfFile("clip.MP4")).toBe("video");
  });

  it("finds the files of one cell of one row by the data/{database}/{table}/{column}/{row_id} layout", () => {
    const named = (path: string) => Object.defineProperty(new File(["x"], path.split("/").pop() ?? "x"), "webkitRelativePath", { value: path });
    const all = [
      named("data/market/showcases/cover/3/a.png"),
      named("data/market/showcases/cover/3/b.png"),
      named("data/market/showcases/cover/4/c.png"),
      named("data/market/showcases/audio/3/d.wav"),
    ];
    expect(filesOfCell(all, "market", "showcases", "cover", "3").map((f) => f.name)).toEqual(["a.png", "b.png"]);
    expect(filesOfCell(all, "market", "showcases", "audio", "3").map((f) => f.name)).toEqual(["d.wav"]);
  });

  it("puts a folder name into the first text column, not a picture", () => {
    expect(titleColumn(table)?.name).toBe("name");
  });
});

