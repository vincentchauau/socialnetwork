"use client";

import { useEffect, useState } from "react";

import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import { abilityIcon } from "../lib/theme";
import type { SetupMeta } from "../lib/types";
import { tr } from "../i18n";

/** The rules, the abilities and the event cards, loaded from /setup/meta so they always match the server. Shown in a table or in the lobby. */
export default function RulesContent({ meta }: { meta?: SetupMeta | null }) {
  const [loaded, setLoaded] = useState<SetupMeta | null>(meta ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (meta) setLoaded(meta);
  }, [meta]);

  useEffect(() => {
    if (loaded) return;
    let cancelled = false;
    werewolfApi
      .meta()
      .then((value) => !cancelled && setLoaded(value))
      .catch((e: unknown) => !cancelled && setError(errorText(e)));
    return () => {
      cancelled = true;
    };
  }, [loaded]);

  return (
    <>
      {!loaded && !error && <p className="muted">{tr("dang_tai")}</p>}
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
          <h3>{tr("chuc_nang")}</h3>
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
          <h3>{tr("the_su_kien")}</h3>
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
    </>
  );
}
