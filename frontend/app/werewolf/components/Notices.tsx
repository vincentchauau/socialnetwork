"use client";

import type { NightEvent } from "../lib/types";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";

/** Error/notice toast: announced to screen readers, closable with the keyboard. */
export function Toast({ message, onClose }: { message: string | null; onClose: () => void }) {
  return (
    <div className="ww-toast-slot">
      {message && (
        <div className="ww-toast" role="alert">
          <span>{message}</span>
          <Button variant="secondary" type="button" className="secondary" onClick={onClose} aria-label={tr("dong_thong_bao")}>
            ✕
          </Button>
        </div>
      )}
    </div>
  );
}

/** Random event card of the current night (and the following day when it affects it). */
export function EventBanner({ event }: { event: NightEvent | null }) {
  if (!event) return null;
  return (
    <section className="ww-event card" aria-label={tr("su_kien_p0_p1", { p0: event.title, p1: event.text })}>
      <span className="ww-big" aria-hidden="true">
        {event.icon}
      </span>
      <div>
        <strong>🎴 {event.title}</strong>
        <p className="muted">{event.text}</p>
      </div>
    </section>
  );
}
