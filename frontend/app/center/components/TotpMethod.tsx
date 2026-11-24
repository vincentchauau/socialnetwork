"use client";

import { FormEvent, useEffect, useState } from "react";

import Alert from "@sn/elements/Alert";
import SharedQrImage from "./QrImage";
import RecoveryCodesBox, { CopyButton } from "./RecoveryCodesBox";
import { digitsOnly, TOTP_LENGTH } from "./TotpLoginForm";
import { INPUT, LABEL, NOTE, PRIMARY_BUTTON, SECONDARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { useReauth } from "../hooks/useReauth";
import { TotpSetup, totpDisable, totpEnable, totpRegenerateRecoveryCodes, totpSetup } from "../lib/auth";
import Button from "@sn/elements/Button";
import { usePasswordProof } from "./PasswordConfirm";
import { tr } from "../i18n";
import TextBox from "@sn/elements/TextBox";

const TOTP_TITLE = tr("xac_thuc_hai_buoc_totp");
const TOTP_HINT = tr("ma_nay_chi_dung_lam_buoc");
const LOW_CODES_THRESHOLD = 2;

const RECOVERY_TITLE = tr("quan_ly_ma_khoi_phuc");

interface Props {
  enabled: boolean;
  recoveryCodesLeft: number;
  hasPassword: boolean;
  onDone: () => void | Promise<void>;
  /** Which tab this is: the authenticator (setup, turn off) or the recovery codes (count, make new ones). */
  part: "totp" | "recovery";
  /** The codes just made, shown once; shared by both tabs because enabling TOTP and regenerating both produce them. */
  codes: string[] | null;
  onCodes: (codes: string[] | null) => void;
}

type Done = Props["onDone"];

function QrImage({ uri }: { uri: string }) {
  return (
    <SharedQrImage value={uri} alt={tr("ma_qr_de_them_tai_khoan")}
                   failureText={tr("khong_tao_duoc_ma_qr_hay_2")} />
  );
}

function PasswordInput({ id, value, onChange }: { id: string; value: string; onChange: (value: string) => void }) {
  return (
    <>
      <label htmlFor={id} className={LABEL}>{tr("nhap_lai_mat_khau_de_xac")}</label>
      <TextBox id={id} type="password" value={value} autoComplete="current-password" required
             onChange={(e) => onChange(e.target.value)} className={INPUT} />
    </>
  );
}

/** Tắt: chưa bật thì hỏi mật khẩu (nếu có) rồi lấy khóa thiết lập. */
function StartSetup({ hasPassword, onStarted }: { hasPassword: boolean; onStarted: (setup: TotpSetup, password?: string) => void }) {
  const { password, setPassword, isShared } = usePasswordProof();
  const { busy, error, run } = useAction();
  const { withReauth, dialog } = useReauth();

  async function submit(event: FormEvent) {
    event.preventDefault();
    let started: TotpSetup | undefined;
    const sent = hasPassword ? password : undefined;
    const ok = await run(() => withReauth(async () => void (started = await totpSetup(sent))));
    setPassword("");
    if (ok && started) onStarted(started, sent);
  }

  return (
    <form onSubmit={submit} aria-label={tr("bat_xac_thuc_hai_buoc")}>
      <p className={NOTE}>{tr("dung_ung_dung_nhu_google_authenticator")}</p>
      {hasPassword && !isShared && <PasswordInput id="totp-start-password" value={password} onChange={setPassword} />}
      <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{busy ? tr("dang_xu_ly") : tr("bat")}</Button>
      <Alert className="mt-2">{error}</Alert>
      {dialog}
    </form>
  );
}

/** QR + khóa để nhập tay + ô nhập mã đầu tiên để xác nhận. */
function ConfirmSetup({ setup, password, onEnabled, onCancel }: { setup: TotpSetup; password?: string; onEnabled: (codes: string[]) => void; onCancel: () => void }) {
  const [code, setCode] = useState("");
  const { busy, error, run } = useAction();
  const { withReauth, dialog } = useReauth();

  async function submit(event: FormEvent) {
    event.preventDefault();
    let codes: string[] = [];
    if (await run(() => withReauth(async () => void (codes = (await totpEnable(code, password)).recovery_codes)))) onEnabled(codes);
    else setCode("");
  }

  return (
    <form onSubmit={submit} aria-label={tr("xac_nhan_ma_xac_thuc")}>
      <p className={NOTE}>{tr("quet_ma_qr_bang_ung_dung")}</p>
      <QrImage uri={setup.otpauth_uri} />
      <p className="text-sm mb-1">{tr("hoac_nhap_khoa_nay_thu_cong")}</p>
      <p className="font-mono text-sm break-all mb-1" aria-label={tr("khoa_thiet_lap")}>{setup.secret}</p>
      <div className="mb-2"><CopyButton text={setup.secret} label={tr("sao_chep_khoa")} /></div>
      <label htmlFor="totp-confirm-code" className={LABEL}>{tr("ma_xac_thuc_6_chu_so")}</label>
      <TextBox id="totp-confirm-code" value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={TOTP_LENGTH}
             disabled={busy} onChange={(e) => setCode(digitsOnly(e.target.value))} className={INPUT} />
      <Button type="submit" disabled={busy || code.length !== TOTP_LENGTH} className={PRIMARY_BUTTON}>
        {busy ? tr("dang_xu_ly") : tr("xac_nhan_va_bat")}
      </Button>
      <Button variant="secondary" type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>{tr("huy")}</Button>
      <Alert className="mt-2">{error}</Alert>
      {dialog}
    </form>
  );
}

interface CodeActionProps {
  label: string;
  submitLabel: string;
  hasPassword: boolean;
  send: (code: string, password?: string) => Promise<void>;
  onCancel: () => void;
}

/** Hỏi một mã hiện tại (mã ứng dụng hoặc mã khôi phục) trước khi tạo lại mã/tắt. */
function CodeAction({ label, submitLabel, hasPassword, send, onCancel }: CodeActionProps) {
  const [code, setCode] = useState("");
  const { password, setPassword, isShared } = usePasswordProof();
  const { busy, error, run, fail } = useAction();
  const { withReauth, dialog } = useReauth();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const clean = code.trim().toLowerCase();
    if (!clean) return fail(tr("hay_nhap_ma"));
    const ok = await run(() => withReauth(() => send(clean, hasPassword ? password : undefined)));
    setPassword("");
    if (!ok) setCode("");
  }

  return (
    <form onSubmit={submit} aria-label={submitLabel} className="mt-2">
      <label htmlFor="totp-action-code" className={LABEL}>{label}</label>
      <TextBox id="totp-action-code" value={code} autoComplete="one-time-code" autoCapitalize="none" spellCheck={false}
             disabled={busy} onChange={(e) => setCode(e.target.value)} className={INPUT} />
      {hasPassword && !isShared && <PasswordInput id="totp-action-password" value={password} onChange={setPassword} />}
      <Button type="submit" disabled={busy} className={PRIMARY_BUTTON}>{busy ? tr("dang_xu_ly") : submitLabel}</Button>
      <Button variant="secondary" type="button" disabled={busy} onClick={onCancel} className={`${SECONDARY_BUTTON} mt-2`}>{tr("huy")}</Button>
      <Alert className="mt-2">{error}</Alert>
      {dialog}
    </form>
  );
}

