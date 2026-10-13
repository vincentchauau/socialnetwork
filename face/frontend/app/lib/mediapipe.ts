import type { FaceMesh, Results } from "@mediapipe/face_mesh";

import type { Landmark } from "./types";

/** Runtime files are copied from node_modules into public/mediapipe by scripts/copy-mediapipe.mjs. */
export const MEDIAPIPE_BASE = "/face/mediapipe";
const SCRIPT_URL = `${MEDIAPIPE_BASE}/face_mesh.js`;

/** Finds landmarks for one video frame; implemented by MediaPipe, faked in tests. */
export interface Landmarker {
  detect(video: HTMLVideoElement): Promise<Landmark[] | null>;
  close(): void;
}

/** Everything the camera loop needs from the outside world. */
export interface FaceDeps {
  openCamera(): Promise<MediaStream>;
  createLandmarker(): Promise<Landmarker>;
}

type FaceMeshCtor = new (config: { locateFile: (file: string) => string }) => FaceMesh;
type MediaPipeWindow = Window & { FaceMesh?: FaceMeshCtor };

function namedError(name: string, message: string): Error {
  const error = new Error(message);
  error.name = name;
  return error;
}

let scriptPromise: Promise<FaceMeshCtor> | null = null;

/** Loads the self-hosted face_mesh.js (a classic script that defines window.FaceMesh). */
export function loadFaceMeshScript(): Promise<FaceMeshCtor> {
  const win = window as MediaPipeWindow;
  if (win.FaceMesh) return Promise.resolve(win.FaceMesh);
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<FaceMeshCtor>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_URL;
    script.async = true;
    script.onload = () => {
      if (win.FaceMesh) resolve(win.FaceMesh);
      else reject(namedError("ModelLoadError", "FaceMesh missing after script load"));
    };
    script.onerror = () => reject(namedError("ModelLoadError", "Cannot load face_mesh.js"));
    document.head.appendChild(script);
  }).catch((error: unknown) => {
    scriptPromise = null; // allow a retry
    throw error;
  });
  return scriptPromise;
}

export async function createMediaPipeLandmarker(): Promise<Landmarker> {
  const Ctor = await loadFaceMeshScript();
  const mesh = new Ctor({ locateFile: (file) => `${MEDIAPIPE_BASE}/${file}` });
  let pending: ((landmarks: Landmark[] | null) => void) | null = null;
  mesh.setOptions({ maxNumFaces: 1, refineLandmarks: false, minDetectionConfidence: 0.5, minTrackingConfidence: 0.5 });
  const emit = (value: Landmark[] | null) => {
    const resolve = pending;
    pending = null;
    resolve?.(value);
  };
  mesh.onResults((results: Results) => emit(results.multiFaceLandmarks?.[0] ?? null));
  try {
    await mesh.initialize();
  } catch {
    throw namedError("ModelLoadError", "FaceMesh initialisation failed");
  }
  return {
    detect: (video) =>
      new Promise<Landmark[] | null>((resolve, reject) => {
        pending = resolve;
        mesh
          .send({ image: video })
          .then(() => emit(null)) // no-op when onResults already answered
          .catch(reject);
      }),
    close: () => {
      void mesh.close();
    },
  };
}

export async function openUserCamera(): Promise<MediaStream> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw namedError("UnsupportedError", "getUserMedia unavailable");
  }
  return navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
}

export const defaultFaceDeps: FaceDeps = {
  openCamera: openUserCamera,
  createLandmarker: createMediaPipeLandmarker,
};
