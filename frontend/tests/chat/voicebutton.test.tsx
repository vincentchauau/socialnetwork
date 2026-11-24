import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VoiceButton, { decimate } from "../../app/chat/components/VoiceButton";

describe("decimate", () => {
  it("brings the sound down to about 16 kHz by averaging groups of samples", () => {
    const loud = new Float32Array(48000).fill(0.5); // one second at 48 kHz
    const out = decimate(loud, 48000);
    expect(out.rate).toBe(16000);
    expect(out.pcm).toHaveLength(16000);
    expect(out.pcm[0]).toBeCloseTo(16383, -1);
  });

  it("keeps a rate that is already about right", () => {
    const out = decimate(new Float32Array(16000), 16000);
    expect(out.rate).toBe(16000);
    expect(out.pcm).toHaveLength(16000);
  });
});

describe("the Voice button", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("says why the microphone cannot be taken, in words the person can act on", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: vi.fn().mockRejectedValue(Object.assign(new Error("denied"), { name: "NotAllowedError" })) },
      configurable: true,
    });
    render(<VoiceButton slug="g" disabled={false} />);
    await userEvent.click(screen.getByRole("button", { name: /Voice/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Voice/ })).toBeEnabled(); // it can be tried again
  });

  it("cannot be pressed where nothing can be sent (muted, closed)", () => {
    render(<VoiceButton slug="g" disabled />);
    expect(screen.getByRole("button", { name: /Voice/ })).toBeDisabled();
  });
});
