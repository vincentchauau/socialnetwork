"use client";

import { useCallback, useEffect, useState } from "react";

import Alert from "./Alert";
import BiometricLoginToggle from "./BiometricLoginToggle";
import DeleteAccount from "./DeleteAccount";
import EnrollBiometrics from "./EnrollBiometrics";
import LinkGoogle from "./LinkGoogle";
import PasswordForm from "./PasswordForm";
import RemoveBiometrics from "./RemoveBiometrics";
import { CARD, PRIMARY_BUTTON, SECTION } from "./ui";
import { useAction } from "../hooks/useAction";
import { AuthConfig, Me, errorText, getAuthConfig, loadMe, logout } from "../lib/auth";
import { goTo } from "../lib/navigate";

type State = { status: "loading" } | { status: "error"; text: string } | { status: "ready"; me: Me };

const NO_CONFIG: AuthConfig = { google_client_id: null, biometrics_enabled: false };

export default function AccountView() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [config, setConfig] = useState<AuthConfig>(NO_CONFIG);
  const signOut = useAction();

  const reload = useCallback(async () => {
    try {
      const me = await loadMe();
      if (!me) return goTo("/login?next=/account");
      setState({ status: "ready", me });
    } catch (caught) {
      setState({ status: "error", text: errorText(caught) });
    }
  }, []);

  useEffect(() => {
    void reload();
    getAuthConfig().then(setConfig).catch(() => setConfig(NO_CONFIG));
  }, [reload]);

  if (state.status === "loading") return <p role="status" className="text-center mt-10">Đang tải...</p>;
  if (state.status === "error") {
    return (
      <main className={CARD}>
        <h1 className="text-2xl font-bold mb-4">Tài khoản</h1>
        <Alert text={state.text} />
        <button type="button" onClick={() => void reload()} className={`${PRIMARY_BUTTON} mt-2`}>
          Thử lại
        </button>
      </main>
    );
  }

  const { me } = state;
  const hasBoth = me.has_audio && me.has_face;

  return (
    <main className={`${CARD} text-center`}>
      <p className="text-left mb-4">
        <a href="/" className="text-blue-700 underline">Về trang chủ</a>
      </p>
      <h1 className="text-2xl font-bold mb-2">Xin chào, {me.username}</h1>
      <p className="mb-1">Vai trò: {me.role}</p>
      <p className="mb-1 text-sm text-gray-600">Email: {me.email ?? "chưa có"}</p>
      <p className="mb-4 text-sm text-gray-600">
        Giọng nói: {me.has_audio ? "đã đăng ký" : "chưa"} · Khuôn mặt: {me.has_face ? "đã đăng ký" : "chưa"}
      </p>

      <PasswordForm hasPassword={me.has_password} onDone={reload} />

      {config.google_client_id && !me.google_linked && (
        <LinkGoogle clientId={config.google_client_id} hasPassword={me.has_password} onDone={reload} />
      )}

      {config.biometrics_enabled && (
        <>
          <EnrollBiometrics hasPassword={me.has_password} hasAudio={me.has_audio} hasFace={me.has_face} onDone={reload} />
          {hasBoth && <BiometricLoginToggle enabled={me.biometric_login} hasPassword={me.has_password} onDone={reload} />}
          {(me.has_audio || me.has_face) && <RemoveBiometrics hasPassword={me.has_password} onDone={reload} />}
        </>
      )}

      <section aria-label="Phiên đăng nhập" className={SECTION}>
        <h2 className="font-bold mb-2">Phiên đăng nhập</h2>
        <button
          type="button"
          disabled={signOut.busy}
          className="w-full bg-gray-700 text-white px-4 py-2 rounded disabled:opacity-50"
          onClick={async () => {
            if (await signOut.run(logout)) goTo("/login");
          }}
        >
          Đăng xuất mọi nơi
        </button>
        <Alert text={signOut.error} />
      </section>

      <DeleteAccount hasPassword={me.has_password} />
    </main>
  );
}
