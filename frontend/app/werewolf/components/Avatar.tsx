import { animalFor } from "../lib/theme";

interface Props {
  name: string;
  size?: number;
  tone?: string;
  badge?: string;
  dead?: boolean;
}

/** Decorative: the name is always written next to it. */
export default function Avatar({ name, size = 54, tone, badge, dead = false }: Props) {
  const style = { width: size, height: size, fontSize: size * 0.55 } as const;
  const className = `ww-avatar${tone ? ` ww-tone-${tone}` : ""}${dead ? " ww-dead" : ""}`;
  return (
    <span className={className} style={style} aria-hidden="true">
      {dead ? "💀" : animalFor(name)}
      {badge && <span className="ww-avatar-badge">{badge}</span>}
    </span>
  );
}
