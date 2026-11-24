import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import FaceCard from "../../../app/chat/components/FaceCard";
import { buildFace } from "../../face/helpers";
import { installBrowserStubs, makeDeps, pump } from "../../face/harness";

beforeEach(() => installBrowserStubs());
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const start = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole("button", { name: "Bật camera" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Tắt camera" })).toBeInTheDocument());
};

describe("the face meter in a card", () => {
  it("keeps the camera off until it is asked, and cannot save before a face is seen", () => {
    const { deps } = makeDeps();
    render(<FaceCard title="Face symmetry" saving={false} error={null} onSave={vi.fn()} deps={deps} />);
    expect(deps.openCamera).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Lưu kết quả" })).toBeDisabled();
    expect(screen.getByText(/Hình ảnh không rời khỏi thiết bị/)).toBeInTheDocument();
  });

  it("shows the scores of the face it sees and saves only those numbers", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const { deps } = makeDeps([null, buildFace()]);
    render(<FaceCard title="Face symmetry" saving={false} error={null} onSave={onSave} deps={deps} />);
    await start(user);
    await pump(12);
    await waitFor(() => expect(screen.getByRole("button", { name: "Lưu kết quả" })).toBeEnabled());
    expect(screen.getByText("Đối xứng")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Lưu kết quả" }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const saved = onSave.mock.calls[0][0];
    expect(Object.keys(saved).sort()).toEqual(["angle", "ear", "eye", "mouth", "nose", "symmetry"]);
    expect(saved.symmetry).toBeGreaterThan(0);
  });

  it("turns the camera off and lets go of it", async () => {
    const user = userEvent.setup();
    const { deps, stop, landmarker } = makeDeps();
    render(<FaceCard title="Face symmetry" saving={false} error={null} onSave={vi.fn()} deps={deps} />);
    await start(user);
    await user.click(screen.getByRole("button", { name: "Tắt camera" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Bật camera" })).toBeInTheDocument());
    expect(stop).toHaveBeenCalled();
    expect(landmarker.close).toHaveBeenCalled();
  });

  it("says why the camera did not start, and shows the error of the last save", async () => {
    const user = userEvent.setup();
    const { deps } = makeDeps();
    deps.openCamera.mockRejectedValue(Object.assign(new Error("denied"), { name: "NotAllowedError" }));
    render(<FaceCard title="Face symmetry" saving={false} error="Too many requests" onSave={vi.fn()} deps={deps} />);
    await user.click(screen.getByRole("button", { name: "Bật camera" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/quyền|camera/i);
    expect(screen.getByRole("button", { name: "Bật camera" })).toBeInTheDocument();
  });

  it("shows that it is saving and does not allow a second save", () => {
    const { deps } = makeDeps();
    render(<FaceCard title="Face symmetry" saving error={null} onSave={vi.fn()} deps={deps} />);
    expect(screen.getByRole("button", { name: "Đang lưu…" })).toBeDisabled();
  });
});
