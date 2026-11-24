import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  Button,
  CheckBox,
  Icon,
  ICON_NAMES,
  LanguageSwitcher,
  LOCALE_STORAGE_KEY,
  LocaleProvider,
  NumberBox,
  Select,
  SplitPanel,
  TextBox,
  TreeView,
  translate,
  useTranslation,
  type Bundle,
} from "@sn/ui";

describe("Select", () => {
  it("is a native select whose options are its children, and reports the chosen value", () => {
    const onChange = vi.fn((event: React.ChangeEvent<HTMLSelectElement>) => event.target.value);
    render(
      <Select aria-label="Size" defaultValue="m" onChange={onChange}>
        <option value="s">Small</option>
        <option value="m">Medium</option>
      </Select>,
    );
    const select = screen.getByRole("combobox", { name: "Size" });
    expect(select).toHaveValue("m");
    fireEvent.change(select, { target: { value: "s" } });
    expect(onChange).toHaveReturnedWith("s");
  });

  it("lets the caller override the style and keeps the other attributes", () => {
    render(<Select aria-label="Pick" disabled style={{ width: 120 }}><option>a</option></Select>);
    const select = screen.getByRole("combobox", { name: "Pick" });
    expect(select).toBeDisabled();
    expect(select).toHaveStyle({ width: "120px" });
  });
});

