import { screen, waitFor } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";

/**
 * Helpers for the tab bar (TabPanel over the horizontal TreeView). A tab inside a group is a link that exists only while
 * the group's drop-down is open, and picking it closes the drop-down again, so tests go through these instead of
 * querying the link directly.
 */
type User = ReturnType<typeof userEvent.setup>;

const groupButtons = () => screen.queryAllByRole("button").filter((button) => button.hasAttribute("aria-haspopup"));
const tabLink = (name: string) => screen.queryByRole("link", { name });

/** The link of a tab, waiting for the bar to have it; opens the groups one after the other until it is shown. */
async function findTabLink(user: User, name: string): Promise<HTMLElement> {
  let found: HTMLElement | null = null;
  await waitFor(async () => {
    found = tabLink(name);
    if (found) return;
    for (const button of groupButtons()) {
      if (button.getAttribute("aria-expanded") === "true") await user.click(button); // close the one left open
    }
    for (const button of groupButtons()) {
      await user.click(button); // opening a group closes the previous one
      found = tabLink(name);
      if (found) return;
    }
    if (groupButtons().some((button) => button.getAttribute("aria-expanded") === "true")) await user.keyboard("{Escape}");
    throw new Error(`No tab named "${name}"`);
  });
  return found as unknown as HTMLElement;
}

/** Waits until the bar has a tab with this name (the bar grows when the config arrives); leaves the drop-downs closed. */
export async function waitForTab(user: User, name: string): Promise<void> {
  await findTabLink(user, name);
  if (groupButtons().some((button) => button.getAttribute("aria-expanded") === "true")) await user.keyboard("{Escape}");
}

/** Opens a tab by its name, opening its group first when it sits in one. */
export async function selectTab(user: User, name: string): Promise<void> {
  await user.click(await findTabLink(user, name));
}

/** Every tab of a bar, in order, reading each group's drop-down in turn. */
export async function tabNames(user: User, barName: string): Promise<string[]> {
  const list = screen.getByRole("navigation", { name: barName }).querySelector("ul") as HTMLElement;
  const names: string[] = [];
  for (const item of Array.from(list.children)) {
    const first = item.firstElementChild as HTMLElement;
    if (first.tagName === "A") {
      names.push(first.textContent ?? "");
      continue;
    }
    await user.click(first);
    for (const link of Array.from(item.querySelectorAll("a"))) names.push(link.textContent ?? "");
    await user.click(first);
  }
  return names;
}

/** The name of the tab that is open: a top-level link, or the tab inside the group that is marked active. */
export async function currentTab(user: User, barName: string): Promise<string | undefined> {
  const list = screen.getByRole("navigation", { name: barName }).querySelector("ul") as HTMLElement;
  for (const item of Array.from(list.children)) {
    const first = item.firstElementChild as HTMLElement;
    if (first.tagName === "A") {
      if (first.getAttribute("aria-current") === "page") return first.textContent ?? undefined;
      continue;
    }
    if (!first.hasAttribute("data-active")) continue;
    await user.click(first);
    const open = item.querySelector('a[aria-current="page"]')?.textContent ?? undefined;
    await user.click(first);
    return open;
  }
  return undefined;
}
