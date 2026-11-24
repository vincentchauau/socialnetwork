"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import CardMessage from "./CardMessage";
import ReportDialog from "./ReportDialog";
import RowDialog from "./RowDialog";
import { PageBar, SelectAllBar, usePaging } from "./TableControls";
import RowMore from "./RowMore";
import { MESSAGE_TABLE, messageRow } from "./rowTables";
import DataTable, { type Column, type Key } from "@sn/compounds/DataTable";
import { socialApi } from "../api";
import { type ChatMessage, type SystemLine, buildTimeline, changeText, systemText } from "../protocol";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import { intlLocale } from "@sn/lib/i18n";

const BOTTOM_TOLERANCE_PX = 40;
/** Who says the lines about the room, where a person's name stands for what they wrote. */
const SYSTEM = "system";

interface Props {
  messages: ChatMessage[];
  system: SystemLine[];
  myId: number;
  hasOlder: boolean;
  onLoadOlder: () => void;
  onReply: (message: ChatMessage) => void;
  /** The sender changes the words of a text message (left out where that is not offered); a rejected promise keeps the box open. */
  onEdit?: (message: ChatMessage, content: string) => Promise<void> | void;
  /** The messages that are picked (only a sender picks their own: they are the ones that can be deleted). */
  picked?: ReadonlySet<Key>;
  onPicked?: (picked: ReadonlySet<Key>) => void;
  /** Only read: no box and no actions on the messages (a room I am no longer in). */
  readOnly?: boolean;
  /** The newest message I had read when I came: a line is drawn before the first one after it. */
  readUpTo?: number;
  /** The columns shown (all of them when left out). */
  shown?: ReadonlySet<string>;
  /** The owner (or a moderator) removes the messages of anyone; the others remove only their own. */
  canModerate?: boolean;
  /** Pin the message, or take the pin off (any member does: left out where that is not offered). */
  onPin?: (message: ChatMessage) => void;
  /** Remove the message from its row (after asking): the sender's own, or anyone's for the owner. */
  onRemove?: (message: ChatMessage) => void;
  /** The room the messages are of (the cards answer to it). */
  slug?: string;
}

type Row = { key: string; kind: "message"; message: ChatMessage } | { key: string; kind: "line"; line: SystemLine };

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString(intlLocale(), { hour: "2-digit", minute: "2-digit" });
}

