"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import { errorMessage } from "../errors";
import { tr } from "../i18n";
import { Tile } from "./CallParts";

export type CheckState = { camera: boolean; mic: boolean; share: boolean; level: number };
/** Switches one of the checks; the bar above calls it. A share starts from a click, as the browser requires. */
export type CheckHandle = { toggle: (what: keyof CheckState) => Promise<void> };
type Props = {
  onState: (state: CheckState) => void;
  /** Reports why a device could not be taken (null when there is no problem). */
  onProblem: (text: string) => void;
};

/** Why the microphone or the camera could not be taken, in words the person can act on (by the name of the error the browser gives). */
export function deviceProblem(caught: unknown, what: "mic" | "camera"): string {
  const name = caught instanceof Error ? caught.name : "";
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") return tr(what === "mic" ? "rm_mic_chan" : "rm_cam_chan");
  if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") return tr(what === "mic" ? "rm_mic_khong_co" : "rm_cam_khong_co");
  if (name === "NotReadableError" || name === "AbortError" || name === "TrackStartError") return tr(what === "mic" ? "rm_mic_dang_ban" : "rm_cam_dang_ban");
  return tr(what === "mic" ? "rm_mic_loi_khac" : "rm_cam_loi_khac", { p0: name || errorMessage(caught) });
}

const VIDEO = { width: "100%", height: "100%", objectFit: "contain", background: "var(--line)" } as const;

/**
 * Before joining: the camera and the screen share, as tiles of the call (the same Tile), with nothing sent.
 * The microphone level is reported in onState; the bar is the CallBar of the room.
 */
const MediaCheck = forwardRef<CheckHandle, Props>(function MediaCheck({ onState, onProblem }, ref) {
  const camera = useRef<HTMLVideoElement>(null);
  const shared = useRef<HTMLVideoElement>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [micOn, setMicOn] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [level, setLevel] = useState(0);

  // The camera preview: on while it is switched on; its tracks stop when it is switched off or the page closes.
  useEffect(() => {
    if (!cameraOn) return;
    let stream: MediaStream | null = null;
    let gone = false;
    navigator.mediaDevices
      .getUserMedia({ video: { aspectRatio: 4 / 3 } })
      .then((found) => {
        if (gone) {
          found.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = found;
        if (camera.current) camera.current.srcObject = found;
      })
      .catch((caught: unknown) => {
        if (!gone) onProblem(deviceProblem(caught, "camera"));
      });
    return () => {
      gone = true;
      stream?.getTracks().forEach((track) => track.stop());
      if (camera.current) camera.current.srcObject = null;
    };
  }, [cameraOn, onProblem]);

  // The microphone level: a bar that moves with the voice, from the same stream.
  useEffect(() => {
    if (!micOn) {
      setLevel(0);
      return;
    }
    let stream: MediaStream | null = null;
    let context: AudioContext | undefined;
    let frameId = 0;
    let gone = false;
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((found) => {
        if (gone) {
          found.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = found;
        context = new AudioContext();
        const analyser = context.createAnalyser();
        analyser.fftSize = 256;
        context.createMediaStreamSource(found).connect(analyser);
        const samples = new Uint8Array(analyser.fftSize);
        const tick = () => {
          analyser.getByteTimeDomainData(samples);
          let sum = 0;
          for (const value of samples) {
            const amplitude = (value - 128) / 128;
            sum += amplitude * amplitude;
          }
          setLevel(Math.min(1, Math.sqrt(sum / samples.length) * 4));
          frameId = requestAnimationFrame(tick);
        };
        tick();
      })
      .catch((caught: unknown) => {
        if (!gone) onProblem(deviceProblem(caught, "mic"));
      });
    return () => {
      gone = true;
      cancelAnimationFrame(frameId);
      stream?.getTracks().forEach((track) => track.stop());
      void context?.close();
    };
  }, [micOn, onProblem]);

  // The screen share: the picture of what would be shared, until it is stopped or the browser stops it.
  function stopShare() {
    (shared.current?.srcObject as MediaStream | null)?.getTracks().forEach((track) => track.stop());
    if (shared.current) shared.current.srcObject = null;
    setSharing(false);
  }

  async function startShare() {
    try {
      const found = await navigator.mediaDevices.getDisplayMedia({ video: true });
      if (shared.current) shared.current.srcObject = found;
      found.getVideoTracks()[0]?.addEventListener("ended", stopShare);
      setSharing(true);
    } catch (caught) {
      onProblem(caught instanceof Error ? caught.message : String(caught));
    }
  }

  useImperativeHandle(ref, () => ({
    toggle: async (what) => {
      if (what === "camera") setCameraOn((on) => !on);
      if (what === "mic") setMicOn((on) => !on);
      if (what === "share") {
        if (sharing) stopShare();
        else await startShare();
      }
    },
  }));

  useEffect(() => {
    onState({ camera: cameraOn, mic: micOn, share: sharing, level });
  }, [cameraOn, micOn, sharing, level, onState]);

  useEffect(() => () => stopShare(), []); // eslint-disable-line react-hooks/exhaustive-deps

  // The tiles only: the caller puts them in the same grid as the call.
  return (
    <>
      {cameraOn && (
        <Tile focused={false} name={tr("rm_ban")}>
          <video ref={camera} autoPlay playsInline muted style={{ ...VIDEO, transform: "scaleX(-1)" }} />
        </Tile>
      )}
      {sharing && (
        <Tile focused={false} name={tr("rm_man_hinh")}>
          <video ref={shared} autoPlay playsInline muted style={VIDEO} />
        </Tile>
      )}
    </>
  );
});

export default MediaCheck;
