import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { APPS } from "@sn/lib/apps";
import { NAV_NODES, isActivePath } from "@sn/lib/nav";
import { TreeView, type TreeNode } from "@sn/ui";

describe("isActivePath with a hash", () => {
  it("tells two views of one page apart", () => {
    expect(isActivePath("/work#file", "/work#file")).toBe(true);
    expect(isActivePath("/work#database", "/work#file")).toBe(false);
    expect(isActivePath("/work#file", "/work#database")).toBe(false);
  });

  it("a link without a hash matches the page whatever its hash", () => {
    expect(isActivePath("/work", "/work#database")).toBe(true);
    expect(isActivePath("/work", "/work")).toBe(true);
  });

  it("a link with a hash needs that hash to be current, and the path to match", () => {
    expect(isActivePath("/work#file", "/work")).toBe(false);
    expect(isActivePath("/work#file", "/chat#file")).toBe(false);
    expect(isActivePath("/work#file", undefined)).toBe(false);
  });

  it("ignores a trailing slash before the hash", () => {
    expect(isActivePath("/work#file", "/work/#file")).toBe(true);
  });
});
describe("isActivePath", () => {
  it("matches the home link only on the home page", () => {
    expect(isActivePath("/", "/")).toBe(true);
    expect(isActivePath("/", "/chat")).toBe(false);
  });

  it("matches an app link on its own page and on the pages below it, not on look-alike paths", () => {
    expect(isActivePath("/chat", "/chat")).toBe(true);
    expect(isActivePath("/chat", "/chat/")).toBe(true);
    expect(isActivePath("/chat", "/chat/room/1")).toBe(true);
    expect(isActivePath("/chat", "/chatter")).toBe(false);
    expect(isActivePath("/chat", "/work")).toBe(false);
  });

  it("matches nothing before the path is known", () => {
    expect(isActivePath("/", undefined)).toBe(false);
  });
});

describe("NAV_NODES", () => {
  const flat = (nodes: readonly TreeNode[]): TreeNode[] => nodes.flatMap((node) => [node, ...flat(node.children ?? [])]);

  it("is a flat list of the apps, in the order of the menu", () => {
    expect(NAV_NODES.every((node) => node.children === undefined)).toBe(true);
    expect(NAV_NODES.map((node) => node.href)).toEqual(["/center", "/chat", "/werewolf", "/face", "/roulette", "/market", "/job", "/file", "/"]);
    expect(NAV_NODES.map((node) => node.label)).not.toContain("ChatWork");
  });

  it("marks a link on its own page and the pages below it", () => {
    expect(isActivePath("/file", "/file/deeper")).toBe(true);
    expect(isActivePath("/file", "/")).toBe(false);
  });

  it("still reaches every app of the gateway", () => {
    const hrefs = flat(NAV_NODES).map((node) => node.href ?? "");
    for (const app of APPS.filter((app) => app.href !== "/chat")) expect(hrefs.some((href) => href === app.href || href.startsWith(`${app.href}#`))).toBe(true); // (the chat page itself is reached from People and the notices)
  });

  it("has unique keys and an icon on every entry", () => {
    const nodes = flat(NAV_NODES);
    expect(new Set(nodes.map((node) => node.key)).size).toBe(nodes.length);
    for (const node of nodes) expect(node.icon).toBeTruthy();
  });
});

const MENU: TreeNode[] = [
  { key: "home", label: "Home", href: "/", icon: "home" },
  {
    key: "apps",
    label: "Apps",
    icon: "apps",
    children: [
      { key: "chat", label: "Chat", href: "/chat", icon: "chat" },
      { key: "work", label: "Work", href: "/work" },
    ],
  },
  { key: "help", label: "Help" },
];

afterEach(() => window.history.pushState(null, "", "/"));

describe("TreeView links and buttons", () => {
  it("a node with an href is a link and the current page is marked", () => {
    // "Apps" holds the current page, so it is already open.
    render(<TreeView data={MENU} activeHref="/chat" />);
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Work" })).not.toHaveAttribute("aria-current");
  });

  it("a node without an href is a button that reports its key", () => {
    const onSelect = vi.fn();
    render(<TreeView data={MENU} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "Help" }));
    expect(onSelect).toHaveBeenCalledWith("help");
  });

  it("without activeHref it reads the browser path, which includes an app's basePath", () => {
    window.history.pushState(null, "", "/work/files");
    render(<TreeView data={MENU} orientation="horizontal" />);
    fireEvent.click(screen.getByRole("button", { name: /Apps/ }));
    expect(screen.getByRole("link", { name: "Work" })).toHaveAttribute("aria-current", "page");
  });

  it("activeHref wins over the browser path", () => {
    window.history.pushState(null, "", "/work");
    render(<TreeView data={MENU} activeHref="/" />);
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
  });

  it("wraps the tree in a <nav> only when it is given a name", () => {
    const { rerender } = render(<TreeView data={MENU} />);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    rerender(<TreeView data={MENU} aria-label="Main" />);
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });
});

