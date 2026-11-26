import { ApiError, apiFetch } from "@sn/api";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DatabaseDock from "../../app/database/DatabaseDock";
import SiteBar from "@sn/complex/SiteBar";

const session = vi.hoisted(() => ({ group: "admin" }));
vi.mock("@sn/lib/useSession", () => ({ useSession: () => ({ status: "signed-in", user: { id: 1, username: "u", group: session.group } }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("../../app/chat/components/EmbedChat", () => ({ default: () => <p>chat</p> }));
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);
const col = { name: "id", type: "int", nullable: false, readonly: true, secret: false };
const tbl = (name: string, label: string) => ({ name, label, pk: ["id"], writable: true, columns: [col] });

beforeEach(() => {
  api.mockReset();
  window.localStorage.clear();
  api.mockImplementation(async (url: string) => {
    if (url === "/api/face/records/tables") return [{ ...tbl("a", "Alpha"), rows: 5 }, tbl("b", "Beta")];
    if (url === "/api/roulette/records/tables") return [tbl("m", "Lamp")];
    if (url.includes("/records/tables")) throw new ApiError(404, "nf", {});
    if (url.includes("/records/")) return { total: 0, rows: [] };
    return [];
  });
});

describe("DatabaseDock", () => {
  const bar = <SiteBar name="Table" href="/" />;
  // The Apps picker is a Select in the bar: its options are the apps.
  const appsPicker = () => screen.findByRole("combobox", { name: /Ứng dụng|Apps/ });

  it("shows the databases on the home page: the panes Database and Grid, and the chooser of the tables of every app", async () => {
    session.group = "admin";
    render(<DatabaseDock bar={bar}><p>sqlite tool</p></DatabaseDock>);
    expect(screen.getByText("sqlite tool")).toBeVisible();
    for (const name of ["Table", "Grid"]) expect(screen.getByRole("button", { name })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "User" })).toBeNull(); // the User panel is the page of an app, not a pane of the databases
    const apps = await appsPicker();
    expect(within(apps).getByRole("option", { name: /database/i })).toBeInTheDocument();
    expect(within(apps).getByRole("option", { name: /face/i })).toBeInTheDocument();
    expect(within(apps).getByRole("option", { name: /roulette/i })).toBeInTheDocument();
    expect(within(apps).queryByRole("option", { name: "Alpha (5)" })).toBeNull();
    const chooser = await screen.findByRole("combobox", { name: "Choose table" });
    for (const name of ["Alpha (5)", "Beta", "Lamp"]) expect(within(chooser).getByRole("option", { name })).toBeInTheDocument(); // the tables of all the apps
  });

  it("loads the table picked in the chooser through the database API and remembers it", async () => {
    session.group = "admin";
    const { unmount } = render(<DatabaseDock bar={bar}><p>sqlite tool</p></DatabaseDock>);
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Choose table" }), "Beta");
    unmount();
    render(<DatabaseDock bar={bar}><p>sqlite tool</p></DatabaseDock>);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Choose table" })).toHaveValue("face/b"));
  });

  it("keeps the Table chooser over every pane of the databases, even when only Database is shown", async () => {
    session.group = "admin";
    render(<DatabaseDock bar={bar}><p>sqlite tool</p></DatabaseDock>);
    await userEvent.click(screen.getByRole("button", { name: "Grid" })); // show a pane beside the page
    expect(screen.getByRole("button", { name: "Grid" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("combobox", { name: "Choose table" })).toBeInTheDocument();
  });

  it("makes the User panel of an app the page when the app is chosen, with no panes of the databases, and leaves out the Agent", async () => {
    session.group = "admin";
    render(<DatabaseDock bar={bar}><p>sqlite tool</p></DatabaseDock>);
    const menu = await appsPicker();
    expect(within(menu).queryByRole("option", { name: /agent/i })).toBeNull();
    expect(within(menu).queryByText(/^agent$/i)).toBeNull();
    expect(within(menu).getByRole("option", { name: /users/i })).toBeInTheDocument(); // Users is an app of the home page
    expect(within(menu).getByRole("option", { name: /file/i })).toBeInTheDocument(); // (no table: listed all the same)
    await userEvent.selectOptions(menu, within(menu).getByRole("option", { name: /face/i }));
    await waitFor(() => expect(screen.queryByText("sqlite tool")).toBeNull());
    for (const name of ["Grid", "User"]) expect(screen.queryByRole("button", { name })).toBeNull();
    await userEvent.selectOptions(await appsPicker(), within(await appsPicker()).getByRole("option", { name: /database/i }));
    expect(await screen.findByText("sqlite tool")).toBeVisible(); // back to the databases
  });

  it("gives anyone else the SQLite tool, and the User panel of an app from the Apps menu, with no call for every row and no Table or Grid", async () => {
    session.group = "user";
    api.mockImplementation(async (url: string) => (url === "/api/roulette/records/tables" ? [{ ...tbl("m", "Lamp"), writable: true }] : url.includes("/records/tables") ? [] : { total: 0, rows: [] }));
    render(<DatabaseDock bar={bar}><p>sqlite tool</p></DatabaseDock>);
    expect(screen.getByText("sqlite tool")).toBeVisible();
    expect(screen.getByRole("button", { name: "Table" })).toBeInTheDocument();
    for (const name of ["Grid", "User"]) expect(screen.queryByRole("button", { name })).toBeNull();
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/roulette/records/tables"));
    await userEvent.selectOptions(await appsPicker(), within(await appsPicker()).getByRole("option", { name: /roulette/i }));
    await waitFor(() => expect(screen.queryByText("sqlite tool")).toBeNull());
    expect(api.mock.calls.some(([url]) => String(url).includes("scope=all"))).toBe(false);
  });
});
