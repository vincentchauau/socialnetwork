import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginFlow from "../../app/center/components/LoginFlow";
import { takeProfileUnsaved } from "../../app/center/lib/profile";
import { jsonResponse, me, mockFetch, session } from "./helpers";

const goTo = vi.hoisted(() => vi.fn());
vi.mock("../../app/center/lib/navigate", async (original) => ({
  ...(await original<typeof import("../../app/center/lib/navigate")>()),
  goTo,
}));

vi.mock("@simplewebauthn/browser", () => ({
  browserSupportsWebAuthn: () => true,
  startAuthentication: vi.fn(),
  startRegistration: vi.fn(),
}));

const PLAIN = { google_client_id: null, biometrics_enabled: false };
const STORED = { name: "Ann Nguyen", city: "Hà Nội", skills: [{ name: "Python", level: "advanced", years: 5 }] };

type User = ReturnType<typeof userEvent.setup>;
type Handler = (url: string, init: RequestInit) => Response | undefined;

const bodyOf = (call: [string, RequestInit]) => JSON.parse(call[1].body as string);
const profileCalls = (fetchMock: ReturnType<typeof mockFetch>, method: string) =>
  fetchMock.mock.calls.filter(([url, init]) => url.endsWith("/auth/me/profile") && (init?.method ?? "GET") === method);

/** A signed-in visitor: /login opens on Cập nhật, whose profile is `stored`; `put` answers a save. */
function account(stored: Record<string, unknown> = STORED, put?: Handler) {
  let current = { ...stored };
  return mockFetch((url, init) => {
    if (url.endsWith("/auth/me/profile")) {
      if (init.method === "PUT") {
        const custom = put?.(url, init);
        if (custom) return custom;
        current = { ...current, ...JSON.parse(init.body as string) };
      }
      return jsonResponse(current);
    }
    if (url.endsWith("/auth/sessions")) return jsonResponse([]);
    if (url.endsWith("/auth/config")) return jsonResponse(PLAIN);
    if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(me);
    return jsonResponse({});
  });
}

const apply = (user: User) => user.click(screen.getByRole("button", { name: "Đổi tài khoản" }));
const nameField = () => screen.findByLabelText("Họ và tên");

beforeEach(() => {
  window.sessionStorage.clear();
  goTo.mockReset();
  window.history.pushState({}, "", "/user");
});

describe("the profile on the Cập nhật screen", () => {
  it("shows what is stored, in its groups", async () => {
    account();
    render(<LoginFlow />);
    expect(await nameField()).toHaveValue("Ann Nguyen");
    expect(screen.getByLabelText("Thành phố")).toHaveValue("Hà Nội");
    expect(screen.getByRole("group", { name: "Kỹ năng" })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Kỹ năng \*/)).toHaveValue("Python");
  });

  it("is not saved until the page's one button is pressed, and then sends only what changed", async () => {
    const fetchMock = account();
    const user = userEvent.setup();
    render(<LoginFlow />);
    const name = await nameField();
    await user.clear(name);
    await user.type(name, "Ann Lee");
    expect(profileCalls(fetchMock, "PUT")).toHaveLength(0);
    expect(screen.getByText(/Thay đổi đang chờ: .*Hồ sơ/)).toBeInTheDocument();
    await apply(user);
    await waitFor(() => expect(profileCalls(fetchMock, "PUT")).toHaveLength(1));
    expect(bodyOf(profileCalls(fetchMock, "PUT")[0] as [string, RequestInit])).toEqual({ name: "Ann Lee" });
    expect(await screen.findByText("Đã lưu hồ sơ.")).toBeInTheDocument();
    expect(screen.getByText(/Chưa có thay đổi nào/)).toBeInTheDocument();
  });

  it("sends null to clear a field", async () => {
    const fetchMock = account();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.clear(await screen.findByLabelText("Thành phố"));
    await apply(user);
    await waitFor(() => expect(profileCalls(fetchMock, "PUT")).toHaveLength(1));
    expect(bodyOf(profileCalls(fetchMock, "PUT")[0] as [string, RequestInit])).toEqual({ city: null });
  });

  it("adds a row to a list, sends the list whole, and drops a row nobody typed in", async () => {
    const fetchMock = account({});
    const user = userEvent.setup();
    render(<LoginFlow />);
    await nameField();
    await user.click(screen.getByRole("button", { name: "Thêm Kỹ năng" }));
    await user.type(screen.getByLabelText(/^Kỹ năng \*/), "Go");
    await user.click(screen.getByRole("button", { name: "Thêm Kỹ năng" })); // a second row, left blank
    await apply(user);
    await waitFor(() => expect(profileCalls(fetchMock, "PUT")).toHaveLength(1));
    expect(bodyOf(profileCalls(fetchMock, "PUT")[0] as [string, RequestInit])).toEqual({ skills: [{ name: "Go" }] });
  });

  it("removes a row", async () => {
    const fetchMock = account();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await nameField();
    await user.click(screen.getByRole("button", { name: "Xóa mục Kỹ năng 1" }));
    await apply(user);
    await waitFor(() => expect(profileCalls(fetchMock, "PUT")).toHaveLength(1));
    expect(bodyOf(profileCalls(fetchMock, "PUT")[0] as [string, RequestInit])).toEqual({ skills: [] });
  });

  it("asks for the missing required field of a row before sending anything", async () => {
    const fetchMock = account({});
    const user = userEvent.setup();
    render(<LoginFlow />);
    await nameField();
    await user.click(screen.getByRole("button", { name: "Thêm Kỹ năng" }));
    await user.type(screen.getByLabelText("Số năm"), "3");
    await apply(user);
    expect(await screen.findByText("Thiếu: Kỹ năng")).toBeInTheDocument();
    expect(profileCalls(fetchMock, "PUT")).toHaveLength(0);
  });

  it("shows the server's reason when it refuses the profile, and keeps what was typed", async () => {
    account(STORED, () => jsonResponse({ detail: "The birth date cannot be in the future" }, 422));
    const user = userEvent.setup();
    render(<LoginFlow />);
    const name = await nameField();
    await user.clear(name);
    await user.type(name, "Ann Lee");
    await apply(user);
    expect(await screen.findByText(/The birth date cannot be in the future/)).toBeInTheDocument();
    expect(name).toHaveValue("Ann Lee");
  });

  it("says when the profile cannot be loaded and offers to try again", async () => {
    let up = false;
    mockFetch((url, init) => {
      if (url.endsWith("/auth/me/profile")) return up ? jsonResponse({ name: "Ann" }) : jsonResponse({ detail: "down" }, 503);
      if (url.endsWith("/auth/sessions")) return jsonResponse([]);
      if (url.endsWith("/auth/config")) return jsonResponse(PLAIN);
      if (url.endsWith("/auth/me") && (init.method ?? "GET") === "GET") return jsonResponse(me);
      return jsonResponse({});
    });
    const user = userEvent.setup();
    render(<LoginFlow />);
    const retry = await screen.findByRole("button", { name: "Thử lại" });
    up = true;
    await user.click(retry);
    expect(await nameField()).toHaveValue("Ann");
  });

  it("keeps each part private unless it is changed", async () => {
    const fetchMock = account({});
    const user = userEvent.setup();
    render(<LoginFlow />);
    await nameField();
    expect(screen.getByLabelText("Địa chỉ", { selector: "select" })).toHaveValue("private");
    await user.selectOptions(screen.getByLabelText("Địa chỉ", { selector: "select" }), "employers");
    await apply(user);
    await waitFor(() => expect(profileCalls(fetchMock, "PUT")).toHaveLength(1));
    expect(bodyOf(profileCalls(fetchMock, "PUT")[0] as [string, RequestInit])).toEqual({ visibility: { address: "employers" } });
  });
});

