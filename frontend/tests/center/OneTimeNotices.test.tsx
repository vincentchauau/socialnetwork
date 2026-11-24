import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import OneTimeNotices from "../../app/center/components/OneTimeNotices";

describe("OneTimeNotices", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("shows the username made for the person and the address the mail went to, once", async () => {
    window.sessionStorage.setItem("center.newUsername", "user-1a2b3c");
    window.sessionStorage.setItem("center.verifyEmail", "ann@example.com");
    render(<OneTimeNotices />);
    expect(await screen.findByText(/user-1a2b3c/)).toBeInTheDocument();
    expect(screen.getByText(/ann@example\.com/)).toBeInTheDocument();
    expect(window.sessionStorage.getItem("center.newUsername")).toBeNull(); // read, so removed
  });

  it("shows the profile that did not save", async () => {
    window.sessionStorage.setItem("sn_profile_unsaved", "1");
    render(<OneTimeNotices />);
    expect(await screen.findByText(/hồ sơ chưa lưu được|could not be saved/)).toBeInTheDocument();
  });

  it("hides a notice when it is closed", async () => {
    window.sessionStorage.setItem("center.newUsername", "user-9b1c3d");
    render(<OneTimeNotices />);
    await userEvent.click(await screen.findByRole("button", { name: /Đóng|Close/ }));
    await waitFor(() => expect(screen.queryByText(/user-9b1c3d/)).not.toBeInTheDocument());
  });

  it("shows nothing when there is no notice", async () => {
    const { container } = render(<OneTimeNotices />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