describe("TreeView vertical", () => {
  it("is the default and shows icons next to the labels", () => {
    const { container } = render(<TreeView data={MENU} />);
    expect(screen.getByRole("link", { name: "Home" }).querySelector("svg")).not.toBeNull();
    expect(container.querySelector("nav")).toBeNull();
  });

  it("opens the parent of the current page by itself, and leaves the others closed", () => {
    render(<TreeView data={MENU} activeHref="/work" />);
    expect(screen.getByRole("button", { name: "Toggle Apps" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Work" })).toBeInTheDocument();
  });

  it("stays closed when the current page is elsewhere, and a manual toggle wins over the automatic one", () => {
    render(<TreeView data={MENU} activeHref="/" />);
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Toggle Apps" }));
    expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Toggle Apps" }));
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
  });

  it("can close a parent that opened itself because it holds the current page", () => {
    render(<TreeView data={MENU} activeHref="/chat" />);
    fireEvent.click(screen.getByRole("button", { name: "Toggle Apps" }));
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
  });

  it("the toggle label can be translated", () => {
    render(<TreeView data={MENU} toggleLabel="Mở" />);
    expect(screen.getByRole("button", { name: "Mở Apps" })).toBeInTheDocument();
  });
});

describe("TreeView horizontal", () => {
  function bar(extra: Partial<React.ComponentProps<typeof TreeView>> = {}) {
    return render(
      <TreeView
        data={MENU}
        orientation="horizontal"
        aria-label="Main"
        brand={<strong>Brand</strong>}
        trailing={<em>Tail</em>}
        {...extra}
      />,
    );
  }

  it("puts the brand first, the entries in a row, and the trailing slot last", () => {
    bar();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toHaveStyle({ display: "flex" });
    const parts = Array.from(nav.children).filter((child) => child.tagName !== "STYLE").map((child) => child.tagName);
    // brand, the menu button for narrow windows, the entries, the trailing slot (wrapped, to push it right)
    expect(parts).toEqual(["STRONG", "BUTTON", "UL", "DIV"]);
    expect(nav.lastElementChild).toHaveTextContent("Tail");
    expect(within(nav).getAllByRole("listitem")).toHaveLength(MENU.length);
  });

  it("shows no icons in the bar", () => {
    bar();
    expect(screen.getByRole("link", { name: "Home" }).querySelector("svg")).toBeNull();
  });

  it("a parent opens a drop-down with its children and closes it again", () => {
    bar();
    const parent = screen.getByRole("button", { name: /Apps/ });
    expect(parent).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
    fireEvent.click(parent);
    expect(parent).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
    fireEvent.click(parent);
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
  });

  it("closes on Escape, on a press outside, and after a link inside it is followed", () => {
    bar();
    const open = () => fireEvent.click(screen.getByRole("button", { name: /Apps/ }));
    open();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
    open();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
    open();
    fireEvent.mouseDown(screen.getByRole("link", { name: "Chat" }));
    expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Chat" }));
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
  });

  it("only one drop-down is open at a time", () => {
    const menu: TreeNode[] = [
      { key: "a", label: "A", children: [{ key: "a1", label: "A one", href: "/a1" }] },
      { key: "b", label: "B", children: [{ key: "b1", label: "B one", href: "/b1" }] },
    ];
    render(<TreeView data={menu} orientation="horizontal" />);
    fireEvent.click(screen.getByRole("button", { name: /^A/ }));
    expect(screen.getByRole("link", { name: "A one" })).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("button", { name: /^B/ }));
    fireEvent.click(screen.getByRole("button", { name: /^B/ }));
    expect(screen.queryByRole("link", { name: "A one" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "B one" })).toBeInTheDocument();
  });

  it("a parent holding the current page is highlighted", () => {
    bar({ activeHref: "/work" });
    expect(screen.getByRole("button", { name: /Apps/ })).toHaveAttribute("data-active", "true");
    expect(screen.getByRole("link", { name: "Home" })).not.toHaveAttribute("aria-current");
  });

  it("a button entry inside a drop-down reports its key and closes the drop-down", () => {
    const onSelect = vi.fn();
    const menu: TreeNode[] = [{ key: "tools", label: "Tools", children: [{ key: "reset", label: "Reset" }] }];
    render(<TreeView data={menu} orientation="horizontal" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /Tools/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(onSelect).toHaveBeenCalledWith("reset");
    expect(screen.queryByRole("button", { name: "Reset" })).not.toBeInTheDocument();
  });

  it("without a trailing slot there is no empty wrapper", () => {
    render(<TreeView data={MENU} orientation="horizontal" aria-label="Main" />);
    expect(screen.getByRole("navigation").querySelector(".sn-tree-trailing")).toBeNull();
  });

  it("renders the real navigation of the apps", () => {
    render(<TreeView data={NAV_NODES} orientation="horizontal" aria-label="Main" activeHref="/file" />);
    expect(screen.queryByRole("link", { name: "Trang chủ" })).not.toBeInTheDocument(); // the brand is the way home
    expect(screen.getByRole("link", { name: "Face" })).toHaveAttribute("href", "/face");
    expect(screen.getByRole("link", { name: "File" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Database" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Database" })).not.toHaveAttribute("aria-current");
    expect(screen.queryByRole("link", { name: "Work" })).not.toBeInTheDocument();
  });
});

describe("TreeView on a narrow window", () => {
  // jsdom applies the bar's own CSS but not its media queries, so the menu button is display:none here and has no
  // accessible name for role queries; its aria-label is still there.
  const menuButton = () => screen.getByLabelText("Menu");
  const list = (container: HTMLElement) => container.querySelector("ul.sn-tree-list") as HTMLElement;

  function bar(extra: Partial<React.ComponentProps<typeof TreeView>> = {}) {
    return render(<TreeView data={MENU} orientation="horizontal" aria-label="Main" {...extra} />);
  }

  it("has a menu button that shows and hides the list, and says which list it controls", () => {
    const { container } = bar();
    const button = menuButton();
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", list(container).id);
    expect(list(container)).not.toHaveAttribute("data-open");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(list(container)).toHaveAttribute("data-open");
    fireEvent.click(button);
    expect(list(container)).not.toHaveAttribute("data-open");
  });

  it("closes the menu on Escape and after an entry is picked, but not when a parent is opened", () => {
    const { container } = bar();
    fireEvent.click(menuButton());
    fireEvent.keyDown(document, { key: "Escape" });
    expect(list(container)).not.toHaveAttribute("data-open");

    fireEvent.click(menuButton());
    fireEvent.click(screen.getByRole("button", { name: /Apps/ }));
    expect(list(container)).toHaveAttribute("data-open");
    expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Chat" }));
    expect(list(container)).not.toHaveAttribute("data-open");
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("the CSS turns the bar vertical below the breakpoint and keeps it a row above", () => {
    const { container } = bar();
    const css = container.querySelector("style")?.textContent ?? "";
    expect(css).toContain("@media (max-width: 639px)");
    expect(css).toMatch(/\.sn-tree-list \{ display: none; flex-direction: column;/);
    expect(css).toMatch(/\.sn-tree-dropdown \{ position: static;/);
    expect(css).toMatch(/\.sn-tree-menu \{ display: none; \}/);
  });

  it("shields its buttons from an app's own global button styles (ChatWork stretches buttons and draws an overlay)", () => {
    const { container } = bar();
    const css = container.querySelector("style")?.textContent ?? "";
    expect(css).toContain(".sn-tree-menu, .sn-tree-toggle { flex: none; }");
    expect(css).toContain(".sn-tree-entry::after, .sn-tree-toggle::after, .sn-tree-menu::after { content: none; }");
  });

  it("the trailing part goes into the menu: shown only while the menu is open", () => {
    const { container } = bar({ trailing: <em>Tail</em> });
    const tail = container.querySelector(".sn-tree-trailing");
    expect(tail).not.toHaveAttribute("data-open");
    fireEvent.click(screen.getByLabelText("Menu"));
    expect(tail).toHaveAttribute("data-open");
    expect(container.querySelector("style")?.textContent).toContain(".sn-tree-collapsible .sn-tree-trailing[data-open] { display: flex; }");
  });

  it("an open menu covers the whole page: the bar is fixed over everything while open", () => {
    const { container } = bar();
    const root = container.querySelector(".sn-tree-bar")!;
    expect(root).not.toHaveAttribute("data-menu-open");
    fireEvent.click(screen.getByLabelText("Menu"));
    expect(root).toHaveAttribute("data-menu-open");
    expect(container.querySelector("style")?.textContent).toMatch(/\.sn-tree-collapsible\.sn-tree-bar\[data-menu-open\] \{ position: fixed; inset: 0;/);
    fireEvent.click(screen.getByLabelText("Menu"));
    expect(root).not.toHaveAttribute("data-menu-open");
  });

  it("an open menu stretches its entries and its tools over the whole width", () => {
    const { container } = bar();
    const css = container.querySelector("style")?.textContent ?? "";
    expect(css).toContain(".sn-tree-collapsible .sn-tree-list > li { width: 100%; }");
    expect(css).toMatch(/\.sn-tree-collapsible \.sn-tree-list \.sn-tree-entry \{ width: 100%;/);
    expect(css).toContain(".sn-tree-collapsible .sn-tree-trailing { display: none; flex: 1 1 100%; order: 4; width: 100%;");
  });

  it("the narrow-window rules belong to the collapsing bar only, so another tree on the page cannot undo them", () => {
    const { container } = render(
      <>
        <TreeView data={MENU} orientation="horizontal" aria-label="Bar" />
        <TreeView data={MENU} orientation="horizontal" aria-label="Tabs" collapseBelow={false} />
      </>,
    );
    const [bar, tabs] = [screen.getByRole("navigation", { name: "Bar" }), screen.getByRole("navigation", { name: "Tabs" })];
    expect(bar).toHaveClass("sn-tree-collapsible");
    expect(tabs).not.toHaveClass("sn-tree-collapsible");
    const [barCss, tabsCss] = [...container.querySelectorAll("style")].map((style) => style.textContent ?? "");
    // every rule inside the media query is tied to the collapsing class (the plain tree's own rules come later and are
    // not tied to anything, so the tied ones must be the more specific)
    const media = barCss.slice(barCss.indexOf("@media"));
    for (const rule of media.match(/^\s+\.[^{]+\{/gm) ?? []) expect(rule.trim().startsWith(".sn-tree-collapsible")).toBe(true);
    expect(tabsCss).not.toContain("@media");
  });

  it("the breakpoint can be changed", () => {
    const { container } = bar({ collapseBelow: 900 });
    expect(container.querySelector("style")?.textContent).toContain("@media (max-width: 899px)");
  });

  it("collapseBelow={false} keeps the bar horizontal at every width: no menu button, no media query", () => {
    const { container } = bar({ collapseBelow: false });
    expect(screen.queryByLabelText("Menu")).not.toBeInTheDocument();
    expect(container.querySelector("style")?.textContent).not.toContain("@media");
  });

  it("the menu button's name can be translated", () => {
    bar({ menuLabel: "Mở menu" });
    expect(screen.getByLabelText("Mở menu")).toBeInTheDocument();
  });

  it("the vertical tree has no menu button and no media query of its own", () => {
    const { container } = render(<TreeView data={MENU} />);
    expect(container.querySelector(".sn-tree-menu")).toBeNull();
    expect(container.querySelector("style")?.textContent).not.toContain("@media");
  });
});

describe("TreeView following the address", () => {
  const FILES: TreeNode[] = [
    { key: "file", label: "File", href: "/work#file" },
    { key: "db", label: "Database", href: "/work#database" },
  ];
  const go = (hash: string) => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  };
  afterEach(() => {
    window.location.hash = "";
  });

  it("starts from activeHref, then follows the browser's path and hash once mounted", () => {
    window.history.pushState(null, "", "/work#database");
    render(<TreeView data={FILES} activeHref="/work#file" followLocation />);
    expect(screen.getByRole("link", { name: "Database" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "File" })).not.toHaveAttribute("aria-current");
  });

  it("marks the other link when only the hash changes", () => {
    window.history.pushState(null, "", "/work#file");
    render(<TreeView data={FILES} followLocation />);
    expect(screen.getByRole("link", { name: "File" })).toHaveAttribute("aria-current", "page");
    act(() => go("#database"));
    expect(screen.getByRole("link", { name: "Database" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "File" })).not.toHaveAttribute("aria-current");
  });

  it("also follows the history (Back and Forward)", () => {
    window.history.pushState(null, "", "/work#file");
    render(<TreeView data={FILES} followLocation />);
    act(() => {
      window.history.pushState(null, "", "/work#database");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole("link", { name: "Database" })).toHaveAttribute("aria-current", "page");
  });

  it("with a fixed activeHref and no followLocation it ignores the browser", () => {
    window.history.pushState(null, "", "/work#database");
    render(<TreeView data={FILES} activeHref="/work#file" />);
    expect(screen.getByRole("link", { name: "File" })).toHaveAttribute("aria-current", "page");
    act(() => go("#database"));
    expect(screen.getByRole("link", { name: "File" })).toHaveAttribute("aria-current", "page");
  });

  it("stops listening when it unmounts", () => {
    const remove = vi.spyOn(window, "removeEventListener");
    const view = render(<TreeView data={FILES} followLocation />);
    view.unmount();
    expect(remove).toHaveBeenCalledWith("hashchange", expect.any(Function));
    expect(remove).toHaveBeenCalledWith("popstate", expect.any(Function));
    remove.mockRestore();
  });
});
