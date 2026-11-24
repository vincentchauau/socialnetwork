import { apiFetch, loadSession } from "@sn/api";
import CrudRowForm from "@sn/compounds/CrudRowForm";
import type { TableInfo } from "@sn/compounds/CrudView";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn(), loadSession: vi.fn() }));

const api = vi.mocked(apiFetch);
const col = (name: string, type: string, extra: object = {}) => ({ name, type, nullable: true, readonly: false, secret: false, ...extra });
const table: TableInfo = {
  name: "posts",
  label: "Posts",
  pk: ["id"],
  writable: true,
  columns: [col("id", "int", { readonly: true }), col("category", "string"), col("body", "text"), col("owner_id", "int", { ref: { table: "users", label: "username" } })] as TableInfo["columns"],
};

function mount() {
  const onSubmit = vi.fn();
  render(<CrudRowForm api="/api/x/records" table={table} row={null} busy={false} error={null} onSubmit={onSubmit} onCancel={vi.fn()} />);
  return onSubmit;
}

const suggestCalls = () => api.mock.calls.filter(([path]) => String(path).includes("/suggest"));

beforeEach(() => {
  api.mockReset();
  vi.mocked(loadSession).mockResolvedValue(null);
  api.mockResolvedValue({ values: [] });
});

describe("form suggestions", () => {
  it("shows suggestions while typing and a pick fills the field", async () => {
    api.mockResolvedValue({ values: ["Photography", "Pets"] });
    mount();
    const input = screen.getByRole("combobox", { name: /category/i });
    await userEvent.type(input, "P");
    expect(await screen.findByRole("option", { name: "Photography" })).toBeTruthy();
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(String(suggestCalls().at(-1)?.[0])).toBe("/api/x/records/posts/suggest?column=category&q=P");
    fireEvent.mouseDown(screen.getByRole("option", { name: "Photography" }));
    expect((input as HTMLInputElement).value).toBe("Photography");
    expect(screen.queryByRole("option")).toBeNull();
  });

  it("keeps free text and submits it", async () => {
    api.mockResolvedValue({ values: ["Photography"] });
    const onSubmit = mount();
    await userEvent.type(screen.getByRole("combobox", { name: /category/i }), "Pxyz");
    await userEvent.click(screen.getByRole("button", { name: /save|lưu/i }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ category: "Pxyz" }));
  });

  it("gives long text columns no popup", async () => {
    mount();
    await userEvent.type(screen.getByRole("textbox", { name: /body/i }), "abc");
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(suggestCalls().every(([path]) => String(path).includes("column=category") || String(path).includes("column=owner_id"))).toBe(true);
  });

  it("does not offer the value that is already typed", async () => {
    api.mockResolvedValue({ values: ["Pets"] });
    mount();
    await userEvent.type(screen.getByRole("combobox", { name: /category/i }), "Pets");
    await waitFor(() => expect(suggestCalls().length).toBeGreaterThan(0));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("option")).toBeNull();
  });

  it("works with the keyboard: arrows, Enter, Escape", async () => {
    api.mockResolvedValue({ values: ["Photography", "Pets"] });
    mount();
    const input = screen.getByRole("combobox", { name: /category/i }) as HTMLInputElement;
    await userEvent.type(input, "P");
    await screen.findByRole("option", { name: "Pets" });
    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getByRole("option", { name: "Pets" }).getAttribute("aria-selected")).toBe("true");
    expect(input.getAttribute("aria-activedescendant")).toBe(screen.getByRole("option", { name: "Pets" }).id);
    await userEvent.keyboard("{Enter}");
    expect(input.value).toBe("Pets");
    await userEvent.type(input, "{Backspace}");
    await screen.findAllByRole("option");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("option")).toBeNull();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("ignores a stale response", async () => {
    let first: (value: unknown) => void = () => undefined;
    api.mockImplementationOnce(() => new Promise((resolve) => { first = resolve; }));
    api.mockResolvedValue({ values: ["Fresh"] });
    mount();
    const input = screen.getByRole("combobox", { name: /category/i });
    await userEvent.type(input, "a");
    await waitFor(() => expect(suggestCalls().length).toBe(1));
    await userEvent.type(input, "b");
    expect(await screen.findByRole("option", { name: "Fresh" })).toBeTruthy();
    first({ values: ["Stale"] });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("option", { name: "Stale" })).toBeNull();
  });

  it("debounces: one request for fast typing", async () => {
    mount();
    await userEvent.type(screen.getByRole("combobox", { name: /category/i }), "abcd");
    await waitFor(() => expect(suggestCalls().length).toBe(1));
    expect(String(suggestCalls()[0][0])).toContain("q=abcd");
  });

  it("a reference option writes its id and shows its label", async () => {
    api.mockResolvedValue({ values: [], options: [{ value: 7, label: "Pam" }] });
    mount();
    const input = screen.getByRole("combobox", { name: /owner/i }) as HTMLInputElement;
    await userEvent.type(input, "Pa");
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Pam" }));
    expect(input.value).toBe("7");
    expect(screen.getByTestId("ref-label-owner_id").textContent).toBe("Pam");
  });
});
