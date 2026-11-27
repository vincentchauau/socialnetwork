"use client";

import { useEffect, useState, type MouseEvent, type RefObject } from "react";

import { apiFetch } from "@sn/api";
import Button from "@sn/elements/Button";
import { API, CORNER_NAMES, PeopleSample, Point, errorText, normalizedPoint } from "./lib";

interface CourtPickerProps {
  matchId: number;
  src: string;
  initial: Point[] | null;
  videoRef: RefObject<HTMLVideoElement | null>;
  /** The players at the current time of the video, or null when there is nothing to draw. */
  sample: PeopleSample | null;
  onTime: (ms: number) => void;
}

/** The video, with the court and the players drawn over it. Four corners are picked by clicks, in any order. */
export default function CourtPicker({ matchId, src, initial, videoRef, sample, onTime }: CourtPickerProps) {
  const [corners, setCorners] = useState<Point[]>(initial ?? []);
  const [picking, setPicking] = useState(false);
  const [aspect, setAspect] = useState("16 / 9");
  const [message, setMessage] = useState("");

  useEffect(() => {
    setCorners(initial ?? []);
    setPicking(false);
    setMessage("");
  }, [matchId, initial]);

  function readAspect() {
    const video = videoRef.current;
    if (video && video.videoWidth > 0 && video.videoHeight > 0) {
      setAspect(`${video.videoWidth} / ${video.videoHeight}`);
    }
  }

  function pick(event: MouseEvent<HTMLDivElement>) {
    if (corners.length >= CORNER_NAMES.length) return;
    const frame = event.currentTarget.getBoundingClientRect();
    setCorners([...corners, normalizedPoint(event.clientX, event.clientY, frame)]);
    setMessage("");
  }

  async function save() {
    try {
      await apiFetch(`${API}/matches/${matchId}/court`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corners }),
      });
      setPicking(false);
      setMessage("Court saved.");
    } catch (failure) {
      setMessage(errorText(failure));
    }
  }

  const nextName = corners.length < CORNER_NAMES.length ? CORNER_NAMES[corners.length] : null;
  // The court marked by hand wins; otherwise the court found on the frame at this time.
  const outline: Point[] | null = corners.length === CORNER_NAMES.length ? corners : (sample?.court ?? null);

  return (
    <div className="rally-frame" style={{ aspectRatio: aspect }}>
      <video
        ref={videoRef}
        className="rally-video"
        controls
        preload="metadata"
        src={src}
        onLoadedMetadata={readAspect}
        onTimeUpdate={(event) => onTime(Math.round(event.currentTarget.currentTime * 1000))}
      />
      {picking && <div className="rally-pick" onClick={pick} role="presentation" />}
      {sample && (
        <svg className="rally-players-layer" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
          {sample.people.map((person, index) => (
            <circle key={index} data-testid="player-dot" cx={person.x} cy={person.y} r={0.012} className={`player ${person.side}`}>
              <title>{person.side}</title>
            </circle>
          ))}
        </svg>
      )}
      {outline && (
        <svg className="rally-court" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
          <polygon data-testid="court-outline" points={outline.map(([x, y]) => `${x},${y}`).join(" ")} />
          {corners.map(([x, y], index) => (
            <circle key={CORNER_NAMES[index]} cx={x} cy={y} r={0.01} />
          ))}
        </svg>
      )}
      <div className="rally-court-bar">
        {!picking && <Button onClick={() => setPicking(true)}>Mark court</Button>}
        {picking && (
          <>
            <span>{nextName ? `Click the ${nextName} corner (${corners.length + 1} of 4)` : "All four corners marked."}</span>
            <Button onClick={() => setCorners([])} disabled={corners.length === 0}>Clear</Button>
            <Button variant="primary" onClick={save} disabled={corners.length !== CORNER_NAMES.length}>Save court</Button>
          </>
        )}
        {message && <span role="status">{message}</span>}
        <span className="muted">The court is found on each frame by itself; a frame with no full court view is skipped.</span>
      </div>
    </div>
  );
}
