"use client";

import { useMediaRecorder } from "../hooks/useMediaRecorder";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

const CONSTRAINTS: MediaStreamConstraints = { audio: true };

interface Props {
  disabled?: boolean;
  onRecorded: (blob: Blob) => void;
}

export default function AudioRecord({ disabled, onRecorded }: Props) {
  const { isRecording, previewUrl, error, recordedBytes, start } = useMediaRecorder({
    constraints: CONSTRAINTS,
    onRecorded,
    fallbackMime: "audio/webm",
  });
  return (
    <div>
      <Button
        type="button"
        onClick={start}
        className="w-full bg-solid-1 text-line px-4 py-2 rounded shadow font-semibold disabled:opacity-50"
        disabled={disabled || isRecording}
      >
        <span aria-hidden="true">{isRecording ? "■ " : "🎤 "}</span>
        {isRecording ? tr("dang_ghi_5_giay") : tr("ghi_giong_noi")}
      </Button>
      <p role="status" aria-live="polite" className="sr-only">
        {isRecording ? tr("dang_ghi_am_trong_5_giay") : previewUrl ? tr("da_ghi_xong_giong_noi") : ""}
      </p>
      {recordedBytes ? <span className="text-sm text-line"> {tr("da_ghi")} {Math.max(1, Math.round(recordedBytes / 1024))} KB</span> : null}
      {previewUrl && <audio src={previewUrl} controls aria-label={tr("nghe_lai_giong_noi_da_ghi")} className="w-full mt-2" />}
      {error && <p role="alert" className="text-sm text-line mt-1">{error}</p>}
    </div>
  );
}
