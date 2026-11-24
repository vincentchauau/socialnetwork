"use client";

import type { AuthMode } from "../lib/authTabs";
import Button from "@sn/elements/Button";
import { useT } from "@sn/locales";

const MODES: readonly AuthMode[] = ["register", "login", "account"];

/** The same chip for every mode: the current one is filled, the others are plain. */
const chip = (selected: boolean) => `inline-block whitespace-nowrap rounded px-3 py-1 text-sm font-medium ${selected ? "bg-solid-2" : "bg-solid-1"}`;

interface Props {
  current: AuthMode;
  onPick: (mode: AuthMode) => void;
  /** A signed-in person only sees the update mode; a visitor sees sign up and sign in. */
  signedIn: boolean;
}

/** The modes of the one screen: a visitor switches between sign up and sign in; a signed-in person has only the update mode. */
export default function ModeSwitch({ current, onPick, signedIn }: Props) {
  const { t } = useT();
  return (
    <div role="tablist" aria-label={t("modes.aria")} className="flex flex-wrap items-center gap-2 mb-4">
      {MODES.filter((mode) => (signedIn ? mode === "account" : mode !== "account")).map((mode) => (
        <Button key={mode} type="button" role="tab" aria-selected={current === mode} onClick={() => onPick(mode)} className={chip(current === mode)}>
          {t(`modes.${mode}`)}
        </Button>
      ))}
    </div>
  );
}
