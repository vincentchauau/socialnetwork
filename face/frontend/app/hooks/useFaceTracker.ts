"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import { drawFaceOverlay } from "../lib/draw";
import { cameraErrorMessage } from "../lib/errors";
import { computeScores, toPixels } from "../lib/geometry";
import type { FaceDeps, Landmarker } from "../lib/mediapipe";
import { averageScores, pushWindow } from "../lib/smoothing";
import type { Landmark, Scores } from "../lib/types";

export type TrackerStatus = "idle" | "starting" | "running";

/** Frames without a face before the smoothed scores are dropped (avoids flicker on a single miss). */
export const MISS_TOLERANCE = 5;
const ANALYSIS_ERROR = "Không phân tích được hình ảnh từ camera. Hãy bật lại camera.";

interface Session {
  stream: MediaStream | null;
  landmarker: Landmarker | null;
  raf: number | null;
  window: Scores[];
  misses: number;
}

const emptySession = (): Session => ({ stream: null, landmarker: null, raf: null, window: [], misses: 0 });
const sameScores = (a: Scores | null, b: Scores | null) => JSON.stringify(a) === JSON.stringify(b);

export interface FaceTracker {
  videoRef: RefObject<HTMLVideoElement | null>;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  status: TrackerStatus;
  error: string | null;
  /** Moving-average scores; null while no face is tracked. */
  scores: Scores | null;
  start: () => Promise<void>;
  stop: () => void;
}

export function useFaceTracker(deps: FaceDeps, drawEnabled: boolean): FaceTracker {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const session = useRef<Session>(emptySession());
  const runId = useRef(0);
  const statusRef = useRef<TrackerStatus>("idle");
  const drawRef = useRef(drawEnabled);
  drawRef.current = drawEnabled;

  const [status, setStatusState] = useState<TrackerStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [scores, setScores] = useState<Scores | null>(null);

  const setStatus = useCallback((next: TrackerStatus) => {
    statusRef.current = next;
    setStatusState(next);
  }, []);

  /** Releases camera, model and loop. Safe to call repeatedly and on unmount. */
  const teardown = useCallback(() => {
    const s = session.current;
    if (s.raf !== null) cancelAnimationFrame(s.raf);
    s.stream?.getTracks().forEach((track) => track.stop());
    s.landmarker?.close();
    const video = videoRef.current;
    if (video) video.srcObject = null;
    const canvas = canvasRef.current;
    canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    session.current = emptySession();
  }, []);

  const handleFrame = useCallback((video: HTMLVideoElement, landmarks: Landmark[] | null) => {
    const w = video.videoWidth;
    const h = video.videoHeight;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (canvas && ctx) {
      if (canvas.width !== w) canvas.width = w;
      if (canvas.height !== h) canvas.height = h;
      ctx.drawImage(video, 0, 0, w, h);
      if (landmarks && drawRef.current) drawFaceOverlay(ctx, toPixels(landmarks, w, h));
    }
    const s = session.current;
    const raw = landmarks ? computeScores(landmarks, w, h) : null;
    if (raw) {
      s.window = pushWindow(s.window, raw);
      s.misses = 0;
    } else if (++s.misses >= MISS_TOLERANCE) {
      s.window = [];
    } else {
      return; // keep showing the last smoothed values for a few frames
    }
    const next = averageScores(s.window);
    setScores((prev) => (sameScores(prev, next) ? prev : next));
  }, []);

  const halt = useCallback((message: string | null) => {
    runId.current += 1;
    teardown();
    setScores(null);
    setError(message);
    setStatus("idle");
  }, [setStatus, teardown]);

  const step = useCallback(async (id: number) => {
    if (runId.current !== id) return;
    const video = videoRef.current;
    const landmarker = session.current.landmarker;
    if (video && landmarker && video.readyState >= 2) {
      try {
        const landmarks = await landmarker.detect(video);
        if (runId.current !== id) return;
        handleFrame(video, landmarks);
      } catch {
        if (runId.current === id) halt(ANALYSIS_ERROR);
        return;
      }
    }
    if (runId.current === id) session.current.raf = requestAnimationFrame(() => void step(id));
  }, [halt, handleFrame]);

  const start = useCallback(async () => {
    if (statusRef.current !== "idle") return;
    const id = ++runId.current;
    setStatus("starting");
    setError(null);
    let stream: MediaStream | null = null;
    let landmarker: Landmarker | null = null;
    try {
      stream = await deps.openCamera();
      if (runId.current !== id) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const video = videoRef.current;
      if (video) {
        video.srcObject = stream;
        await video.play().catch(() => undefined); // autoplay is also set; a rejected play() is not fatal
      }
      landmarker = await deps.createLandmarker();
      if (runId.current !== id) {
        landmarker.close();
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
    } catch (e) {
      stream?.getTracks().forEach((track) => track.stop());
      if (runId.current === id) {
        runId.current += 1;
        teardown();
        setError(cameraErrorMessage(e));
        setStatus("idle");
      }
      return;
    }
    session.current = { ...emptySession(), stream, landmarker };
    setStatus("running");
    void step(id);
  }, [deps, setStatus, step, teardown]);

  const stop = useCallback(() => halt(null), [halt]);

  useEffect(() => () => {
    runId.current += 1;
    teardown();
  }, [teardown]);

  return { videoRef, canvasRef, status, error, scores, start, stop };
}
