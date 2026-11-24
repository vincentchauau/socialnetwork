import { LocaleProvider } from "@sn/lib/i18n";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Alert, AUTH_GATE_LABELS_VI, AuthGate, Card } from "@sn/ui";
import { type Auth, useSession } from "@sn/lib/useSession";

const loadSession = vi.hoisted(() => vi.fn());
vi.mock("@sn/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@sn/api")>()), loadSession }));

describe("Alert", () => {
  it("an error is an assertive alert", () => {
    render(<Alert>Something broke</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Something broke");
    expect(alert).toHaveAttribute("aria-live", "assertive");
    expect(alert.getAttribute("style")).toContain("--line");
  });

  it("the other tones are polite status messages", () => {
    const { rerender } = render(<Alert tone="success">Saved</Alert>);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    rerender(<Alert tone="info">Note</Alert>);
    expect(screen.getByRole("status")).toHaveTextContent("Note");
  });

  it.each([null, undefined, false, ""])("stays in the page but hidden when there is nothing to say (%p)", (nothing) => {
    const { container } = render(<Alert>{nothing}</Alert>);
    const region = container.firstElementChild as HTMLElement;
    expect(region).toHaveAttribute("hidden");
    expect(region).toHaveAttribute("role", "alert");
  });

  it("shows up when text arrives in the same region", () => {
    const { container, rerender } = render(<Alert>{null}</Alert>);
    const before = container.firstElementChild;
    rerender(<Alert>Late news</Alert>);
    expect(container.firstElementChild).toBe(before);
    expect(screen.getByRole("alert")).toBeVisible();
  });

  it("accepts a class and a style from the caller", () => {
    render(<Alert className="mt-2" style={{ fontSize: 20 }}>Hi</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("mt-2");
    expect(alert).toHaveStyle({ fontSize: "20px" });
  });
});

describe("Card", () => {
  it("is a bordered panel on the surface color that works without theme.css", () => {
    render(<Card data-testid="card">Body</Card>);
    const style = screen.getByTestId("card").getAttribute("style") ?? "";
    expect(style).toContain("border");
    expect(style).toContain("var(--line");
    expect(screen.getByText("Body")).toBeInTheDocument();
  });

  it("stacks its children in a column only when asked", () => {
    const { rerender } = render(<Card data-testid="card">x</Card>);
    expect(screen.getByTestId("card")).not.toHaveStyle({ display: "flex" });
    rerender(<Card data-testid="card" stack>x</Card>);
    expect(screen.getByTestId("card")).toHaveStyle({ display: "flex", flexDirection: "column" });
  });

  it("passes attributes through and lets the caller override the style", () => {
    render(<Card role="dialog" aria-label="Settings" style={{ padding: 4 }}>x</Card>);
    const card = screen.getByRole("dialog", { name: "Settings" });
    expect(card).toHaveStyle({ padding: "4px" });
  });
});

describe("useSession", () => {
  beforeEach(() => {
    loadSession.mockReset();
  });

  function Probe() {
    const auth: Auth = useSession();
    return <p>{auth.status === "signed-in" ? `in:${auth.user.username}` : auth.status}</p>;
  }

  it("goes from loading to signed in", async () => {
    loadSession.mockResolvedValue({ id: 1, username: "ann" });
    render(<Probe />);
    expect(screen.getByText("loading")).toBeInTheDocument();
    expect(await screen.findByText("in:ann")).toBeInTheDocument();
  });

  it("is anonymous without a session, and reports an error when the server cannot be reached", async () => {
    loadSession.mockResolvedValue(null);
    const first = render(<Probe />);
    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    first.unmount();
    loadSession.mockRejectedValue(new Error("down"));
    render(<Probe />);
    expect(await screen.findByText("error")).toBeInTheDocument();
  });
});

describe("AuthGate", () => {
  beforeEach(() => {
    loadSession.mockReset();
  });
  const inEnglish = (ui: React.ReactElement) => render(<LocaleProvider defaultLocale="en">{ui}</LocaleProvider>);

  it("shows the loading text, then the page for a signed-in user, who is passed to children", async () => {
    loadSession.mockResolvedValue({ id: 7, username: "ann", group: "admin" });
    inEnglish(<AuthGate title="Files">{(user) => <p>{`hello ${user.username} (${user.group})`}</p>}</AuthGate>);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(await screen.findByText("hello ann (admin)")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Files" })).not.toBeInTheDocument();
  });

  it("asks an anonymous visitor to sign in, and never renders the page", async () => {
    loadSession.mockResolvedValue(null);
    inEnglish(<AuthGate title="Files">{() => <p>secret</p>}</AuthGate>);
    expect(await screen.findByRole("link", { name: "sign in" })).toHaveAttribute("href", "/user");
    expect(screen.getByRole("heading", { name: "Files" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Home" })).toHaveAttribute("href", "/");
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("reports a server problem as an alert, and never renders the page", async () => {
    loadSession.mockRejectedValue(new Error("down"));
    inEnglish(<AuthGate title="Files">{() => <p>secret</p>}</AuthGate>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server");
    expect(screen.queryByRole("link", { name: "sign in" })).not.toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("speaks Vietnamese when the site is in Vietnamese (the default), keeping the strings the apps' tests rely on", async () => {
    loadSession.mockResolvedValue(null);
    const first = render(<LocaleProvider defaultLocale="vi"><AuthGate title="T">{() => <p>x</p>}</AuthGate></LocaleProvider>);
    expect(screen.getByText("Đang tải…")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "đăng nhập" })).toHaveAttribute("href", "/user");
    expect(screen.getByText(/Hãy/)).toBeInTheDocument();
    first.unmount();
    loadSession.mockRejectedValue(new Error("down"));
    render(<LocaleProvider defaultLocale="vi"><AuthGate title="T">{() => <p>x</p>}</AuthGate></LocaleProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
  });

  it("a single label can be replaced and the rest stay in the language of the site", async () => {
    loadSession.mockResolvedValue(null);
    inEnglish(<AuthGate title="T" labels={{ home: "Back" }}>{() => <p>x</p>}</AuthGate>);
    expect(await screen.findByRole("link", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "sign in" })).toBeInTheDocument();
  });
});
