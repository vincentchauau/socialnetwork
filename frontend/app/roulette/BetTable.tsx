"use client";

import { BetKind, betKey, colourOf, hits, splitPick } from "./lib";
import { tr } from "./i18n";

interface Props {
  placed: Readonly<Record<string, number>>;
  winner: number | null;
  disabled: boolean;
  onPlace: (key: string) => void;
}

const NUMBERS = Array.from({ length: 36 }, (_, index) => index + 1);
// The table has three rows: the top one holds 3, 6, 9 ... 36, the bottom one 1, 4, 7 ... 34.
const ROWS = [0, 2, 1].map((remainder) => NUMBERS.filter((number) => number % 3 === remainder));

/**
 * The betting table: the numbers, the columns under them, and the even-money bets: a click puts the chosen chip on a place.
 * The bets on more than one number lie on the lines between the numbers: the edge of a cell (split), its corner (four numbers),
 * the top of a cell (a row of three, or two rows).
 */
export default function BetTable({ placed, winner, disabled, onPlace }: Props) {
  const shown = (kind: BetKind, pick: number | null) => winner !== null && hits(kind, pick, winner);

  const place = (kind: BetKind, pick: number | null, text: string, className: string, label?: string) => {
    const key = betKey(kind, pick);
    const stake = placed[key];
    return (
      <button
        key={key}
        type="button"
        className={`cell ${className}${shown(kind, pick) ? " winner" : ""}`}
        disabled={disabled}
        aria-label={`${tr("bet_on")} ${label ?? text}${stake ? ` (${stake})` : ""}`}
        onClick={() => onPlace(key)}
      >
        {text}
        {stake ? <span className="stake" aria-hidden="true">{stake}</span> : null}
      </button>
    );
  };

  /** A small place on a line or at a corner, over the cell it belongs to. */
  const hit = (kind: BetKind, pick: number, where: string, label: string) => {
    const key = betKey(kind, pick);
    const stake = placed[key];
    return (
      <button
        key={key}
        type="button"
        className={`hit ${where}${stake ? " has-stake" : ""}${shown(kind, pick) ? " winner" : ""}`}
        disabled={disabled}
        aria-label={`${tr("bet_on")} ${tr(kind)} ${label}${stake ? ` (${stake})` : ""}`}
        onClick={() => onPlace(key)}
      >
        {stake ? <span className="stake" aria-hidden="true">{stake}</span> : null}
      </button>
    );
  };

  const numberCell = (number: number, rowIndex: number) => {
    const isTop = rowIndex === 0;
    const isBottom = rowIndex === 2;
    const isLastColumn = number >= 34;
    const right = number + 3;
    const below = number - 1; // the cell under it, in the same column
    return (
      <div key={`n${number}`} className="slot">
        {place("straight", number, String(number), colourOf(number))}
        {!isLastColumn ? hit("split", splitPick(number, right), "r", `${number}/${right}`) : null}
        {!isBottom ? hit("split", splitPick(below, number), "b", `${below}/${number}`) : null}
        {!isBottom && !isLastColumn ? hit("corner", below, "c", `${below}, ${number}, ${right - 1}, ${right}`) : null}
        {isTop ? hit("street", number - 2, "t", `${number - 2}–${number}`) : null}
        {isTop && !isLastColumn ? hit("line", number - 2, "tc", `${number - 2}–${right}`) : null}
        {number <= 3 ? hit("split", number, "l", `0/${number}`) : null}
      </div>
    );
  };

  return (
    <div className="table" role="group" aria-label={tr("table")}>
      {place("straight", 0, "0", "green zero")}
      {ROWS.map((row, rowIndex) => [
        ...row.map((number) => numberCell(number, rowIndex)),
        place("column", 3 - rowIndex, "2:1", "outside", `${tr("column")} ${3 - rowIndex}`),
      ])}
      <span />
      {[1, 2, 3].map((dozen) => place("dozen", dozen, tr(`dozen_${dozen}`), "outside span4"))}
      <span />
      <span />
      {place("low", null, tr("low"), "outside span2")}
      {place("even", null, tr("even"), "outside span2")}
      {place("red", null, tr("red"), "red span2")}
      {place("black", null, tr("black"), "black span2")}
      {place("odd", null, tr("odd"), "outside span2")}
      {place("high", null, tr("high"), "outside span2")}
      <span />
    </div>
  );
}
