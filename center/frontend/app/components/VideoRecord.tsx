"use client";

import { useMediaRecorder } from "../hooks/useMediaRecorder";

// Một lần quay có cả hình lẫn tiếng: server lấy khuôn mặt từ khung hình và giọng nói từ âm thanh trong cùng tệp.
const CONSTRAINTS: MediaStreamConstraints = { video: true, audio: true };

interface Props {
  disabled?: boolean;
  onRecorded: (blob: Blob) => void;
}

export default function VideoRecord({ disabled, onRecorded }: Props) {
  const { isRecording, previewUrl, error, recordedBytes, stream, start } = useMediaRecorder({
    constraints: CONSTRAINTS,
    onRecorded,
    fallbackMime: "video/webm",
  });

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
        {isRecording ? "Đang quay (5 giây): nhìn camera và nói..." : "Quay khuôn mặt + giọng nói"}
      </button>
      <p role="status" aria-live="polite" className="sr-only">
        {isRecording ? "Đang quay hình và tiếng trong 5 giây" : previewUrl ? "Đã quay xong hình và tiếng" : ""}
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
