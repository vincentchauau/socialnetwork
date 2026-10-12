"use client";

import { useMediaRecorder } from "../hooks/useMediaRecorder";

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
      <button
        type="button"
        onClick={start}
        className="w-full bg-green-600 text-white px-4 py-2 rounded shadow font-semibold disabled:opacity-50"
        disabled={disabled || isRecording}
      >
        <span aria-hidden="true">{isRecording ? "■ " : "🎤 "}</span>
        {isRecording ? "Đang ghi (5 giây)..." : "Ghi giọng nói"}
      </button>
      <p role="status" aria-live="polite" className="sr-only">
        {isRecording ? "Đang ghi âm trong 5 giây" : previewUrl ? "Đã ghi xong giọng nói" : ""}
      </p>
      {recordedBytes ? <span className="text-sm text-gray-600"> Đã ghi {Math.max(1, Math.round(recordedBytes / 1024))} KB</span> : null}
      {previewUrl && <audio src={previewUrl} controls aria-label="Nghe lại giọng nói đã ghi" className="w-full mt-2" />}
      {error && <p role="alert" className="text-sm text-red-600 mt-1">{error}</p>}
    </div>
  );
}