/** Turn the authenticator off: asks for a current code first. */
function TotpEnabledView({ hasPassword, onDone }: { hasPassword: boolean; onDone: Done }) {
  const [disabling, setDisabling] = useState(false);

  async function disable(code: string, password?: string) {
    await totpDisable(code, password);
    await onDone();
  }

  return (
    <>
      <p className="text-sm font-medium mb-1">{tr("trang_thai_dang_bat")}</p>
      {disabling ? (
        <CodeAction label={tr("ma_xac_thuc_hoac_ma_khoi")} submitLabel={tr("xac_nhan_tat")}
                    hasPassword={hasPassword} send={disable} onCancel={() => setDisabling(false)} />
      ) : (
        <Button variant="secondary" type="button" className={SECONDARY_BUTTON} onClick={() => setDisabling(true)}>{tr("tat")}</Button>
      )}
    </>
  );
}

interface RecoveryProps {
  left: number;
  hasPassword: boolean;
  onCodes: (codes: string[]) => void;
  onDone: Done;
}

/** How many recovery codes are left, and a way to make a new set (the old ones stop working). */
function RecoveryView({ left, hasPassword, onCodes, onDone }: RecoveryProps) {
  const [regenerating, setRegenerating] = useState(false);
  const low = left <= LOW_CODES_THRESHOLD;

  async function regenerate(code: string, password?: string) {
    const { recovery_codes } = await totpRegenerateRecoveryCodes(code, password);
    setRegenerating(false);
    onCodes(recovery_codes);
    await onDone();
  }

  return (
    <>
      <p role={low ? "alert" : undefined}
         className={low ? "text-sm font-semibold text-line bg-solid border border-line rounded p-2 mb-2" : "text-sm mb-2"}>
        {tr("con")} {left} {tr("ma_khoi_phuc_2")}{low ? tr("hay_tao_lai_ma_moi_som") : ""}
      </p>
      {regenerating ? (
        <CodeAction label={tr("ma_xac_thuc_hien_tai_ma")} submitLabel={tr("xac_nhan_tao_lai_ma")}
                    hasPassword={hasPassword} send={regenerate} onCancel={() => setRegenerating(false)} />
      ) : (
        <Button variant="secondary" type="button" className={SECONDARY_BUTTON} onClick={() => setRegenerating(true)}>{tr("tao_lai_ma_khoi_phuc")}</Button>
      )}
    </>
  );
}