describe("the profile when registering", () => {
  function registering(put?: Handler) {
    return mockFetch((url, init) => {
      if (url.endsWith("/auth/config")) return jsonResponse(PLAIN);
      if (url.endsWith("/register/combined")) return jsonResponse(session, 201);
      if (url.endsWith("/auth/me/profile") && init.method === "PUT") return put?.(url, init) ?? jsonResponse({});
      return jsonResponse({ detail: "no session" }, 401);
    });
  }
  async function fillAccount(user: User) {
    await user.click(await screen.findByRole("tab", { name: "Đăng ký" }));
    await user.type(await screen.findByLabelText(/^Tên đăng nhập/), "ann");
    await user.type(screen.getByLabelText("Mật khẩu", { selector: "input[type=password]" }), "Password-1x");
  }

  it("offers the profile as an optional part, with no checkbox", async () => {
    registering();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await user.click(await screen.findByRole("tab", { name: "Đăng ký" }));
    expect(screen.getByText("Hồ sơ (không bắt buộc)")).toBeInTheDocument();
    expect(screen.getByLabelText("Họ và tên")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("saves what was typed once the account exists", async () => {
    const fetchMock = registering();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAccount(user);
    await user.type(screen.getByLabelText("Họ và tên"), "Ann Nguyen");
    await user.type(screen.getByLabelText("Thành phố"), "Đà Nẵng");
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(bodyOf(profileCalls(fetchMock, "PUT")[0] as [string, RequestInit])).toEqual({ name: "Ann Nguyen", city: "Đà Nẵng" });
  });

  it("does not call the profile route when nothing was typed", async () => {
    const fetchMock = registering();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAccount(user);
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(profileCalls(fetchMock, "PUT")).toHaveLength(0);
  });

  it("tells a bad row before creating the account", async () => {
    const fetchMock = registering();
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAccount(user);
    await user.click(screen.getByRole("button", { name: "Thêm Kỹ năng" }));
    await user.type(screen.getByLabelText("Số năm"), "2");
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    expect(await screen.findByText("Thiếu: Kỹ năng")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/register/combined"))).toBe(false);
  });

  it("still signs up when the profile cannot be saved, and says so on the next screen", async () => {
    registering(() => jsonResponse({ detail: "down" }, 503));
    const user = userEvent.setup();
    render(<LoginFlow />);
    await fillAccount(user);
    await user.type(screen.getByLabelText("Họ và tên"), "Ann");
    await user.click(screen.getByRole("button", { name: "Đăng ký" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("/"));
    expect(takeProfileUnsaved()).toBe(true);
    expect(takeProfileUnsaved()).toBe(false); // once
  });
});
