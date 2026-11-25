"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { chatApi } from "../api";
import { errorMessage } from "../errors";
import { type Room, isPrivateRoom, roomLink, stateText } from "../protocol";
import { useLobby } from "../useLobby";
import { useRooms } from "../useRooms";
import CrudToolbar from "@sn/complex/CrudToolbar";
import DataTable, { type Column, type Key, type Sort } from "@sn/compounds/DataTable";
import AvatarImage from "./AvatarImage";
import RowMore from "./RowMore";
import RowDialog from "./RowDialog";
import RoomStatusControls from "./RoomStatusControls";
import { CONTROL, PageBar, SelectAllBar, sortRows, useColumns, usePaging } from "./TableControls";
import { ROOM_FIELDS, roomMatches, splitTerms } from "./searchTerms";
import { ROOM_TABLE, changesOfRoom, roomRow } from "./rowTables";
import { TermChips, useSearchTerms } from "@sn/compounds/InputBox";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import { ConfirmModal } from "@sn/compounds/Dialogs";
import { tr } from "../i18n";

const NOTHING_ASKED = (): void => undefined;

const COPIED_MS = 2000;

const statusText = (room: Room): string => (isPrivateRoom(room) ? tr("rm_rieng_tu") : tr("rm_cong_khai"));

type Ask = { kind: "delete" | "leave"; slugs: string[]; title: string } | null;

interface Props {
  selected: string | null;
  onSelect: (slug: string | null) => void;
  onCreate: () => void;
  /** A room was changed from its Edit form (only its owner does that): the room as it is now. */
  onRoomChanged: (room: Room) => void;
  /** Changes when something the list shows changed (a room made, joined, left): the list is fetched again. */
  listVersion: number;
  /** The page of ChatWork opens on the first of my rooms when none is asked for. */
  onFirstRoom?: (slug: string) => void;
  /** Told how many rooms the list has (for the button of Rooms). */
  onCount?: (count: number) => void;
}

/**
 * Rooms: make one (Create), read them all in one table (name, people, who is online, who can come in, whose it is), change one (Edit, only the
 * owner), delete the ones picked (only the owner's). Alive only while Rooms is open.
 */
