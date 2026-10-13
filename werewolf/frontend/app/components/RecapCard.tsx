import { useEffect, useRef, useState } from "react";

import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { Recap } from "../lib/types";

export const RECAP_SHOW_MS = 6_000;

const KIND = {
  dawn: { icon: "🌅", title: "Bình minh", unit: "Ngày" },
  dusk: { icon: "🌇", title: "Hoàng hôn", unit: "Đêm" },
} as const;

/** Who just died: shown whenever `seq` changes (not for the card already there on arrival); hides itself or on click. */
export default function RecapCard({ recap }: { recap: Recap | null }) {
  const [shown, setShown] = useState<Recap | null>(null);
  const seen = useRef<number | null>(null);
  const seq = recap?.seq ?? null;

  useEffect(() => {
    if (!recap) return undefined;
    if (seen.current === null) {
      seen.current = recap.seq; // first render: do not replay an old card
      return undefined;
    }
    if (seen.current === recap.seq) return undefined;
    seen.current = recap.seq;
    setShown(recap);
    const id = setTimeout(() => setShown(null), RECAP_SHOW_MS);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new seq starts a card
  }, [seq]);

  if (!shown) return null;
  const kind = KIND[shown.kind];
  return (
    <section className={`ww-recap ww-recap-${shown.kind} card`} aria-label={`${kind.title}, ${kind.unit} ${shown.round}`}>
      <button type="button" className="secondary ww-recap-close" onClick={() => setShown(null)} aria-label="Ẩn thẻ tóm tắt">
        ✕
      </button>
      <h2>
        <span aria-hidden="true">{kind.icon}</span> {kind.title} · {kind.unit} {shown.round}
      </h2>
      {shown.deaths.length === 0 ? (
        <p>🕊️ Không ai chết.</p>
      ) : (
        <ul className="ww-plain-list">
          {shown.deaths.map((death) => (
            <li key={death.id}>
              💀 <strong>{death.name}</strong> đã chết <span className="muted">[{death.cause}]</span>
              {death.revealed && (
                <div className="muted">
                  📢 Lộ diện: {FACTION_ICON[death.revealed.faction.code]} {death.revealed.faction.label} ·{" "}
                  {abilityIcon(death.revealed.ability.code)} {death.revealed.ability.label}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
