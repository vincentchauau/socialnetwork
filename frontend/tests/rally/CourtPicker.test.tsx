import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import CourtPicker from "../../app/rally/CourtPicker";
import type { PeopleSample, Point } from "../../app/rally/lib";

const COURT: Point[] = [[0.1, 0.9], [0.9, 0.9], [0.7, 0.2], [0.3, 0.2]];
const SAMPLE: PeopleSample = {
  t_ms: 500,
  court: COURT,
  shuttle: [0.5, 0.4],
  people: [
    { id: 1, side: "near-left", x: 0.3, y: 0.8, box: [0.2, 0.6, 0.4, 0.8], x_m: 1, y_m: 2, score: 0.9 },
    { id: 2, side: "far-right", x: 0.6, y: 0.4, box: [0.55, 0.3, 0.65, 0.4], x_m: 4, y_m: 10, score: 0.8 },
  ],
};

function renderPicker(sample: PeopleSample | null) {
  const videoRef = createRef<HTMLVideoElement>();
  return render(<CourtPicker src="/video" videoRef={videoRef} sample={sample} onTime={vi.fn()} />);
}

describe("CourtPicker: what the detector found is drawn over the video", () => {
  it("draws the court found on the frame", () => {
    renderPicker(SAMPLE);

    expect(screen.getByTestId("court-outline")).toBeInTheDocument();
  });

  it("draws a box and a label for each player on the court", () => {
    renderPicker(SAMPLE);

    expect(screen.getAllByTestId("player-box")).toHaveLength(2);
    expect(screen.getByText("P1")).toBeInTheDocument();
    expect(screen.getByText("P2")).toBeInTheDocument();
  });

  it("draws the shuttle where it was found", () => {
    renderPicker(SAMPLE);

    expect(screen.getByTestId("shuttle")).toBeInTheDocument();
  });

  it("draws nothing extra when there is no sample for this time", () => {
    renderPicker(null);

    expect(screen.queryByTestId("court-outline")).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("player-box")).toHaveLength(0);
    expect(screen.queryByTestId("shuttle")).not.toBeInTheDocument();
  });

  it("draws no shuttle when the shuttle is not seen on this frame", () => {
    renderPicker({ ...SAMPLE, shuttle: null });

    expect(screen.queryByTestId("shuttle")).not.toBeInTheDocument();
  });
});
