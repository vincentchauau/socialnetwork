"use client";

import { type FormEvent, useState } from "react";

import { REPORT_REASONS, type ReportReason } from "../api";
import { errorMessage } from "../errors";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import Card from "@sn/elements/Card";
import Select from "@sn/elements/Select";
import TextBox from "@sn/elements/TextBox";
import { BG, FG } from "@sn/lib/theme";
import { tr } from "../i18n";

export const REASON_TEXT: Record<ReportReason, () => string> = {
  spam: () => tr("sc_rd_spam"),
  abuse: () => tr("sc_rd_abuse"),
  impersonation: () => tr("sc_rd_impersonation"),
  illegal: () => tr("sc_rd_illegal"),
  other: () => tr("sc_rd_other"),
};

interface Props {
  /** Says what is reported (a message of someone): shown over the form. */
  about: string;
  /** Sends the report; a rejection says why not (shown in the form). */
  onSend: (reason: ReportReason, details: string) => Promise<void>;
  onClose: () => void;
}

/** The form of a report (a reason and what is wrong), in a dialog over the page; the same words as the report of a person. */
export default function ReportDialog({ about, onSend, onClose }: Props) {
  const [reason, setReason] = useState<ReportReason>("spam");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSend(reason, details);
      onClose();
    } catch (caught) {
      setError(errorMessage(caught));
      setBusy(false);
    }
  }

  return (
    <div
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: 12, background: "color-mix(in srgb, var(--line) 45%, transparent)" }}
    >
      <form onSubmit={(event) => void submit(event)} role="dialog" aria-modal="true" aria-label={tr("sc_bao_cao")} noValidate style={{ width: "100%", maxWidth: 480 }}>
        <Card stack style={{ background: BG, color: FG }}>
          <h3 style={{ margin: 0 }}>{tr("sc_bao_cao")}</h3>
          <p className="muted" style={{ margin: 0 }}>{about}</p>
          <label>{tr("sc_ly_do")}
            <Select value={reason} onChange={(event) => setReason(event.target.value as ReportReason)}>
              {REPORT_REASONS.map((value) => <option key={value} value={value}>{REASON_TEXT[value]()}</option>)}
            </Select>
          </label>
          <label>{tr("sc_chi_tiet")}
            <TextBox multiline rows={3} maxLength={500} value={details} onChange={(event) => setDetails(event.target.value)} />
          </label>
          {error ? <Alert>{error}</Alert> : null}
          <div style={{ display: "flex", gap: 8 }}>
            <Button type="submit" disabled={busy}>{tr("sc_gui_bao_cao")}</Button>
            <Button type="button" variant="secondary" onClick={onClose}>{tr("rm_huy")}</Button>
          </div>
        </Card>
      </form>
    </div>
  );
}