const dayOf = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(intlLocale(), { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
};

/** The columns of the table of messages, for the Columns menu. */
export const MESSAGE_COLUMNS = [
  { key: "time", label: tr("rm_luc") },
  { key: "from", label: tr("rm_nguoi_gui") },
  { key: "what", label: tr("rm_noi_dung") },
];

const NOTHING = new Set<Key>();
const IGNORE = (): void => undefined;

/**
 * The conversation as the same table as the rooms and the members: the time, who said it, what was said (with what it answers, and whether it was
 * changed), and Reply and Edit on the messages. A message is picked (to be deleted) only by the one who sent it; the lines about the room are said
 * by `system`, and nobody sent those.
 */
export default function MessageList({ messages, system, myId, hasOlder, onLoadOlder, onReply, onEdit, picked = NOTHING, onPicked = IGNORE, readOnly = false, readUpTo = 0, slug = "", canModerate = false, onPin, onRemove, shown }: Props) {
  const rows = useMemo<Row[]>(
    () => buildTimeline(messages, system).map((item) => (item.kind === "message" ? { key: item.key, kind: "message", message: item.message } : { key: item.key, kind: "line", line: item.line })),
    [messages, system],
  );
  const byId = useMemo(() => new Map(messages.map((message) => [message.id, message])), [messages]);
  const logRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const [editing, setEditing] = useState<ChatMessage | null>(null);
  const [reporting, setReporting] = useState<ChatMessage | null>(null);
  const [reported, setReported] = useState<ReadonlyMap<number, number>>(new Map());  // message -> my open report of it, which I can take back

  // The reports I made of messages that nobody has looked at yet: asked once, for the Unreport button.
  useEffect(() => {
    let current = true;
    void (async () => {
      try {
        const mine = await socialApi.myReports();
        if (current) setReported(new Map(mine.filter((row) => row.target_type === "message").map((row) => [Number(row.target_id), row.id])));
      } catch {
        // the button of Report stays: taking back is a help, not worth an error
      }
    })();
    return () => {
      current = false;
    };
  }, [slug]);

  async function takeBack(message: ChatMessage) {
    const id = reported.get(message.id);
    if (id === undefined) return;
    try {
      await socialApi.unreport(id);
    } catch {
      return; // looked at already (or gone): the button stays as it was
    }
    setReported((previous) => new Map([...previous].filter(([key]) => key !== message.id)));
  }

  function handleScroll() {
    const el = logRef.current;
    if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_TOLERANCE_PX;
  }

  // Follow new content only when the reader is already at the bottom.
  useLayoutEffect(() => {
    const el = logRef.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [rows]);

  // The first message of someone else after the one I had read (with something read before it): "Unread messages" goes there.
  const firstUnread = readUpTo > 0 ? messages.find((message) => message.id > readUpTo && message.user_id !== myId && message.kind !== "system") : undefined;
  const showUnread = firstUnread !== undefined && messages.some((message) => message.id <= readUpTo);
  const timeOf = (row: Row) => (row.kind === "message" ? row.message.created_at : row.line.at);
  const dayBefore = (row: Row) => {
    const index = rows.indexOf(row);
    const day = dayOf(timeOf(row));
    return day && (index === 0 || dayOf(timeOf(rows[index - 1])) !== day) ? day : "";
  };
  const mine = (message: ChatMessage) => message.user_id === myId && message.kind === "text";

  const columns: Column<Row>[] = [
    { key: "time", label: tr("rm_luc"), narrow: true, sortValue: (row) => timeOf(row), render: (row) => <time dateTime={timeOf(row)}>{formatTime(timeOf(row))}</time> },
    { key: "from", label: tr("rm_nguoi_gui"), narrow: true, sortValue: (row) => (row.kind === "line" || row.message.kind === "system" ? SYSTEM : row.message.username), render: (row) => (row.kind === "line" || row.message.kind === "system" ? SYSTEM : row.message.username) },
    {
      key: "what",
      label: tr("rm_noi_dung"),
      sortValue: (row) => (row.kind === "line" ? systemText(row.line) : row.message.kind === "system" ? changeText(row.message.content) : row.message.content),
      render: (row) => {
        if (row.kind === "line") return <span className="cw-system">{systemText(row.line)}</span>;
        const { message } = row;
        if (message.kind === "system") return <span className="cw-system">{changeText(message.content)}</span>;
        const quoted = message.reply_to_id !== null ? byId.get(message.reply_to_id) : undefined;
        return (
          <>
            {message.reply_to_id !== null && <div className="cw-quote">{quoted ? `${quoted.username}: ${quoted.content}` : tr("rm_tin_nhan_goc")}</div>}
            {message.kind === "card" ? (
              <CardMessage message={message} slug={slug} myId={myId} />
            ) : (
              <span>{message.content}</span>
            )}
            {message.edited_at && <span className="muted"> ({tr("rm_da_sua")})</span>}
            {message.pinned_at && <span role="img" aria-label={tr("rm_da_ghim")}> 📌</span>}
          </>
        );
      },
    },
  ];

  // newest first: page 1 is the latest messages, "next" goes back in time
  const paging = usePaging(rows.length);
  const end = rows.length - paging.offset;
  const visible = rows.slice(Math.max(0, end - paging.pageSize), end);

  return (
    <div ref={logRef} className="cw-log" role="log" aria-live="polite" aria-relevant="additions" aria-label={tr("tin_nhan")} tabIndex={0} onScroll={handleScroll}>
      {hasOlder && end <= paging.pageSize && (
        <Button type="button" size="sm" variant="secondary" className="cw-older" onClick={onLoadOlder}>
          {tr("rm_xem_tin_cu_hon")}
        </Button>
      )}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        {!readOnly && (
        <SelectAllBar
          keys={visible.flatMap((row) => (row.kind === "message" && !readOnly && (mine(row.message) || (canModerate && row.message.kind === "text")) ? [row.message.id] : []))}
          picked={picked}
          onPicked={onPicked}
        />
        )}
        <PageBar paging={paging} total={rows.length} label={tr("tin_nhan")} />
      </div>
      <DataTable
        label={tr("tin_nhan")}
        columns={shown ? columns.filter((column) => shown.has(column.key)) : columns}
        rows={visible}
        headerSelect={false}
        rowKey={(row) => (row.kind === "message" ? row.message.id : row.key)}
        rowLabel={(row) => (row.kind === "message" ? `${row.message.username}: ${row.message.content.slice(0, 30)}` : row.key)}
        pickable={(row) => !readOnly && row.kind === "message" && (mine(row.message) || (canModerate && row.message.kind === "text"))}
        picked={picked}
        onPicked={onPicked}
        before={(row) => {
          const day = dayBefore(row);
          const unread = showUnread && row.kind === "message" && row.message.id === firstUnread?.id;
          return day || unread ? (
            <>
              {day && <div className="cw-day">{day}</div>}
              {unread && <div className="cw-day" role="separator">{tr("rm_tin_chua_doc")}</div>}
            </>
          ) : null;
        }}
        actions={
          readOnly
            ? undefined
            : (row) =>
                row.kind === "message" && row.message.kind === "text" ? (
                  <RowMore label={`#${row.message.id}`}>
                    <Button type="button" size="sm" variant="secondary" onClick={() => onReply(row.message)}>
                      {tr("rm_tra_loi")}
                    </Button>
                    {onEdit && mine(row.message) && (
                      <Button type="button" size="sm" variant="secondary" onClick={() => setEditing(row.message)}>
                        {tr("rm_sua")}
                      </Button>
                    )}
                    {onRemove && (mine(row.message) || canModerate) && (
                      <Button type="button" size="sm" variant="danger" onClick={() => onRemove(row.message)}>
                        {tr("rm_xoa")}
                      </Button>
                    )}
                    {onPin && (
                      <Button type="button" size="sm" variant="secondary" onClick={() => onPin(row.message)}>
                        {row.message.pinned_at ? tr("rm_bo_ghim") : tr("rm_ghim")}
                      </Button>
                    )}
                    {!mine(row.message) && row.message.user_id !== myId &&
                      (reported.has(row.message.id) ? (
                        <Button type="button" size="sm" variant="ghost" onClick={() => void takeBack(row.message)}>{tr("sc_huy_bao_cao")}</Button>
                      ) : (
                        <Button type="button" size="sm" variant="ghost" onClick={() => setReporting(row.message)}>{tr("sc_bao_cao")}</Button>
                      ))}
                  </RowMore>
                ) : null
        }
        empty={tr("chua_co_tin_nhan_nao")}
      />
      {reporting && (
        <ReportDialog
          about={`${reporting.username}: ${reporting.content.slice(0, 120)}`}
          onClose={() => setReporting(null)}
          onSend={async (reason, details) => {
            const made = await socialApi.report({ target_type: "message", target_id: String(reporting.id), reason, details });
            setReported((previous) => new Map(previous).set(reporting.id, made.id));
          }}
        />
      )}
      {editing && onEdit && (
        <RowDialog table={MESSAGE_TABLE} row={messageRow(editing)} onClose={() => setEditing(null)} onSave={(changed) => Promise.resolve(onEdit(editing, String(changed.content ?? "")))} />
      )}
    </div>
  );
}
