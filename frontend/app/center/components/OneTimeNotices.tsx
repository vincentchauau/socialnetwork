"use client";

import { useEffect, useRef, useState } from "react";

import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import { takeNewUsername, takeVerificationEmail } from "../lib/auth";
import { takeProfileUnsaved } from "../lib/profile";

type Notices = { username: string | null; email: string | null; profile: boolean };

/**
 * What the last sign-up left to say on the next screen: the username made for the person, the address the confirmation mail went to,
 * and a profile that did not save. Each is read (and so removed) once, then shown until the person closes it.
 */
export default function OneTimeNotices() {
  // Read on the page, not during render (the server has no session storage). A ref keeps the first reading: the reads remove the notices.
  const taken = useRef<Notices | null>(null);
  const [notices, setNotices] = useState<Notices | null>(null);
  const [closed, setClosed] = useState<Set<keyof Notices>>(() => new Set());

  useEffect(() => {
    taken.current ??= { username: takeNewUsername(), email: takeVerificationEmail(), profile: takeProfileUnsaved() };
    setNotices(taken.current);
  }, []);

  if (!notices) return null;
  const shown: { key: keyof Notices; text: string }[] = [];
  if (notices.username && !closed.has("username")) shown.push({ key: "username", text: tr("notice_new_username", { p0: notices.username }) });
  if (notices.email && !closed.has("email")) shown.push({ key: "email", text: tr("notice_verify_email", { p0: notices.email }) });
  if (notices.profile && !closed.has("profile")) shown.push({ key: "profile", text: tr("notice_profile_unsaved") });
  if (shown.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, margin: "8px 0" }}>
      {shown.map(({ key, text }) => (
        <div key={key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Alert tone="info" style={{ flex: 1 }}>{text}</Alert>
          <Button type="button" size="sm" variant="ghost" onClick={() => setClosed((current) => new Set(current).add(key))}>
            {tr("notice_close")}
          </Button>
        </div>
      ))}
    </div>
  );
}
