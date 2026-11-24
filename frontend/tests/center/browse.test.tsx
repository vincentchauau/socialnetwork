import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FacetGridView } from "@sn/compounds/SplitPanel";
import FileDropZone from "@sn/compounds/FileTools";
import FacetView from "@sn/compounds/FacetView";
import { usePagedList } from "@sn/lib/hooks";

describe("FacetView", () => {
  const facets = [{ name: "home", count: 2 }, { name: "toys", count: 1 }];

  it("lists every facet with its count, and All with the total", () => {
    render(<FacetView label="Categories" allLabel="All" facets={facets} value="" onChange={() => undefined} />);
    expect(screen.getByRole("button", { name: /All \(3\)/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /home \(2\)/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /toys \(1\)/ })).toBeInTheDocument();
  });

  it('tells the chosen facet, and an empty text for All', async () => {
    const onChange = vi.fn();
    render(<FacetView label="Categories" allLabel="All" facets={facets} value="home" onChange={onChange} />);
    expect(screen.getByRole("button", { name: /home \(2\)/ })).toHaveAttribute("aria-current", "true");
    await userEvent.click(screen.getByRole("button", { name: /toys/ }));
    expect(onChange).toHaveBeenLastCalledWith("toys");
    await userEvent.click(screen.getByRole("button", { name: /All/ }));
    expect(onChange).toHaveBeenLastCalledWith("");
  });
});

describe("FacetGridView", () => {
  it("shows the filters and the results, each with a button that hides it", async () => {
    render(<FacetGridView name="test" filtersLabel="Filters" resultsLabel="Results" filters={<p>the tree</p>}><p>the list</p></FacetGridView>);
    expect(screen.getByText("the tree")).toBeInTheDocument();
    expect(screen.getByText("the list")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.queryByText("the tree")).toBeNull();
    expect(screen.getByText("the list")).toBeInTheDocument();
  });
});


describe("usePagedList", () => {
  const pages = (cursor: number | null) => Promise.resolve({ items: cursor === null ? [1, 2] : [3], next_cursor: cursor === null ? 2 : null });

  it("reads the first page, then one more on loadMore, and says when there is no more", async () => {
    const { result } = renderHook(() => usePagedList<number, number>(pages, [], String));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toEqual([1, 2]);
    expect(result.current.hasMore).toBe(true);
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toEqual([1, 2, 3]));
    expect(result.current.hasMore).toBe(false);
  });

  it("starts again when the filters change, and drops a reply that comes too late", async () => {
    let release: (value: { items: string[]; next_cursor: null }) => void = () => undefined;
    const load = vi.fn((_cursor: number | null) => new Promise<{ items: string[]; next_cursor: null }>((resolve) => (release = resolve)));
    const { result, rerender } = renderHook(({ q }) => usePagedList<string, number>(() => load(null), [q], String), { initialProps: { q: "a" } });
    const first = release;
    rerender({ q: "b" });
    await act(async () => first({ items: ["late"], next_cursor: null }));
    expect(result.current.items).toEqual([]);
    await act(async () => release({ items: ["fresh"], next_cursor: null }));
    await waitFor(() => expect(result.current.items).toEqual(["fresh"]));
  });

  it("says why a page could not be read", async () => {
    const { result } = renderHook(() => usePagedList<number, number>(() => Promise.reject(new Error("down")), [], (failure) => `failed: ${(failure as Error).message}`));
    await waitFor(() => expect(result.current.error).toBe("failed: down"));
    expect(result.current.items).toEqual([]);
    fireEvent.click(document.body);
  });
});

describe("FileDropZone", () => {
  const file = (name: string) => new File(["x"], name, { type: "text/plain" });

  it("takes a chosen file, and only the first one unless it takes several", async () => {
    const one = vi.fn();
    const { rerender } = render(<FileDropZone inputLabel="File" onFiles={one} prompt="Drop here" />);
    await userEvent.upload(screen.getByLabelText("File"), [file("a.txt"), file("b.txt")]);
    expect(one).toHaveBeenCalledWith([expect.objectContaining({ name: "a.txt" })]);
    const many = vi.fn();
    rerender(<FileDropZone inputLabel="File" multiple onFiles={many} prompt="Drop here" />);
    await userEvent.upload(screen.getByLabelText("File"), [file("a.txt"), file("b.txt")]);
    expect(many.mock.calls[0][0]).toHaveLength(2);
  });

  it("takes dropped files in the box and in the bar, and nothing while busy", () => {
    const onFiles = vi.fn();
    const { rerender } = render(<FileDropZone testId="zone" onFiles={onFiles} prompt="Drop here" />);
    fireEvent.drop(screen.getByTestId("zone"), { dataTransfer: { files: [file("a.txt")] } });
    expect(onFiles).toHaveBeenCalledTimes(1);
    rerender(<FileDropZone testId="zone" variant="bar" multiple onFiles={onFiles} buttonLabel="Upload">or drop</FileDropZone>);
    fireEvent.drop(screen.getByTestId("zone"), { dataTransfer: { files: [file("a.txt"), file("b.txt")] } });
    expect(onFiles).toHaveBeenCalledTimes(2);
    rerender(<FileDropZone testId="zone" variant="bar" busy onFiles={onFiles} buttonLabel="Upload">or drop</FileDropZone>);
    fireEvent.drop(screen.getByTestId("zone"), { dataTransfer: { files: [file("a.txt")] } });
    expect(onFiles).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  });

  it("is only a button in the button variant, and the button opens the picker", async () => {
    render(<FileDropZone variant="button" inputLabel="CSV" buttonLabel="Import" accept=".csv" onFiles={() => undefined} />);
    const input = screen.getByLabelText("CSV") as HTMLInputElement;
    const click = vi.spyOn(input, "click");
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(click).toHaveBeenCalled();
    expect(input).toHaveAttribute("accept", ".csv");
  });
});

describe("FileDropZone accept", () => {
  it("lets through only the extensions and types it was told, also for a drop, and says what it refused", () => {
    const onFiles = vi.fn();
    const onRejected = vi.fn();
    render(<FileDropZone testId="zone" accept=".csv,.PDF,image/*" multiple onFiles={onFiles} onRejected={onRejected} prompt="Drop" />);
    const drop = (...files: File[]) => fireEvent.drop(screen.getByTestId("zone"), { dataTransfer: { files } });
    drop(new File(["x"], "a.csv"), new File(["x"], "b.pdf"), new File(["x"], "c.png", { type: "image/png" }), new File(["x"], "d.exe"));
    expect(onFiles.mock.calls[0][0].map((f: File) => f.name)).toEqual(["a.csv", "b.pdf", "c.png"]);
    expect(onRejected.mock.calls[0][0].map((f: File) => f.name)).toEqual(["d.exe"]);
    drop(new File(["x"], "e.exe"));
    expect(onFiles).toHaveBeenCalledTimes(1);
  });
});


