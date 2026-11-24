"use client";

import { useEffect, useRef, useState } from "react";

import { RECORD_MS, useMediaRecorder } from "../hooks/useMediaRecorder";
import {
  LIVENESS_LABEL,
  LivenessAction,
  LivenessSetting,
  createLivenessChallenge,
  errorText,
} from "../lib/auth";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

// Mặc định CHỈ camera (không xin quyền micro). Bước xác minh danh tính (MFA) bật `withAudio` để quay cả tiếng.
const FACE_ONLY: MediaStreamConstraints = { video: true, audio: false };
const FACE_AND_VOICE: MediaStreamConstraints = { video: true, audio: true };

const LIVENESS_REQUIRED_ERROR = tr("khong_lay_duoc_yeu_cau_kiem");

interface Props {
  disabled?: boolean;
  /** Quay cả tiếng (chỉ dùng cho bước xác minh danh tính). Mặc định: chỉ khuôn mặt. */
  withAudio?: boolean;
  /** Kiểm tra người thật (liveness): cấu hình từ máy chủ. Bỏ qua = không dùng. */
  liveness?: LivenessSetting;
  /** `livenessToken` chỉ có khi bản quay đi kèm một thử thách liveness. */
  onRecorded: (blob: Blob, livenessToken?: string) => void;
}

export default function VideoRecord({ disabled, withAudio = false, liveness, onRecorded }: Props) {
  const [actions, setActions] = useState<LivenessAction[]>([]);
  const [step, setStep] = useState(0);
  const [preparing, setPreparing] = useState(false);
  const [livenessError, setLivenessError] = useState<string | null>(null);
  const tokenRef = useRef<string | undefined>(undefined);
  const mountedRef = useRef(true);

  const { isRecording, previewUrl, error, recordedBytes, stream, start } = useMediaRecorder({
    constraints: withAudio ? FACE_AND_VOICE : FACE_ONLY,
    onRecorded: (blob) => onRecorded(blob, tokenRef.current),
    fallbackMime: "video/webm",
  });

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Each action gets an equal share of the recording time.
  useEffect(() => {
    if (!isRecording || actions.length === 0) return;
    setStep(0);
    const timer = window.setInterval(() => setStep((value) => Math.min(value + 1, actions.length - 1)), RECORD_MS / actions.length);
    return () => window.clearInterval(timer);
  }, [isRecording, actions]);

  /** The challenge lives 60 s: fetch it right before the camera starts, never earlier. */
  async function begin() {
    tokenRef.current = undefined;
    setActions([]);
    setLivenessError(null);
    if (liveness?.liveness_enabled) {
      setPreparing(true);
      try {
        const challenge = await createLivenessChallenge();
        tokenRef.current = challenge.challenge_token;
        if (mountedRef.current) setActions(challenge.actions.filter((action) => action in LIVENESS_LABEL));
      } catch (caught) {
        if (liveness.liveness_required) {
          if (mountedRef.current) {
            setLivenessError(`${LIVENESS_REQUIRED_ERROR} (${errorText(caught)})`);
            setPreparing(false);
          }
          return;
        }
      }
      if (!mountedRef.current) return;
      setPreparing(false);
    }
    await start();
  }

  const recordingLabel = withAudio
    ? tr("dang_quay_5_giay_nhin_camera")
    : tr("dang_quay_5_giay_nhin_thang");
  const idleLabel = withAudio ? tr("quay_khuon_mat_giong_noi") : tr("quay_khuon_mat");
  const what = withAudio ? tr("hinh_va_tieng") : tr("hinh");

  // Callback ref: gắn luồng ngay khi phần tử <video> được tạo, không phụ thuộc thứ tự effect.
  const attachStream = (node: HTMLVideoElement | null) => {
    if (node) node.srcObject = stream;
  };

  const showSteps = isRecording && actions.length > 0;

  return (
    <div>
      <Button
        type="button"
        onClick={() => void begin()}
        className="w-full bg-solid-1 text-line px-4 py-2 rounded shadow font-semibold disabled:opacity-50"
        disabled={disabled || isRecording || preparing}
      >
        <span aria-hidden="true">{isRecording ? "■ " : "📹 "}</span>
        {isRecording ? recordingLabel : idleLabel}
      </Button>
      <p role="status" aria-live="polite" className="sr-only">
        {isRecording ? tr("dang_quay_what_trong_5_giay", { what }) : previewUrl ? tr("da_quay_xong_what", { what }) : ""}
      </p>
      {recordedBytes ? <span className="text-sm text-line"> {tr("da_ghi")} {Math.max(1, Math.round(recordedBytes / 1024))} KB</span> : null}
      {/* The live preview may be mirrored for comfort; the recorder always gets the raw (unmirrored) stream. */}
      {stream && (
        <div className="relative mt-2">
          <video ref={attachStream} autoPlay muted playsInline aria-label={tr("hinh_anh_camera_truc_tiep")}
                  className="w-full h-40 bg-black rounded" style={{ transform: "scaleX(-1)" }} />
          {showSteps && (
            <div data-testid="liveness-steps" aria-live="polite"
                 className="absolute inset-x-0 bottom-0 bg-black/60 text-white text-center p-2 rounded-b">
              <p className="font-bold">{tr("buoc")} {step + 1}/{actions.length}: {LIVENESS_LABEL[actions[step]]}</p>
              <ol className="text-xs">
                {actions.map((action, index) => (
                  <li key={`${action}-${index}`} aria-current={index === step ? "step" : undefined}
                      className={index === step ? "font-bold" : "opacity-70"}>
                    {index + 1}. {LIVENESS_LABEL[action]}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
      {previewUrl && !isRecording && (
        <video src={previewUrl} controls aria-label={tr("xem_lai_ban_quay_da_ghi")}
               className="w-full h-40 bg-black rounded mt-2" />
      )}
      {livenessError && <p role="alert" className="text-sm text-line mt-1">{livenessError}</p>}
      {error && <p role="alert" className="text-sm text-line mt-1">{error}</p>}
    </div>
  );
}
