"use client";

import type { CSSProperties, ReactNode } from "react";

import Button from "../elements/Button";
import { SearchBox, type SearchTerms } from "../compounds/InputBox";
import TextBox from "../elements/TextBox";
import { crudTr as tr } from "../compounds/crudModel";

export interface BulkAction {
  key: string;
  label: string;
  /** Hurting actions (kick, ban, delete) are `danger`, the gentle ones `primary` or `secondary`: the same on every table. */
  variant: "primary" | "secondary" | "danger";
  onClick: () => void;
  disabled?: boolean;
}

interface Props {
  /** What the table is of ("rooms", "members", "messages"): names the toolbar for people who cannot see it. */
  name: string;
  searchLabel: string;
  query: string;
  onQuery: (query: string) => void;
  /** The button that makes a new one (left out where nothing is made from here). */
  createLabel?: string;
  onCreate?: () => void;
  creating?: boolean;
  /** How many rows are picked in the table: the actions on them show up when it is more than none. */
  pickedCount: number;
  bulk: BulkAction[];
  /** What else belongs to the bar (a list to choose from). */
  children?: ReactNode;
  /** Enter in the search box searches at once (the words typed are also searched for after a short wait). */
  onSearch?: () => void;
  /** The box of the Table pane: words and `column:value` terms, kept as chips; with it `query` and `onQuery` are not used. */
  search?: SearchTerms;
  extra?: ReactNode;
  controlStyle?: CSSProperties;
}

/**
 * The same bar over every table of the chat: Search, Create, and with some rows picked, how many and what can be done to all of them.
 * What can be done to one row is on the row, in the table.
 */
export default function CrudToolbar({ name, searchLabel, query, onQuery, createLabel, onCreate, creating = false, pickedCount, bulk, children, onSearch, search, extra, controlStyle }: Props) {
  return (
    <div className="stack cw-toolbar" role="toolbar" aria-label={name} style={{ gap: 6 }}>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        {search ? (
          <SearchBox search={search} controlStyle={controlStyle ?? {}} />
        ) : (
          <TextBox type="search" value={query} maxLength={80} autoComplete="off" aria-label={searchLabel} placeholder={searchLabel} onChange={(event) => onQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") onSearch?.(); }} style={{ flex: "1 1 160px", minWidth: 0, ...controlStyle }} />
        )}
        {onCreate && createLabel && (
          <Button type="button" size={controlStyle ? "md" : "sm"} style={controlStyle} variant={creating ? "primary" : "secondary"} aria-pressed={creating} onClick={onCreate}>
            {createLabel}
          </Button>
        )}
        {extra}
      </div>
      {children}
      {pickedCount > 0 && bulk.length > 0 && (
        <div className="row" style={{ gap: 6, flexWrap: "wrap", alignItems: "center" }} role="group" aria-label={tr("bulk_actions")}>
          <span className="cw-room-sub" role="status">{tr("picked_count", { p0: pickedCount })}</span>
          {bulk.map((action) => (
            <Button key={action.key} type="button" size="sm" variant={action.variant} disabled={action.disabled} onClick={action.onClick}>
              {action.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
