"use client";

import { FormEvent, useState } from "react";

import { CENTER_API, User, apiFetch } from "@sn/api";

type Mode = "login" | "register";

export default function LoginPage() {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch<User>(`${CENTER_API}/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      window.location.assign("/");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <h1>{mode === "login" ? "Sign in" : "Create account"}</h1>
      <input
        aria-label="Username"
        placeholder="Username (3-32 letters, digits, _)"
        autoComplete="username"
        value={username}
        onChange={(event) => setUsername(event.target.value)}
        required
      />
      <input
        aria-label="Password"
        type="password"
        placeholder="Password (min 8 characters)"
        autoComplete={mode === "login" ? "current-password" : "new-password"}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button disabled={busy}>{mode === "login" ? "Sign in" : "Register"}</button>
      <button
        type="button"
        className="secondary"
        onClick={() => setMode(mode === "login" ? "register" : "login")}
      >
        {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
      </button>
    </form>
  );
}
