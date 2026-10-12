"use client";

import { FormEvent, useState } from "react";

import Alert from "./Alert";
import AudioRecord from "./AudioRecord";
import BiometricWarning from "./BiometricWarning";
import VideoRecord from "./VideoRecord";
import { INPUT, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { MethodsStatus, removeVoice, removeWebcam, saveVoice, saveWebcam } from "../lib/auth";

export type BiometricKind = "voice" | "webcam";

interface Props {
  kind: BiometricKind;
  enabled: boolean;
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
}

const TEXT = {
  voice: {
    name: "giọng nói",
    add: "Lưu giọng nói",
    replace: "Thay giọng nói",
    remove: "Hủy giọng nói",
    missing: "Hãy ghi giọng nói trước khi lưu",
    saved: "Đã lưu giọng nói.",
    removed: "Đã hủy đăng nhập bằng giọng nói.",
  },
  webcam: {
    name: "webcam",
    add: "Lưu webcam",
    replace: "Thay webcam",
    remove: "Hủy webcam",
    missing: "Hãy quay webcam trước khi lưu",
    saved: "Đã lưu webcam.",
    removed: "Đã hủy đăng nhập bằng webcam.",
  },
} as const;

/** Thêm, thay hoặc hủy MỘT cách đăng nhập sinh trắc (giọng nói hoặc webcam); nhập lại mật khẩu nếu tài khoản có. */
export default function BiometricMethod({ kind, enabled, hasPassword, onDone }: Props) {
  const text = TEXT[kind];
  const [blob, setBlob] = useState<Blob>();
  const [password, setPassword] = useState("");
  const [recordingKey, setRecordingKey] = useState(0);
  const { busy, error, message, run, fail } = useAction();

  const reset = () => {
    setBlob(undefined);
    setPassword("");
    setRecordingKey((key) => key + 1); // xóa bản xem trước cũ
  };
  const proof = hasPassword ? password : undefined;

  async function act(action: () => Promise<MethodsStatus>, done: string) {
    if (hasPassword && !password) return fail("Hãy nhập mật khẩu để xác nhận");
    if (await run(async () => { await action(); return done; })) {
      reset();
      await onDone();
    }
  }

  function save(event: FormEvent) {
    event.preventDefault();
    if (!blob) return fail(text.missing);
    void act(() => (kind === "voice" ? saveVoice(blob, proof) : saveWebcam(blob, proof)), text.saved);
  }

  const remove = () => void act(() => (kind === "voice" ? removeVoice(proof) : removeWebcam(proof)), text.removed);

  return (
    <form onSubmit={save} aria-label={`Đăng nhập bằng ${text.name}`} className="mt-2">
      <BiometricWarning />
      {kind === "voice" ? (
        <AudioRecord key={recordingKey} disabled={busy} onRecorded={setBlob} />
      ) : (
        <VideoRecord key={recordingKey} disabled={busy} onRecorded={setBlob} />
      )}
      {hasPassword && (
        <>
          <label htmlFor={`${kind}-password`} className={`${LABEL} mt-2`}>Nhập lại mật khẩu để xác nhận</label>
          <input id={`${kind}-password`} type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <button type="submit" disabled={busy} className={`${PRIMARY_BUTTON} mt-2`}>
        {busy ? "Đang lưu..." : enabled ? text.replace : text.add}
      </button>
      {enabled && (
        <button type="button" disabled={busy} onClick={remove} className={`${SECONDARY_BUTTON} mt-2`}>
          {text.remove}
        </button>
      )}
      <Alert text={error} />
      <Alert text={message} ok />
    </form>
  );
}
