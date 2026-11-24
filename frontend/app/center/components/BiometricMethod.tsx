"use client";

import { FormEvent, useState } from "react";

import { useAccountChange } from "./AccountChanges";
import Alert from "@sn/elements/Alert";
import ApplyButton from "./ApplyButton";
import AudioRecord from "./AudioRecord";
import BiometricWarning from "./BiometricWarning";
import VideoRecord from "./VideoRecord";
import { INPUT, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { LivenessSetting, MethodsStatus, removeVoice, removeWebcam, saveVoice, saveWebcam } from "../lib/auth";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

type BiometricKind = "voice" | "webcam";

interface Props {
  kind: BiometricKind;
  enabled: boolean;
  hasPassword: boolean;
  liveness?: LivenessSetting;
  onDone: () => void | Promise<void>;
}

const TEXT = {
  voice: {
    get name() { return tr("giong_noi_2"); },
    get add() { return tr("luu_giong_noi"); },
    get replace() { return tr("thay_giong_noi"); },
    get remove() { return tr("huy_giong_noi"); },
    get missing() { return tr("hay_ghi_giong_noi_truoc_khi_2"); },
    get saved() { return tr("da_luu_giong_noi"); },
    get removed() { return tr("da_huy_dang_nhap_bang_giong"); },
  },
  webcam: {
    get name() { return tr("webcam_khuon_mat_2"); },
    get add() { return tr("luu_webcam"); },
    replace: "Thay webcam",
    get remove() { return tr("huy_webcam"); },
    get missing() { return tr("hay_quay_khuon_mat_truoc_khi_2"); },
    get saved() { return tr("da_luu_webcam"); },
    get removed() { return tr("da_huy_dang_nhap_bang_webcam"); },
  },
} as const;

/** Thêm, thay hoặc hủy MỘT cách đăng nhập sinh trắc (giọng nói hoặc webcam); nhập lại mật khẩu nếu tài khoản có. */
export default function BiometricMethod({ kind, enabled, hasPassword, liveness, onDone }: Props) {
  const text = TEXT[kind];
  const [blob, setBlob] = useState<Blob>();
  const [livenessToken, setLivenessToken] = useState<string>();
  const { password, setPassword, isShared } = usePasswordProof();
  const [recordingKey, setRecordingKey] = useState(0);
  const { busy, error, message, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();

  const reset = () => {
    setBlob(undefined);
    setLivenessToken(undefined);
    setPassword("");
    setRecordingKey((key) => key + 1); // xóa bản xem trước cũ
  };
  const proof = hasPassword ? password : undefined;

  async function act(action: () => Promise<MethodsStatus>, done: string): Promise<boolean> {
    if (hasPassword && !password) {
      fail(tr("hay_nhap_mat_khau_de_xac"));
      return false;
    }
    if (!(await run(async () => { await withReauth(action); return done; }))) return false;
    reset();
    await onDone();
    return true;
  }

  /** Same code for the form's own button and for the page's "Đổi tài khoản": true when the sample was saved. */
  async function apply(): Promise<boolean> {
    if (!blob) {
      fail(text.missing);
      return false;
    }
    return act(() => (kind === "voice" ? saveVoice(blob, proof) : saveWebcam(blob, proof, livenessToken)), text.saved);
  }

  useAccountChange(`cach-${kind}`, kind === "voice" ? tr("giong_noi") : tr("webcam_khuon_mat"), blob !== undefined, apply);

  function save(event: FormEvent) {
    event.preventDefault();
    void apply();
  }

  const remove = () => void act(() => (kind === "voice" ? removeVoice(proof) : removeWebcam(proof)), text.removed);

  return (
    <form onSubmit={save} aria-label={tr("dang_nhap_bang_p0", { p0: text.name })} className="mt-2">
      <BiometricWarning kinds={[kind]} />
      {kind === "voice" ? (
        <AudioRecord key={recordingKey} disabled={busy} onRecorded={setBlob} />
      ) : (
        <VideoRecord
          key={recordingKey}
          disabled={busy}
          liveness={liveness}
          onRecorded={(video, token) => {
            setBlob(video);
            setLivenessToken(token);
          }}
        />
      )}
      {hasPassword && !isShared && (
        <>
          <label htmlFor={`${kind}-password`} className={`${LABEL} mt-2`}>{tr("nhap_lai_mat_khau_de_xac")}</label>
          <TextBox id={`${kind}-password`} type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} className={INPUT} />
        </>
      )}
      <ApplyButton disabled={busy} className={`${PRIMARY_BUTTON} mt-2`}>
        {busy ? tr("dang_luu") : enabled ? text.replace : text.add}
      </ApplyButton>
      {enabled && (
        <Button variant="secondary" type="button" disabled={busy} onClick={remove} className={`${SECONDARY_BUTTON} mt-2`}>
          {text.remove}
        </Button>
      )}
      <Alert className="mt-2">{error}</Alert>
      <Alert tone="success" className="mt-2">{message}</Alert>
      {dialog}
    </form>
  );
}
