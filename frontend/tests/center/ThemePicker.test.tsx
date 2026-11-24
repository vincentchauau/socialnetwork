import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { ThemePicker } from "@sn/compounds/SiteSettings";
import { THEME_STORAGE_KEY, buildTheme } from "@sn/lib/theme";

const root = () => document.documentElement.style;

function open() {
  fireEvent.click(screen.getByRole("button", { name: "Theme" }));
}

const colorInput = () => screen.getByLabelText("Main color", { selector: 'input[type="color"]' });

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("style");
});

test("changes nothing until the user picks something", () => {
  render(<ThemePicker />);
  expect(document.documentElement.getAttribute("style")).toBeNull();
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
});

test("the color picker sets the page color through the shared tokens", () => {
  render(<ThemePicker />);
  open();
  fireEvent.change(colorInput(), { target: { value: "#101010" } });
  expect(root().getPropertyValue("--solid-0")).toBe("#101010");
  expect(root().getPropertyValue("--line")).toBe("#ffffff");
});

test("the accent count changes the accent slots and is clamped", () => {
  render(<ThemePicker />);
  open();
  const count = screen.getByRole("spinbutton", { name: "Accent colors" });
  fireEvent.change(count, { target: { value: "2" } });
  expect(root().getPropertyValue("--solid-2")).toBe(root().getPropertyValue("--solid-0"));
  fireEvent.change(count, { target: { value: "99" } });
  expect(count).toHaveValue(8);
});

test("saves the theme, restores it on the next load and shows the saved color", () => {
  const first = render(<ThemePicker />);
  open();
  fireEvent.change(colorInput(), { target: { value: "#16a34a" } });
  first.unmount();
  document.documentElement.removeAttribute("style");

  render(<ThemePicker />);
  expect(root().getPropertyValue("--solid-0")).toBe(buildTheme({ primary: "#16a34a", count: 3, contrast: 4.5 }).vars["--solid-0"]);
  open();
  expect(colorInput()).toHaveValue("#16a34a");
});

test("an invalid saved theme is ignored", () => {
  localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify({ primary: "javascript:alert(1)", count: 3, contrast: 4.5 }));
  render(<ThemePicker />);
  expect(document.documentElement.getAttribute("style")).toBeNull();
});

test("follows a theme change made in another tab", () => {
  render(<ThemePicker />);
  const { vars } = buildTheme({ primary: "#101010", count: 3, contrast: 4.5 });
  localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify({ primary: "#101010", count: 3, contrast: 4.5 }));
  fireEvent(window, new StorageEvent("storage", { key: THEME_STORAGE_KEY }));
  expect(root().getPropertyValue("--solid-0")).toBe(vars["--solid-0"]);
});

test("closes on Escape and on an outside click", () => {
  render(<ThemePicker />);
  open();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  open();
  fireEvent.mouseDown(document.body);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("labels can be translated", () => {
  render(<ThemePicker labels={{ theme: "Giao diện", color: "Màu chủ đạo" }} />);
  fireEvent.click(screen.getByRole("button", { name: "Giao diện" }));
  expect(screen.getByLabelText("Màu chủ đạo", { selector: 'input[type="color"]' })).toBeInTheDocument();
});

test("shows one swatch per color, edged with the line color", () => {
  render(<ThemePicker />);
  open();
  fireEvent.change(screen.getByRole("spinbutton", { name: "Accent colors" }), { target: { value: "4" } });
  const swatches = screen.getByRole("dialog").querySelectorAll('[aria-hidden="true"] > span');
  expect(swatches).toHaveLength(4);
  expect((swatches[0] as HTMLElement).style.border).toContain("var(--line");
});
