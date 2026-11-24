import { tr } from "./i18n";
import { splitPick } from "./lib";
import type { BetKind } from "./lib";

/** A bet in words: `17`, `Chia đôi 5/6`, `Hàng ba 4–6`, `Đỏ`. */
export function betLabel(kind: BetKind, pick: number | null): string {
  if (kind === "straight") return String(pick);
  if (pick === null) return tr(kind);
  switch (kind) {
    case "split": {
      const low = Math.floor(pick / 100);
      return `${tr("split")} ${low}/${pick % 100}`;
    }
    case "street": return `${tr("street")} ${pick}–${pick + 2}`;
    case "corner": return `${tr("corner")} ${pick}, ${pick + 1}, ${pick + 3}, ${pick + 4}`;
    case "line": return `${tr("line")} ${pick}–${pick + 5}`;
    case "dozen": return tr(`dozen_${pick}`);
    default: return `${tr(kind)} ${pick}`;
  }
}

;
