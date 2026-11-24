"use client";

import { useEffect, useState } from "react";

import { httpErrorText as errorText } from "@sn/api";
import Button from "@sn/elements/Button";
import Select from "@sn/elements/Select";

import { listShares, makeShare, takeBackShare } from "../lib/api";
import type { ShareEntry } from "../lib/types";
import { tr } from "../i18n";

/** How long a new link lasts, in days (0: until it is taken back). */
const LASTS = [0, 7, 30];

/** The link that gives one file to anybody who has it, without a sign-in: make it, copy it, take it back. */
export default function ShareSection({ path, name, onClose }: { path: string; name: string; onClose: () => void }) {
  const [share, setShare] = useState<ShareEntry | null | undefined>(undefined);
  const [days, setDays] = useState(0);
  const [copied, setCopied] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setShare(undefined);
    setCopied(false);
    setProblem(null);
    listShares().then(
      (found) => !cancelled && setShare(found.shares.find((item) => item.path === path) ?? null),
      (failure) => {
        if (cancelled) return;
        setShare(null);
        setProblem(errorText(failure));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [path]);

  async function make() {
    setProblem(null);
    try {
      setShare(await makeShare(path, days || undefined));
      setCopied(false);
    } catch (failure) {
      setProblem(errorText(failure));
    }
  }

  async function takeBack() {
    if (!share) return;
    setProblem(null);
    try {
      await takeBackShare(share.token);
      setShare(null);
    } catch (failure) {
      setProblem(errorText(failure));
    }
  }

  async function copy() {
    if (!share) return;
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${share.page}`);
      setCopied(true);
    } catch {
      setProblem(tr("share_could_not_copy"));
    }
  }

  return (
    <section aria-label={tr("share_of_p0", { p0: name })} className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <strong>🔗 {name}</strong>
      {share === undefined ? <span role="status" className="muted">…</span> : null}
      {share ? (
        <>
          <Button type="button" size="sm" onClick={() => void copy()}>{copied ? tr("share_copied") : tr("share_copy")}</Button>
          <Button type="button" size="sm" variant="secondary" onClick={() => void takeBack()}>{tr("share_take_back")}</Button>
          {share.expiresAt ? <span className="muted">{tr("share_until_p0", { p0: new Date(share.expiresAt * 1000).toLocaleDateString() })}</span> : null}
        </>
      ) : null}
      {share === null ? (
        <>
          <Select aria-label={tr("share_lasts")} value={days} onChange={(event) => setDays(Number(event.target.value))}>
            {LASTS.map((value) => (
              <option key={value} value={value}>{value === 0 ? tr("share_forever") : tr("share_days_p0", { p0: value })}</option>
            ))}
          </Select>
          <Button type="button" size="sm" onClick={() => void make()}>{tr("share_make")}</Button>
        </>
      ) : null}
      <Button type="button" size="sm" variant="ghost" aria-label={tr("huy")} onClick={onClose}>✕</Button>
      {problem ? <span role="alert" className="error">{problem}</span> : null}
    </section>
  );
}
