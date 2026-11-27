"use client";

import type { RefObject } from "react";

import { PLAYER_COLORS, PeopleSample } from "./lib";

interface CourtPickerProps {
  src: string;
  videoRef: RefObject<HTMLVideoElement | null>;
  /** What was found on the frame at the current time, or null when nothing is known yet. */
  sample: PeopleSample | null;
  onTime: (ms: number) => void;
}

const SHUTTLE_COLOR = "#ff3b30";

/** The video with what the detector found drawn over it: the court, each player's box and label, and the shuttle. */
export default function CourtPicker({ src, videoRef, sample, onTime }: CourtPickerProps) {
  return (
    <div className="rally-frame">
      <video
        ref={videoRef}
        className="rally-video"
        controls
        preload="metadata"
        src={src}
        onTimeUpdate={(event) => onTime(Math.round(event.currentTarget.currentTime * 1000))}
      />
      {sample?.court && (
        <svg className="rally-court" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
          <polygon data-testid="court-outline" points={sample.court.map(([x, y]) => `${x},${y}`).join(" ")} />
        </svg>
      )}
      {sample?.people.map((person) => {
        const [x1, y1, x2, y2] = person.box;
        const colour = PLAYER_COLORS[person.id] ?? "#888";
        return (
          <div
            key={person.id}
            data-testid="player-box"
            className="rally-box"
            title={person.side}
            style={{ left: `${x1 * 100}%`, top: `${y1 * 100}%`, width: `${(x2 - x1) * 100}%`, height: `${(y2 - y1) * 100}%`, borderColor: colour }}
          >
            <span style={{ background: colour }}>P{person.id}</span>
          </div>
        );
      })}
      {sample?.shuttle && (
        <div
          data-testid="shuttle"
          className="rally-shuttle"
          style={{ left: `${sample.shuttle[0] * 100}%`, top: `${sample.shuttle[1] * 100}%`, borderColor: SHUTTLE_COLOR }}
        />
      )}
    </div>
  );
}
