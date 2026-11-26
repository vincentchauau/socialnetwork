/** One line of a ranking: a key for React, the name shown first and the value shown after it. */
export interface RankingRow {
  key: string;
  name: string;
  value: string;
}

interface RankingListProps {
  rows: RankingRow[];
  /** The class of the list, and of its name and value, so each app keeps its own look. */
  className?: string;
  nameClass?: string;
  valueClass?: string;
}

/** A ranking as a numbered-in-order list: the name, then the value (wins, chips...). The order is the order of `rows`. */
export default function RankingList({ rows, className, nameClass, valueClass }: RankingListProps) {
  return (
    <ol className={className}>
      {rows.map((row) => (
        <li key={row.key}>
          <span className={nameClass}>{row.name}</span> <span className={valueClass}>{row.value}</span>
        </li>
      ))}
    </ol>
  );
}
