"use client";

import AudioRecord from "./AudioRecord";
import VideoRecord from "./VideoRecord";
import type { LivenessSetting } from "../lib/auth";

interface Props {
  disabled?: boolean;
  liveness?: LivenessSetting;
  onVideo: (blob: Blob, livenessToken?: string) => void;
  onAudio: (blob: Blob) => void;
}

/** Video (face + voice) recorder with an optional voice-only fallback. Remount with a new `key` to clear. */
export default function BiometricCapture({ disabled, liveness, onVideo, onAudio }: Props) {
  return (
    <>
      <div className="mb-2">
        <VideoRecord withAudio disabled={disabled} liveness={liveness} onRecorded={onVideo} />
      </div>
      <details className="mb-2">
        <summary className="cursor-pointer text-sm text-gray-700">Không quay được tiếng? Ghi giọng nói riêng</summary>
        <div className="mt-2">
          <AudioRecord disabled={disabled} onRecorded={onAudio} />
        </div>
      </details>
    </>
  );
}
