"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { useAccountChange } from "./AccountChanges";
import Alert from "@sn/elements/Alert";
import ApplyButton from "./ApplyButton";
import ProfileFields from "./ProfileFields";
import { PRIMARY_BUTTON } from "./ui";
import { useAction } from "../hooks/useAction";
import { errorText } from "../lib/auth";
import { type Draft, ProfileProblem, draftOf, getProfile, hasChanges, patchOf, saveProfile } from "../lib/profile";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

/** The profile of the account, in the account page, as a closed bar like the one of the sign-up form: saved by the page's one button (or Enter), like every other form. */
export default function ProfileSection() {
  const [initial, setInitial] = useState<Draft | null>(null);
  const [draft, setDraft] = useState<Draft>(() => draftOf(null));
  const [loadError, setLoadError] = useState<string | null>(null);
  const { busy, error, message, run, fail } = useAction();

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const next = draftOf(await getProfile());
      setInitial(next);
      setDraft(next);
    } catch (caught) {
      setLoadError(errorText(caught));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const dirty = initial !== null && hasChanges(draft, initial);

  /** Same code for the form's own button and for the page's "Đổi tài khoản": true when the profile was saved. */
  async function apply(): Promise<boolean> {
    if (!initial) return false;
    let patch: Record<string, unknown>;
    try {
      patch = patchOf(draft, initial);
    } catch (caught) {
      fail(caught instanceof ProfileProblem ? caught.message : errorText(caught));
      return false;
    }
    return run(async () => {
      if (Object.keys(patch).length > 0) {
        const saved = draftOf(await saveProfile(patch));
        setInitial(saved);
        setDraft(saved);
      }
      return tr("pf_da_luu_ho_so");
    });
  }

  useAccountChange("cach-profile", tr("pf_ho_so"), dirty, apply);

  function submit(event: FormEvent) {
    event.preventDefault();
    void apply();
  }

  return (
    <details className="border rounded p-2 mb-4">
      <summary className="font-medium cursor-pointer">{tr("pf_ho_so")}</summary>
      <form onSubmit={submit} aria-label={tr("pf_ho_so")} className="mt-2">
        {loadError ? (
          <>
            <Alert className="mt-2">{loadError}</Alert>
            <Button type="button" onClick={() => void load()} className={`${PRIMARY_BUTTON} mt-2`}>{tr("thu_lai")}</Button>
          </>
        ) : initial === null ? (
          <p role="status" className="text-sm">{tr("dang_tai")}</p>
        ) : (
          <fieldset disabled={busy} className="border-0 p-0 m-0">
            <ProfileFields draft={draft} onChange={setDraft} />
            <ApplyButton className={PRIMARY_BUTTON}>{busy ? tr("dang_luu") : tr("pf_luu_ho_so")}</ApplyButton>
          </fieldset>
        )}
        <Alert className="mt-2">{error}</Alert>
        <Alert tone="success" className="mt-2">{message}</Alert>
      </form>
    </details>
  );
}
