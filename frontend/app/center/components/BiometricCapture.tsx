"use client";

import AudioRecord from "./AudioRecord";
import VideoRecord from "./VideoRecord";
import type { LivenessSetting } from "../lib/auth";
import { tr } from "../i18n";

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
        <summary className="cursor-pointer text-sm text-line">{tr("khong_quay_duoc_tieng_ghi_giong")}</summary>
        <div className="mt-2">
          <AudioRecord disabled={disabled} onRecorded={onAudio} />
        </div>
      </details>
    </>
  );
}
