"use client";

import { useEffect, useState, type MouseEvent, type RefObject } from "react";

import { apiFetch } from "@sn/api";
import Button from "@sn/elements/Button";
import { API, CORNER_NAMES, Point, errorText, normalizedPoint } from "./lib";

interface CourtPickerProps {
  matchId: number;
  src: string;
  initial: Point[] | null;
  videoRef: RefObject<HTMLVideoElement | null>;
}

/** The video, with the court drawn over it: four corners are picked by clicks in the order of CORNER_NAMES. */
export default function CourtPicker({ matchId, src, initial, videoRef }: CourtPickerProps) {
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

  return (
    <div className="rally-frame" style={{ aspectRatio: aspect }}>
      <video
        ref={videoRef}
        className="rally-video"
        controls
        preload="metadata"
        src={src}
        onLoadedMetadata={readAspect}
      />
      {picking && <div className="rally-pick" onClick={pick} role="presentation" />}
      {corners.length > 0 && (
        <svg className="rally-court" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
          {corners.length === CORNER_NAMES.length && (
            <polygon points={corners.map(([x, y]) => `${x},${y}`).join(" ")} />
          )}
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
      </div>
    </div>
  );
}
