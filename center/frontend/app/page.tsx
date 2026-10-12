"use client";

import { useEffect, useState } from "react";

import { User, loadSession } from "@sn/api";
import { APPS } from "./apps";
import Alert from "./components/Alert";
import { CARD, PRIMARY_BUTTON } from "./components/ui";
import { errorText, logout as signOut } from "./lib/auth";

type Session =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: User };

const APP_CARD = "block border rounded p-4 text-left hover:bg-gray-50 focus:outline focus:outline-2 focus:outline-blue-600";

export default function HomePage() {
  const [session, setSession] = useState<Session>({ status: "loading" });
  const [logoutError, setLogoutError] = useState<string | null>(null);

  useEffect(() => {
    loadSession()
      .then((user) => setSession(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setSession({ status: "error" }));
  }, []);

  async function logout() {
    setLogoutError(null);
    try {
      await signOut();
      setSession({ status: "anonymous" });
    } catch (caught) {
      setLogoutError(`Không đăng xuất được. ${errorText(caught)}`);
    }
  }

  if (session.status === "loading") return <p role="status" className="text-center mt-10">Đang tải...</p>;

  if (session.status === "error") {
    return (
      <main className={`${CARD} text-center`}>
        <h1 className="text-2xl font-bold mb-2">Mạng xã hội</h1>
        <Alert text="Không kết nối được tới server. Hãy thử lại." />
      </main>
    );
  }

  if (session.status === "anonymous") {
    return (
      <main className={`${CARD} text-center`}>
        <h1 className="text-2xl font-bold mb-2">Mạng xã hội</h1>
        <p className="mb-4">Đăng nhập để dùng các ứng dụng.</p>
        <a href="/login" className={`${PRIMARY_BUTTON} block text-center`}>Đăng nhập hoặc đăng ký</a>
      </main>
    );
  }

  return (
    <main className={`${CARD} text-center`}>
      <h1 className="text-2xl font-bold mb-4">Xin chào, {session.user.username}</h1>
      <nav aria-label="Ứng dụng" className="flex flex-col gap-2 mb-4">
        {APPS.map((app) => (
          <a key={app.href} href={app.href} className={APP_CARD}>
            <strong>{app.name}</strong>
            <div className="text-sm text-gray-600">{app.description}</div>
          </a>
        ))}
      </nav>
      <a href="/account" className="block w-full border px-4 py-2 rounded mb-2 text-center">Tài khoản</a>
      <button type="button" onClick={logout} className="w-full bg-gray-700 text-white px-4 py-2 rounded">
        Đăng xuất
      </button>
      <Alert text={logoutError} />
    </main>
  );
}
