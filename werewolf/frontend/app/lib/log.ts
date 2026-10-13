import type { LogEntry } from "./types";

export interface LogGroup {
  round: string;
  lines: string[];
}

const MAX_ROUNDS = 12;

/** Groups the log per night/day: newest group first, lines inside a group in the order they happened. */
export function groupLog(log: LogEntry[]): LogGroup[] {
  const groups: LogGroup[] = [];
  for (const entry of log) {
    const last = groups[groups.length - 1];
    if (last && last.round === entry.round) {
      groups[groups.length - 1] = { round: last.round, lines: [...last.lines, entry.text] };
    } else {
      groups.push({ round: entry.round, lines: [entry.text] });
    }
  }
  return groups.reverse().slice(0, MAX_ROUNDS);
}