export default function RoomsPanel({ selected, onSelect, onCreate, onRoomChanged, listVersion, onFirstRoom, onCount }: Props) {
  const searchTerms = useSearchTerms(NOTHING_ASKED);
  const { words, named } = useMemo(() => splitTerms(searchTerms.terms, ROOM_FIELDS), [searchTerms.terms]);
  const [picked, setPicked] = useState<ReadonlySet<Key>>(new Set());
  const [ask, setAsk] = useState<Ask>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>(null);
  const [editing, setEditing] = useState<Room | null>(null);
  // The row of the room being edited is fixed while its dialog is open.
  const editingRow = useMemo(() => (editing ? roomRow(editing) : null), [editing]);
  const opened = useRef(false);
  const lobby = useLobby();
  // One table of every room the person can see: the ones they are in, the requests to write to them, and the public ones they could join.
  const mine = useRooms({ scope: "mine", q: words }, lobby);
  const asked = useRooms({ scope: "requests", q: words }, lobby);
  const open = useRooms({ scope: "public", q: words }, lobby);
  const all = useMemo(() => {
    const seen = new Set<string>();
    return [...mine.rooms, ...asked.rooms, ...open.rooms].filter((room) => !seen.has(room.slug) && seen.add(room.slug));
  }, [mine.rooms, asked.rooms, open.rooms]);
  const rooms = useMemo(() => all.filter((room) => roomMatches(room, named)), [all, named]);
  useEffect(() => {
    if (!searchTerms.text) onCount?.(all.length); // a search leaves some rooms out: the count stays the one of all
  }, [all.length, searchTerms.text, onCount]);
  const paging = usePaging(rooms.length);
  useEffect(() => paging.setOffset(0), [searchTerms.text]); // eslint-disable-line react-hooks/exhaustive-deps
  const loading = mine.loading || asked.loading || open.loading;
  const reload = async () => {
    await Promise.all([mine.reload(), asked.reload(), open.reload()]);
  };
  useEffect(() => {
    if (listVersion > 0) void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listVersion]);
  useEffect(() => {
    if (opened.current || loading) return;
    opened.current = true;
    if (!selected && mine.rooms.length > 0) onFirstRoom?.(mine.rooms[0].slug);
  }, [selected, loading, mine.rooms, onFirstRoom]);

  const isOwner = (room: Room) => room.me?.role === "owner" && room.me.status === "joined";
  const mayDelete = (room: Room) => isOwner(room);
  const mayLeave = (room: Room) => room.me?.status === "joined";
  const mayJoin = (room: Room) => room.kind === "chat" && room.state === "open" && room.me?.status !== "joined" && room.me?.status !== "pending" && room.me?.status !== "banned";

  async function run(kind: "delete" | "leave", slugs: string[]) {
    setError(null);
    try {
      for (const slug of slugs) await (kind === "leave" ? chatApi.leave(slug) : chatApi.remove(slug));
    } catch (caught) {
      setError(errorMessage(caught));
    }
    setPicked(new Set());
    await reload();
    if (selected && slugs.includes(selected)) onSelect(null);
  }

  async function join(room: Room) {
    setError(null);
    try {
      await chatApi.join(room.slug);
    } catch (caught) {
      setError(errorMessage(caught));
    }
    await reload();
  }

  async function copy(room: Room) {
    try {
      await navigator.clipboard.writeText(roomLink(room.slug));
      setCopied(room.slug);
      setTimeout(() => setCopied((slug) => (slug === room.slug ? null : slug)), COPIED_MS);
    } catch {
      setError(tr("khong_sao_chep_duoc_hay_chon"));
    }
  }

  const columns: Column<Room>[] = [
    {
      key: "name",
      label: tr("rm_ten_phong"),
      sortValue: (room) => room.title,
      className: "cw-col-name",
      render: (room) => {
        const unread = room.me?.notify === false ? 0 : (room.me?.unread ?? 0);
        const note = room.me?.status === "pending" ? tr("rm_dang_cho_duyet") : stateText(room.state);
        return (
          <>
            <AvatarImage url={room.avatar} name={room.title} />
            <Button type="button" size="sm" variant="ghost" aria-current={room.slug === selected ? "true" : undefined} onClick={() => onSelect(room.slug)}>
              {room.visibility === "private" ? "🔒 " : ""}
              {room.title}
            </Button>
            {note && <span className="cw-tag">{note}</span>}
            {unread > 0 && <span className="cw-badge" aria-label={tr("rm_p0_chua_doc", { p0: unread })}>{unread > 99 ? "99+" : unread}</span>}
          </>
        );
      },
    },
    { key: "people", label: tr("rm_thanh_vien"), narrow: true, sortValue: (room) => room.members, render: (room) => (room.kind === "dm" ? "" : `${room.members}/${room.capacity}`) },
    { key: "owner", label: tr("rm_chu_phong_cot"), narrow: true, sortValue: (room) => room.owner_name ?? "", render: (room) => `${room.owner_name ?? ""}${isOwner(room) ? ` (${tr("rm_ban")})` : ""}`.trim() || "—" },
    { key: "access", label: tr("rm_trang_thai"), narrow: true, sortValue: (room) => statusText(room), render: (room) => statusText(room) },
  ];

  const columnChoice = useColumns("rooms", columns.map((column) => ({ key: column.key, label: column.label })));
  const sortedRooms = sortRows(rooms, columns, sort);
  const pageRooms = paging.page(sortedRooms);

  return (
    <aside className="cw-embed-rooms cw-panel" aria-label={tr("em_phong")}>
      <CrudToolbar
        name={tr("rm_phong_chat")}
        searchLabel={tr("rm_tim_phong")}
        query=""
        onQuery={() => undefined}
        search={searchTerms}
        createLabel={tr("rm_tao_phong")}
        onCreate={onCreate}
        pickedCount={picked.size}
        controlStyle={CONTROL}
        extra={columnChoice.menu}
        bulk={[
          {
            key: "delete",
            label: tr("rm_xoa"),
            variant: "danger",
            onClick: () => {
              const slugs = rooms.filter((room) => picked.has(room.slug) && mayDelete(room)).map((room) => room.slug);
              if (slugs.length > 0) setAsk({ kind: "delete", slugs, title: slugs.length === 1 ? (rooms.find((room) => room.slug === slugs[0])?.title ?? "") : "" });
            },
          },
        ]}
      />
      <TermChips search={searchTerms} total={rooms.length} ready={!loading} />
      <Alert>{mine.error ?? open.error ?? error}</Alert>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <SelectAllBar keys={pageRooms.filter(mayDelete).map((room) => room.slug)} picked={picked} onPicked={setPicked} />
        <PageBar paging={paging} total={rooms.length} label={tr("danh_sach_phong")} />
      </div>
      <DataTable
        label={tr("danh_sach_phong")}
        columns={columns.filter((column) => columnChoice.shown.has(column.key))}
        rows={pageRooms}
        headerSelect={false}
        sort={sort}
        onSort={setSort}
        rowKey={(room) => room.slug}
        rowLabel={(room) => room.title}
        pickable={mayDelete}
        picked={picked}
        onPicked={setPicked}
        current={(room) => room.slug === selected}
        empty={loading ? tr("dang_tai") : searchTerms.text ? tr("khong_co_phong_nao_khop_bo") : tr("rm_ban_chua_vao_phong_nao")}
        actions={(room) => (
          <RowMore label={room.title}>
            {mayJoin(room) && (
              <Button type="button" size="sm" onClick={() => void join(room)}>
                {tr("rm_tham_gia")}
              </Button>
            )}
            {room.kind === "chat" && (
              <Button type="button" size="sm" variant="secondary" onClick={() => void copy(room)}>
                {copied === room.slug ? tr("da_sao_chep") : tr("rm_lien_ket")}
              </Button>
            )}
            <RoomStatusControls room={room} onRoom={() => void reload()} />
            {isOwner(room) && room.kind === "chat" && (
              <Button type="button" size="sm" variant="secondary" onClick={() => setEditing(room)}>
                {tr("rm_sua")}
              </Button>
            )}
            {mayLeave(room) && (
              <Button type="button" size="sm" variant="danger" onClick={() => setAsk({ kind: "leave", slugs: [room.slug], title: room.title })}>
                {tr("rm_roi")}
              </Button>
            )}
          </RowMore>
        )}
      />
      <p role="status" className="cw-room-sub" style={{ margin: 0 }}>
        {tr("rm_p0_dang_truc_tuyen", { p0: lobby.onlineTotal })}
      </p>
      {editing && editingRow && (
        <RowDialog
          table={ROOM_TABLE}
          row={editingRow}
          onClose={() => setEditing(null)}
          onSave={async (changed) => {
            onRoomChanged(await chatApi.update(editing.slug, changesOfRoom(changed)));
            void reload();
          }}
        />
      )}
      <ConfirmModal
        open={ask !== null}
        message={ask ? (ask.kind === "delete" ? (ask.slugs.length === 1 ? tr("rm_xoa_phong_p0_hoi", { p0: ask.title }) : tr("rm_xoa_p0_phong_hoi", { p0: ask.slugs.length })) : tr("rm_roi_phong_p0_hoi", { p0: ask.title })) : ""}
        confirmLabel={ask?.kind === "delete" ? tr("rm_xoa") : tr("rm_roi_phong")}
        cancelLabel={tr("rm_huy")}
        onCancel={() => setAsk(null)}
        onConfirm={() => {
          const current = ask;
          setAsk(null);
          if (current) void run(current.kind, current.slugs);
        }}
      />
    </aside>
  );
}
