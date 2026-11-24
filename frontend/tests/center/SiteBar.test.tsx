import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { jsonResponse, me, mockFetch } from "./helpers";

import { LOCALE_STORAGE_KEY, LocaleProvider } from "@sn/lib/i18n";
import SiteBar from "@sn/complex/SiteBar";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.lang = "";
});

test("offers the language switcher and the theme picker together", () => {
  render(<SiteBar name="Chat" href="/chat" />);
  expect(screen.getByRole("combobox", { name: "Ngôn ngữ" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Giao diện" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Tiếng Việt" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "English" })).toBeInTheDocument();
});

test("choosing a language sets <html lang> and is saved for the other apps", () => {
  render(<SiteBar name="Chat" href="/chat" />);
  fireEvent.change(screen.getByRole("combobox", { name: "Ngôn ngữ" }), { target: { value: "en" } });
  expect(document.documentElement.lang).toBe("en");
  expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en");
});

test("starts from the language chosen earlier", async () => {
  localStorage.setItem(LOCALE_STORAGE_KEY, "en");
  render(<SiteBar name="Chat" href="/chat" />);
  expect(await screen.findByRole("combobox", { name: "Language" })).toHaveValue("en");
  expect(document.documentElement.lang).toBe("en");
});

test("greets a signed-in user next to the language switcher, as plain text", async () => {
  mockFetch((url) => (url.endsWith("/auth/me") ? jsonResponse(me) : jsonResponse({}, 404)));
  render(<SiteBar name="Chat" href="/chat" />);
  const greeting = await screen.findByText("Xin chào, ann");
  expect(greeting.closest("a")).toBeNull();
  expect(screen.getByRole("combobox", { name: "Ngôn ngữ" })).toBeInTheDocument();
});

test("shows no greeting while signed out", async () => {
  const fn = mockFetch((url) => (url.endsWith("/auth/me") ? jsonResponse({ detail: "no" }, 401) : jsonResponse({}, 401)));
  render(<SiteBar name="Chat" href="/chat" />);
  await vi.waitFor(() => expect(fn).toHaveBeenCalled());
  expect(screen.queryByText(/Xin chào/)).not.toBeInTheDocument();
});

test("choosing English changes the words of the bar, not only <html lang>", async () => {
  const { useT } = await import("@sn/locales");
  function Probe() {
    return <p>{useT().t("site.language")}</p>;
  }
  render(
    <LocaleProvider>
      <SiteBar name="Chat" href="/chat" />
      <Probe />
    </LocaleProvider>,
  );
  expect(screen.getAllByText("Ngôn ngữ").length).toBeGreaterThan(0);
  fireEvent.change(screen.getByRole("combobox", { name: "Ngôn ngữ" }), { target: { value: "en" } });
  expect(screen.getByRole("combobox", { name: "Language" })).toBeInTheDocument();
  expect(screen.getByText("Language")).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();
});
