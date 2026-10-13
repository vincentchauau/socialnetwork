"use client";

import { useEffect, useRef, useState } from "react";

import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import { abilityIcon } from "../lib/theme";
import type { SetupMeta } from "../lib/types";

/** "❓ Luật": rules, abilities and event cards, loaded from /setup/meta so they always match the server. */
export default function HelpSheet({ meta }: { meta?: SetupMeta | null }) {
  const [isOpen, setOpen] = useState(false);
  const [loaded, setLoaded] = useState<SetupMeta | null>(meta ?? null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (meta) setLoaded(meta);
  }, [meta]);

  useEffect(() => {
    if (!isOpen || loaded) return;
    let cancelled = false;
    werewolfApi
      .meta()
      .then((value) => !cancelled && setLoaded(value))
      .catch((e: unknown) => !cancelled && setError(errorText(e)));
    return () => {
      cancelled = true;
    };
  }, [isOpen, loaded]);

  useEffect(() => {
    if (isOpen) closeRef.current?.focus();
  }, [isOpen]);

  const close = () => {
    setOpen(false);
    openerRef.current?.focus();
  };

  return (
    <>
      <button ref={openerRef} type="button" className="secondary" onClick={() => setOpen(true)} aria-haspopup="dialog">
        ❓ Luật
      </button>
      {isOpen && (
        <div
          className="ww-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ww-help-title"
          onKeyDown={(event) => event.key === "Escape" && close()}
        >
          <div className="ww-sheet">
            <h2 id="ww-help-title">❓ Luật chơi</h2>
            {!loaded && !error && <p className="muted">Đang tải…</p>}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            {loaded?.help.rules.map((rule) => (
              <section key={rule.title} className="card">
                <h3>
                  {rule.icon} {rule.title}
                </h3>
                <p>{rule.text}</p>
              </section>
            ))}
            {loaded && (
              <section className="card">
                <h3>🧰 Chức năng</h3>
                <dl>
                  {loaded.abilities.map((ability) => (
                    <div key={ability.code} className="ww-def">
                      <dt>
                        {abilityIcon(ability.code)} {ability.label}
                      </dt>
                      <dd className="muted">{ability.help}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
            {loaded && (
              <section className="card">
                <h3>🎴 Thẻ sự kiện</h3>
                <dl>
                  {loaded.help.events.map((event) => (
                    <div key={event.code} className="ww-def">
                      <dt>
                        {event.icon} {event.title}
                      </dt>
                      <dd className="muted">{event.text}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
            <button ref={closeRef} type="button" onClick={close}>
              Đóng
            </button>
          </div>
        </div>
      )}
    </>
  );
}
