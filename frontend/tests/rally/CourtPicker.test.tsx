import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@sn/api";
import CourtPicker from "../../app/rally/CourtPicker";
import type { PeopleSample, Point } from "../../app/rally/lib";

vi.mock("@sn/api", () => ({
  apiFetch: vi.fn(),
  apiForm: vi.fn(),
  errorText: (error: unknown) => String(error),
}));

const COURT: Point[] = [[0.1, 0.9], [0.9, 0.9], [0.7, 0.2], [0.3, 0.2]];
const SAMPLE: PeopleSample = {
  t_ms: 500,
  court: COURT,
  people: [
    { id: 1, side: "near-left", x: 0.3, y: 0.8, x_m: 1, y_m: 2, score: 0.9 },
    { id: 2, side: "far-right", x: 0.6, y: 0.4, x_m: 4, y_m: 10, score: 0.8 },
  ],
};

function renderPicker(sample: PeopleSample | null, onTime = vi.fn()) {
  const videoRef = createRef<HTMLVideoElement>();
  return render(
    <CourtPicker matchId={7} src="/video" initial={null} videoRef={videoRef} sample={sample} onTime={onTime} />,
  );
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
  // jsdom has no layout: give the overlay a 100 x 100 box so clicks map to 0..1 easily.
  Element.prototype.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
});

describe("CourtPicker: the court and the players are found by themselves", () => {
  it("draws the court found on the frame, without any click", () => {
    renderPicker(SAMPLE);

    expect(screen.getByTestId("court-outline")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save court" })).not.toBeInTheDocument();
  });

  it("draws one ring for each player on the court at this time", () => {
    renderPicker(SAMPLE);

    expect(screen.getAllByTestId("player-ring")).toHaveLength(2);
  });

  it("labels each ring with the player's label, P1 to P4", () => {
    renderPicker(SAMPLE);

    expect(screen.getByText("P1")).toBeInTheDocument();
    expect(screen.getByText("P2")).toBeInTheDocument();
  });

  it("draws no players when there is no sample for this time", () => {
    renderPicker(null);

    expect(screen.queryAllByTestId("player-ring")).toHaveLength(0);
    expect(screen.queryByTestId("court-outline")).not.toBeInTheDocument();
  });

  it("says that the court is found on each frame, so no manual step is needed", () => {
    renderPicker(SAMPLE);

    expect(screen.getByText(/found on each frame by itself/)).toBeInTheDocument();
  });
});

describe("CourtPicker: a court marked by hand overrides the found one", () => {
  it("saves four clicked corners in any order", async () => {
    vi.mocked(apiFetch).mockResolvedValue({});
    const { container } = renderPicker(null);

    fireEvent.click(screen.getByRole("button", { name: "Mark court" }));
    const overlay = container.querySelector(".rally-pick") as HTMLElement;
    fireEvent.click(overlay, { clientX: 80, clientY: 90 });
    fireEvent.click(overlay, { clientX: 20, clientY: 90 });
    fireEvent.click(overlay, { clientX: 40, clientY: 20 });
    fireEvent.click(overlay, { clientX: 60, clientY: 20 });
    fireEvent.click(screen.getByRole("button", { name: "Save court" }));

    await screen.findByText("Court saved.");
    expect(apiFetch).toHaveBeenCalledWith(
      "/api/rally/matches/7/court",
      expect.objectContaining({ method: "PUT" }),
    );
    const body = JSON.parse(vi.mocked(apiFetch).mock.calls[0][1]?.body as string);
    expect(body.corners).toEqual([[0.8, 0.9], [0.2, 0.9], [0.4, 0.2], [0.6, 0.2]]);
  });
});
