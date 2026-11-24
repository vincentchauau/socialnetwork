import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TabPanel, type TreeNode } from "@sn/ui";
import { currentTab, selectTab, tabNames } from "./tabs";

const DATA: TreeNode[] = [
  {
    key: "login",
    label: "Đăng nhập",
    children: [
      { key: "password", label: "Mật khẩu" },
      { key: "passkey", label: "Passkey" },
    ],
  },
  { key: "totp", label: "Xác thực hai bước" },
];

const PANELS = {
  password: <p>panel-password</p>,
  passkey: <p>panel-passkey <span id="add-passkey">add</span></p>,
  totp: <p>panel-totp</p>,
};

function setup(extra: Partial<React.ComponentProps<typeof TabPanel>> = {}) {
  return render(<TabPanel data={DATA} panels={PANELS} aria-label="Cài đặt" {...extra} />);
}

describe("TabPanel", () => {
  beforeEach(() => {
    window.location.hash = "";
  });
  afterEach(() => {
    window.location.hash = "";
  });

  it("shows the first tab and keeps every panel mounted", () => {
    setup();
    expect(screen.getByText("panel-password")).toBeVisible();
    expect(screen.getByText("panel-passkey", { exact: false })).not.toBeVisible();
    expect(screen.getByText("panel-totp")).not.toBeVisible();
  });

  it("draws a group as a drop-down of its tabs and a top-level tab as a link to #key", async () => {
    const user = userEvent.setup();
    setup();
    const nav = screen.getByRole("navigation", { name: "Cài đặt" });
    expect(screen.getByRole("link", { name: "Xác thực hai bước" })).toHaveAttribute("href", "#totp");
    expect(screen.queryByRole("link", { name: "Passkey" })).not.toBeInTheDocument(); // the drop-down is closed
    await user.click(within(nav).getByRole("button", { name: /Đăng nhập/ }));
    expect(screen.getByRole("link", { name: "Passkey" })).toHaveAttribute("href", "#passkey");
    await user.keyboard("{Escape}");
    expect(await tabNames(user, "Cài đặt")).toEqual(["Mật khẩu", "Passkey", "Xác thực hai bước"]);
  });

  it("marks the open tab as current and switches panels on click", async () => {
    const user = userEvent.setup();
    setup();
    expect(await currentTab(user, "Cài đặt")).toBe("Mật khẩu");
    await selectTab(user, "Xác thực hai bước");
    expect(screen.getByText("panel-totp")).toBeVisible();
    expect(screen.getByText("panel-password")).not.toBeVisible();
    expect(await currentTab(user, "Cài đặt")).toBe("Xác thực hai bước");
    await selectTab(user, "Passkey"); // a tab in a group: the drop-down opens first
    expect(screen.getByText("panel-passkey", { exact: false })).toBeVisible();
    expect(await currentTab(user, "Cài đặt")).toBe("Passkey");
  });

  it("follows activeKey when controlled and reports clicks", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    setup({ activeKey: "passkey", onChange });
    expect(await currentTab(user, "Cài đặt")).toBe("Passkey");
    await selectTab(user, "Xác thực hai bước");
    expect(onChange).toHaveBeenCalledWith("totp");
  });

  it("opens the tab named by the URL hash on load", () => {
    window.location.hash = "#totp";
    setup();
    expect(screen.getByText("panel-totp")).toBeVisible();
  });

  it("follows a later hash change (Back/Forward)", () => {
    setup();
    window.location.hash = "#passkey";
    fireEvent(window, new HashChangeEvent("hashchange"));
    expect(screen.getByText("panel-passkey", { exact: false })).toBeVisible();
  });

  it("opens the tab behind an alias hash and scrolls to the target inside it", () => {
    const scroll = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = scroll;
    window.location.hash = "#add-passkey";
    setup({ aliases: { "add-passkey": "passkey" } });
    expect(screen.getByText("panel-passkey", { exact: false })).toBeVisible();
    expect(scroll).toHaveBeenCalled();
  });

  it("ignores a hash that matches no tab", () => {
    window.location.hash = "#nothing";
    setup();
    expect(screen.getByText("panel-password")).toBeVisible();
  });
});

describe("TabPanel keepMounted={false}", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  it("builds only the open tab's panel", () => {
    const built = vi.fn((name: string) => <p>{name}</p>);
    const panels = { password: built("p"), passkey: <span>never-built</span>, totp: <span>never-built-2</span> };
    render(<TabPanel data={DATA} panels={panels} aria-label="Cài đặt" keepMounted={false} />);
    expect(screen.getByText("p")).toBeVisible();
    expect(screen.queryByText("never-built")).not.toBeInTheDocument();
    expect(screen.queryByText("never-built-2")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Xác thực hai bước" }));
    expect(screen.getByText("never-built-2")).toBeVisible();
    expect(screen.queryByText("p")).not.toBeInTheDocument();
  });

  it("falls back to the first tab when the active one disappears from data", () => {
    const { rerender } = render(<TabPanel data={DATA} panels={PANELS} aria-label="Cài đặt" activeKey="totp" />);
    expect(screen.getByText("panel-totp")).toBeVisible();
    rerender(<TabPanel data={DATA.slice(0, 1)} panels={PANELS} aria-label="Cài đặt" activeKey="totp" />);
    expect(screen.getByText("panel-password")).toBeVisible();
  });
});
