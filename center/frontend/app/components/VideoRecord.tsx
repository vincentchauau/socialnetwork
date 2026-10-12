"use client";

import { useMediaRecorder } from "../hooks/useMediaRecorder";

// Mặc định CHỈ camera (không xin quyền micro). Bước xác minh danh tính (MFA) bật `withAudio` để quay cả tiếng.
const FACE_ONLY: MediaStreamConstraints = { video: true, audio: false };
const FACE_AND_VOICE: MediaStreamConstraints = { video: true, audio: true };

interface Props {
  disabled?: boolean;
  /** Quay cả tiếng (chỉ dùng cho bước xác minh danh tính). Mặc định: chỉ khuôn mặt. */
  withAudio?: boolean;
  onRecorded: (blob: Blob) => void;
}

export default function VideoRecord({ disabled, withAudio = false, onRecorded }: Props) {
  const { isRecording, previewUrl, error, recordedBytes, stream, start } = useMediaRecorder({
    constraints: withAudio ? FACE_AND_VOICE : FACE_ONLY,
    onRecorded,
    fallbackMime: "video/webm",
  });

  const recordingLabel = withAudio
    ? "Đang quay (5 giây): nhìn camera và nói..."
    : "Đang quay (5 giây): nhìn thẳng vào camera...";
  const idleLabel = withAudio ? "Quay khuôn mặt + giọng nói" : "Quay khuôn mặt";
  const what = withAudio ? "hình và tiếng" : "hình";

  // Callback ref: gắn luồng ngay khi phần tử <video> được tạo, không phụ thuộc thứ tự effect.
  const attachStream = (node: HTMLVideoElement | null) => {
    if (node) node.srcObject = stream;
  };

  return (
    <div>
      <button
        type="button"
        onClick={start}
        className="w-full bg-green-600 text-white px-4 py-2 rounded shadow font-semibold disabled:opacity-50"
        disabled={disabled || isRecording}
      >
        <span aria-hidden="true">{isRecording ? "■ " : "📹 "}</span>
        {isRecording ? recordingLabel : idleLabel}
      </button>
      <p role="status" aria-live="polite" className="sr-only">
        {isRecording ? `Đang quay ${what} trong 5 giây` : previewUrl ? `Đã quay xong ${what}` : ""}
      </p>
      {recordedBytes ? <span className="text-sm text-gray-600"> Đã ghi {Math.max(1, Math.round(recordedBytes / 1024))} KB</span> : null}
      {stream && (
        <video ref={attachStream} autoPlay muted playsInline aria-label="Hình ảnh camera trực tiếp"
               className="w-full h-40 bg-black rounded mt-2" />
      )}
      {previewUrl && !isRecording && (
        <video src={previewUrl} controls aria-label="Xem lại bản quay đã ghi"
               className="w-full h-40 bg-black rounded mt-2" />
      )}
      {error && <p role="alert" className="text-sm text-red-600 mt-1">{error}</p>}
    </div>
  );
}