describe("Button", () => {
  it("hands its ref to the <button>, so callers can manage focus", () => {
    const ref = { current: null as HTMLButtonElement | null };
    render(<Button ref={ref}>Go</Button>);
    expect(ref.current).toBe(screen.getByRole("button", { name: "Go" }));
  });

  it("shows the loading label and disables itself while loading", () => {
    const onClick = vi.fn();
    render(<Button loading loadingLabel="Saving…" onClick={onClick}>Save</Button>);
    const button = screen.getByRole("button", { name: "Saving…" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("fills come from --solid-1 onward and ghost stays transparent", () => {
    render(
      <>
        <Button>Save</Button>
        <Button variant="secondary">Back</Button>
        <Button variant="danger">Delete</Button>
        <Button variant="ghost">Skip</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Delete" })).toHaveStyle({ background: "var(--solid-3)" });
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("data-variant", "primary");
    expect(screen.getByRole("button", { name: "Back" })).toHaveStyle({ background: "var(--solid-2)" });
    expect(screen.getByRole("button", { name: "Skip" })).toHaveStyle({ background: "transparent" });
  });

  it("exposes its variant, effect and status for lib/button.css", () => {
    render(
      <Button variant="secondary" effect="sweep" status="error">
        Go
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Go" });
    expect(button).toHaveAttribute("data-variant", "secondary");
    expect(button).toHaveAttribute("data-effect", "sweep");
    expect(button).toHaveAttribute("data-status", "error");
  });

  it("adds a ripple at the click for the ripple effect and removes it afterwards", () => {
    vi.useFakeTimers();
    const onClick = vi.fn();
    render(<Button effect="ripple" onClick={onClick}>Tap</Button>);
    const button = screen.getByRole("button", { name: "Tap" });
    fireEvent.click(button);
    expect(button.querySelector(".sn-ripple")).not.toBeNull();
    expect(onClick).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(700);
    });
    expect(button.querySelector(".sn-ripple")).toBeNull();
    vi.useRealTimers();
  });

  it("adds no ripple for the other effects", () => {
    render(<Button effect="lift">Up</Button>);
    const button = screen.getByRole("button", { name: "Up" });
    fireEvent.click(button);
    expect(button.querySelector(".sn-ripple")).toBeNull();
  });

  it("replaces a submit button: type submit, swaps its label and disables while the form is being sent", () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    const { rerender } = render(
      <form onSubmit={onSubmit}>
        <Button type="submit" loading={false} loadingLabel="Sending…">Send</Button>
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    rerender(
      <form onSubmit={onSubmit}>
        <Button type="submit" loading loadingLabel="Sending…">Send</Button>
      </form>,
    );
    expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Sending…" })).toHaveAttribute("type", "submit");
  });

  it("passes click events through when enabled", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("TextBox", () => {
  it("renders an input by default and a textarea with multiline", () => {
    render(
      <>
        <TextBox aria-label="one" />
        <TextBox aria-label="many" multiline rows={5} />
      </>,
    );
    expect(screen.getByLabelText("one").tagName).toBe("INPUT");
    const area = screen.getByLabelText("many");
    expect(area.tagName).toBe("TEXTAREA");
    expect(area).toHaveAttribute("rows", "5");
  });

  it("does not leak the multiline prop to the DOM", () => {
    render(<TextBox aria-label="many" multiline />);
    expect(screen.getByLabelText("many")).not.toHaveAttribute("multiline");
  });
});

describe("NumberBox", () => {
  it("reports typed values as numbers", () => {
    const onChange = vi.fn();
    render(<NumberBox value={2} onChange={onChange} aria-label="n" />);
    fireEvent.change(screen.getByLabelText("n"), { target: { value: "7" } });
    expect(onChange).toHaveBeenCalledWith(7);
  });

  it("the arrows step and stay inside min and max", () => {
    const onChange = vi.fn();
    render(<NumberBox value={5} min={1} max={5} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Increase" }));
    expect(onChange).toHaveBeenLastCalledWith(5);
    fireEvent.click(screen.getByRole("button", { name: "Decrease" }));
    expect(onChange).toHaveBeenLastCalledWith(4);
  });

  it("hides the arrows with controls={false}", () => {
    render(<NumberBox value={1} controls={false} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("CheckBox", () => {
  it("reports the new checked state and shows a label", () => {
    const onChange = vi.fn();
    render(<CheckBox checked={false} onChange={onChange} label="Agree" />);
    fireEvent.click(screen.getByLabelText("Agree"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("sets the indeterminate property", () => {
    render(<CheckBox checked={false} indeterminate label="Some" onChange={() => {}} />);
    expect((screen.getByLabelText("Some") as HTMLInputElement).indeterminate).toBe(true);
  });
});

describe("SplitPanel", () => {
  const panes = (shown: boolean[] = [true, true, false]) => ["a", "b", "c"].map((key, i) => ({ key, label: key.toUpperCase(), node: <p>{key}</p>, minSize: 50, defaultVisible: shown[i] }));

  it("has one button per pane, and a divider between each two that are shown", () => {
    render(<SplitPanel panes={panes()} />);
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual(["A", "B", "C"]);
    expect(screen.getAllByRole("separator")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "C" }));
    expect(screen.getAllByRole("separator")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "C" })).toHaveAttribute("aria-pressed", "true");
  });

  it("does not render a pane that is off, unless it is kept mounted", () => {
    const { rerender } = render(<SplitPanel panes={panes()} />);
    expect(screen.queryByText("c")).not.toBeInTheDocument();
    rerender(<SplitPanel panes={panes().map((pane) => ({ ...pane, keepMounted: true }))} />);
    expect(screen.getByText("c")).not.toBeVisible();
  });

  it("tells the owner what is shown when the state is kept by it", () => {
    const onVisibleChange = vi.fn();
    render(<SplitPanel panes={panes()} visible={{ a: true, b: true, c: false }} onVisibleChange={onVisibleChange} />);
    fireEvent.click(screen.getByRole("button", { name: "A" }));
    expect(onVisibleChange).toHaveBeenCalledWith({ a: false, b: true, c: false });
    expect(screen.getAllByRole("separator")).toHaveLength(1); // still as the owner says
  });

  it("has no buttons when no pane has a label", () => {
    render(<SplitPanel panes={panes().map((pane) => ({ ...pane, label: undefined }))} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("moves a divider with the arrow keys, never below the least size", () => {
    const { container } = render(<SplitPanel panes={panes([true, true, false])} />);
    const grid = container.querySelector("[style*='grid-template-columns']") as HTMLElement;
    grid.getBoundingClientRect = () => ({ width: 508, height: 100, left: 0, top: 0, right: 508, bottom: 100, x: 0, y: 0, toJSON: () => ({}) });
    const before = grid.style.gridTemplateColumns;
    fireEvent.keyDown(screen.getByRole("separator"), { key: "ArrowRight" });
    expect(grid.style.gridTemplateColumns).not.toBe(before);
    for (let i = 0; i < 40; i += 1) fireEvent.keyDown(screen.getByRole("separator"), { key: "ArrowRight" });
    const second = Number(/minmax\(50px, ([\d.]+)fr\)$/.exec(grid.style.gridTemplateColumns)?.[1]);
    expect(second).toBeGreaterThan(0);
  });

  it("uses a vertical layout when asked", () => {
    render(<SplitPanel orientation="vertical" panes={panes()} />);
    expect(screen.getByRole("separator")).toHaveAttribute("aria-orientation", "horizontal");
  });

  it("remembers what is shown under its storage key", () => {
    const { unmount } = render(<SplitPanel panes={panes()} storageKey="split-test" />);
    fireEvent.click(screen.getByRole("button", { name: "B" }));
    unmount();
    render(<SplitPanel panes={panes()} storageKey="split-test" />);
    expect(screen.getByRole("button", { name: "B" })).toHaveAttribute("aria-pressed", "false");
    window.localStorage.removeItem("split-test");
  });
});

describe("TreeView", () => {
  const data = [{ key: "root", label: "Root", children: [{ key: "leaf", label: "Leaf" }] }];

  it("expands and collapses children and selects nodes", () => {
    const onSelect = vi.fn();
    render(<TreeView data={data} onSelect={onSelect} />);
    expect(screen.queryByText("Leaf")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Toggle Root" }));
    expect(screen.getByRole("button", { name: "Toggle Root" })).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByText("Leaf"));
    expect(onSelect).toHaveBeenCalledWith("leaf");
    fireEvent.click(screen.getByRole("button", { name: "Toggle Root" }));
    expect(screen.queryByText("Leaf")).not.toBeInTheDocument();
  });

  it("shows no toggle for a node without children", () => {
    render(<TreeView data={[{ key: "x", label: "Solo" }]} />);
    expect(screen.queryByRole("button", { name: /Toggle/ })).not.toBeInTheDocument();
  });
});

describe("Icon", () => {
  it.each(ICON_NAMES)("draws %s", (name) => {
    const { container } = render(<Icon name={name} size={20} />);
    expect(container.querySelector("svg")).toHaveAttribute("width", "20");
  });

  it("renders nothing for an unknown name", () => {
    const { container } = render(<Icon name="nope" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("i18n", () => {
  const bundles: Record<string, Bundle> = {
    vi: { common: { save: "Lưu" }, only: "chỉ vi" },
    en: { common: { save: "Save" } },
  };

  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("lang");
    document.documentElement.removeAttribute("dir");
  });

  it("translate returns the path for missing keys and for non-leaf nodes", () => {
    expect(translate(bundles.vi, "common.save")).toBe("Lưu");
    expect(translate(bundles.vi, "common.missing")).toBe("common.missing");
    expect(translate(bundles.vi, "common")).toBe("common");
    expect(translate(bundles.vi, "only.deeper")).toBe("only.deeper");
    expect(translate(undefined, "a.b")).toBe("a.b");
  });

  function Probe() {
    const { t, locale } = useTranslation(bundles);
    return <p>{`${locale}:${t("common.save")}`}</p>;
  }

  it("useTranslation follows the locale chosen in the switcher and stores it", () => {
    render(
      <LocaleProvider defaultLocale="vi">
        <Probe />
        <LanguageSwitcher locales={["vi", "en"]} />
      </LocaleProvider>,
    );
    expect(screen.getByText("vi:Lưu")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Select language"), { target: { value: "en" } });
    expect(screen.getByText("en:Save")).toBeInTheDocument();
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("restores the stored locale and follows other tabs", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    render(<LocaleProvider defaultLocale="vi"><Probe /></LocaleProvider>);
    expect(screen.getByText("en:Save")).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: LOCALE_STORAGE_KEY, newValue: "vi" }));
    });
    expect(screen.getByText("vi:Lưu")).toBeInTheDocument();
  });

  it("an unknown locale falls back to the first bundle, and right-to-left locales set dir", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "xx");
    render(
      <LocaleProvider>
        <Probe />
        <LanguageSwitcher locales={["vi", "ar"]} />
      </LocaleProvider>,
    );
    expect(screen.getByText("xx:Lưu")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Select language"), { target: { value: "ar" } });
    expect(document.documentElement.dir).toBe("rtl");
  });
});
