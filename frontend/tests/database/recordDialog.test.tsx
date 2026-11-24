import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as sn from "@sn/api";
import RecordDialog from "../../app/database/components/record/RecordDialog";

vi.mock("@sn/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@sn/api")>();
  return { ...real, apiFetch: vi.fn(), apiForm: vi.fn() };
});

const fetchMock = vi.mocked(sn.apiFetch);
const formMock = vi.mocked(sn.apiForm);

const API = "/api/market/records";
const table = {
  name: "showcases",
  label: "showcases",
  pk: ["id"],
  writable: true,
  columns: [
    { name: "id", type: "int", nullable: false, readonly: true, secret: false },
    { name: "title", type: "text", nullable: true, readonly: false, secret: false },
    { name: "brand_id", type: "int", nullable: true, readonly: false, secret: false, ref: { table: "brands", label: "name", key: "id" } },
    { name: "cover", type: "text", nullable: true, readonly: false, secret: false, media: { kind: "image" } },
  ],
} as never;
const row = { id: 3, title: "Chair", brand_id: 1, cover: null };

/** The files of a cell are listed as none; the save and the delete answer ok. */
function answer() {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/batch-update")) return { results: [{ ok: true }] };
    if (init?.method === "DELETE") return undefined;
    if (url.includes("/files/")) return { files: [] };
    throw new Error(`unrouted ${url}`);
  });
}

function open(overrides: Partial<{ onDone: () => void; onClose: () => void; onPickRef: (column: { name: string }, pending: unknown) => void }> = {}) {
  const onDone = overrides.onDone ?? vi.fn();
  const onClose = overrides.onClose ?? vi.fn();
  render(<RecordDialog api={API} table={table} row={row as never} onDone={onDone} onClose={onClose} onPickRef={overrides.onPickRef as never} />);
  return { onDone, onClose };
}

beforeEach(() => {
  fetchMock.mockReset();
  formMock.mockReset();
  answer();
});

describe("the record dialog", () => {
  it("shows the fields of the row, with the reference as a clickable value", () => {
    open();
    expect(screen.getByRole("dialog", { name: /showcases: row 3/ })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "title" })).toHaveValue("Chair");
    expect(screen.getByRole("button", { name: "Pick brand_id" })).toHaveTextContent("1");
  });

  it("saves only the changed values", async () => {
    const user = userEvent.setup();
    const { onDone } = open();
    const title = screen.getByRole("textbox", { name: "title" });
    await user.clear(title);
    await user.type(title, "Desk");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const save = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/batch-update"));
    expect(save).toBeDefined();
    expect(String(save?.[1]?.body)).toContain("Desk");
    expect(String(save?.[1]?.body)).not.toContain("brand_id");
  });

  it("shows the reason when the values are not saved, and keeps the dialog open", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith("/batch-update")) return { results: [{ ok: false, error: "title is too long" }] };
      return { files: [] };
    });
    const { onDone } = open();
    await user.type(screen.getByRole("textbox", { name: "title" }), "!");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The values were not saved: title is too long");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("hands a reference click to the Table tab with the unsaved edits", async () => {
    const user = userEvent.setup();
    const onPickRef = vi.fn();
    open({ onPickRef });
    await user.type(screen.getByRole("textbox", { name: "title" }), "!");
    await user.click(screen.getByRole("button", { name: "Pick brand_id" }));
    expect(onPickRef).toHaveBeenCalledTimes(1);
    const [column, pending] = onPickRef.mock.calls[0];
    expect(column.name).toBe("brand_id");
    expect(pending.values).toEqual({ title: "Chair!" });
  });

  it("deletes the row after confirmation", async () => {
    const user = userEvent.setup();
    const { onDone } = open();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getAllByRole("button", { name: "Delete" }).slice(-1)[0]); // the confirmation asks again
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(fetchMock.mock.calls.some(([url, init]) => String(url) === `${API}/showcases/3` && init?.method === "DELETE")).toBe(true);
  });

  it("closes with Escape", () => {
    const { onClose } = open();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