/** The recovery-codes tab: the set just made (once), else the count and "make new codes". */
function RecoveryTab({ enabled, recoveryCodesLeft, hasPassword, onDone, codes, onCodes }: Omit<Props, "part">) {
  let body;
  if (codes) {
    body = <RecoveryCodesBox codes={codes} onDismiss={() => onCodes(null)} />;
  } else if (enabled) {
    body = <RecoveryView left={recoveryCodesLeft} hasPassword={hasPassword} onCodes={onCodes} onDone={onDone} />;
  } else {
    body = <p className="text-sm mb-2">{tr("bat_xac_thuc_hai_buoc_tab")}</p>;
  }
  return (
    <section aria-label={RECOVERY_TITLE} className={SECTION}>
      <h2 className="font-bold mb-1">{RECOVERY_TITLE}</h2>
      {body}
    </section>
  );
}

/** Thẻ Xác thực hai bước (tab Mã TOTP) hoặc thẻ mã khôi phục (tab Mã khôi phục), tùy `part`. */
export default function TotpMethod(props: Props) {
  const { enabled, hasPassword, onDone, onCodes, part } = props;
  const [setup, setSetup] = useState<{ data: TotpSetup; password?: string } | null>(null);
  if (part === "recovery") return <RecoveryTab {...props} />;

  let body;
  if (enabled) {
    body = <TotpEnabledView hasPassword={hasPassword} onDone={onDone} />;
  } else if (setup) {
    body = (
      <ConfirmSetup
        setup={setup.data}
        password={setup.password}
        onCancel={() => setSetup(null)}
        onEnabled={async (recovery) => {
          setSetup(null);
          onCodes(recovery);
          await onDone();
        }}
      />
    );
  } else {
    body = <StartSetup hasPassword={hasPassword} onStarted={(data, password) => setSetup({ data, password })} />;
  }

  return (
    <section aria-label={TOTP_TITLE} className={SECTION}>
      <h2 className="font-bold mb-1">{TOTP_TITLE}</h2>
      {!enabled && <p className="text-sm font-medium mb-1">{tr("trang_thai_dang_tat_mac_dinh")}</p>}
      <p className={NOTE}>{TOTP_HINT}</p>
      {body}
    </section>
  );
}
