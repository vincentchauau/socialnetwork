import type { NightEvent } from "../lib/types";

/** Random event card of the current night (and the following day when it affects it). */
export default function EventBanner({ event }: { event: NightEvent | null }) {
  if (!event) return null;
  return (
    <section className="ww-event card" aria-label={`Sự kiện: ${event.title}. ${event.text}`}>
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
