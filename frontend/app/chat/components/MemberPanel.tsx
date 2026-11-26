"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { chatApi } from "../api";
import { errorMessage } from "../errors";
import type { MemberRow, Room } from "../protocol";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import TextBox from "@sn/elements/TextBox";
import { ConfirmModal } from "@sn/compounds/Dialogs";
import AddVirtual, { MEMBERS_CHANGED } from "./AddVirtual";
import CrudToolbar, { type BulkAction } from "@sn/complex/CrudToolbar";
import PersonActions from "./PersonActions";
import RowDialog from "./RowDialog";
import { MEMBER_TABLE, changesOfMember, memberRow } from "./rowTables";
import AvatarImage from "./AvatarImage";
import RowMore from "./RowMore";
import DataTable, { type Column, type Key, type Sort } from "@sn/compounds/DataTable";
import { CONTROL, PageBar, SelectAllBar, sortRows, useColumns, usePaging } from "./TableControls";
import { MEMBER_FIELDS, has, splitTerms } from "./searchTerms";
import { TermChips, useSearchTerms } from "@sn/compounds/InputBox";
import { tr } from "../i18n";

const NOTHING_ASKED = (): void => undefined;
const STATUSES = ["joined", "pending", "left", "kicked", "banned"];
const STATUS_LABEL: Record<string, () => string> = {
  joined: () => tr("rm_st_joined"),
  pending: () => tr("rm_dang_cho_duyet"),
  left: () => tr("rm_st_left"),
  kicked: () => tr("rm_st_kicked"),
  banned: () => tr("rm_st_banned"),
};

interface Props {
  room: Room;
  myId: number;
  /** Changes when someone joined or left, so the list is fetched again. */
  version: number;
  /** Who has the room open right now (the live presence of the room): it says who is online, as it changes. */
  onlineIds?: ReadonlySet<number>;
  /** Write privately to a member. */
  onWrite: (userId: number, username: string) => void;
  /** The room itself changed: ask for it again. */
  onChanged: () => void;
}

type Ask = { kind: "ban" | "kick" | "owner"; ids: number[] } | null;

const isMuted = (member: MemberRow): boolean => member.muted;

const cap = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);
const roleText = (role: MemberRow["role"]): string => cap(role === "owner" ? tr("rm_chu_phong") : tr("rm_thanh_vien_thuong"));

/**
 * Members: add one (a username, or some virtual people drawn at random), read the people of the room in one table (who, what role, a person
 * or a virtual one, in the room or not), change the ones picked (approve, kick, ban: only the owner), write privately to one.
 */
export default function MemberPanel({ room, myId, version, onlineIds, onWrite, onChanged }: Props) {
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ask, setAsk] = useState<Ask>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<MemberRow | null>(null);
  const [sort, setSort] = useState<Sort>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const searchTerms = useSearchTerms(NOTHING_ASKED);
  const { words, named } = useMemo(() => splitTerms(searchTerms.terms, MEMBER_FIELDS), [searchTerms.terms]);
  const statusTerm = STATUSES.includes(named.status) ? named.status : ""; // `status:left` asks the server for the ones who left
  const [picked, setPicked] = useState<ReadonlySet<Key>>(new Set());
  const owner = room.me?.role === "owner" && room.me.status === "joined";
  const canAdd = room.kind !== "dm" && room.me?.status === "joined";

  const load = useCallback(async () => {
    try {
      setMembers(await chatApi.members(room.slug, words, statusTerm === "joined" || statusTerm === "pending" ? "" : statusTerm));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [room.slug, words, statusTerm]);

  // The list follows what is searched, and the room when somebody comes or goes.
  useEffect(() => {
    void load();
  }, [load, version]);

  async function act(work: () => Promise<unknown>) {
    try {
      await work();
      setError(null);
      await load();
      onChanged();
      window.dispatchEvent(new CustomEvent(MEMBERS_CHANGED, { detail: { slug: room.slug } })); // the game of the room follows the people
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  /** Do `work` for every id, one after the other; then the table is fetched again and the picking starts over. */
  async function each(ids: number[], work: (id: number) => Promise<unknown>) {
    setPicked(new Set());
    await act(async () => {
      for (const id of ids) await work(id);
    });
  }

  const inRoom = statusTerm === "" || statusTerm === "joined" || statusTerm === "pending";
  const listed = members.filter(
    (member) =>
      (!inRoom || member.status === "joined" || member.status === "pending") &&
      (statusTerm !== "joined" && statusTerm !== "pending" ? true : member.status === statusTerm) &&
      (!named.role || member.role === named.role) &&
      has(member.username, named.name ?? ""),
  );
  const paging = usePaging(listed.length);
  useEffect(() => paging.setOffset(0), [searchTerms.text]); // eslint-disable-line react-hooks/exhaustive-deps
  const isOnline = (member: MemberRow): boolean => (onlineIds ? onlineIds.has(member.user_id) : member.online);
  const pickable = (member: MemberRow) => owner && member.user_id !== myId && member.role !== "owner";
  const chosen = listed.filter((member) => picked.has(member.user_id));
  const chosenIds = chosen.map((member) => member.user_id);

  const pendingOnes = chosen.filter((m) => m.status === "pending");
  const loosOnes = chosen.filter((m) => m.status === "joined" && !isMuted(m));
  const mutedOnes = chosen.filter((m) => m.status === "joined" && isMuted(m));
  const idsOf = (list: MemberRow[]) => list.map((m) => m.user_id);
  const set = (list: MemberRow[], body: { status?: "joined" | "banned"; muted?: boolean }) => () => void each(idsOf(list), (id) => chatApi.changeMember(room.slug, id, body));
  // only what fits the people picked: a muted one has Unmute, not Mute; Approve/Decline are for those waiting
  const bulk: BulkAction[] = !owner
    ? []
    : inRoom
      ? [
          { key: "approve", label: tr("rm_duyet"), variant: "primary", show: pendingOnes.length > 0, onClick: set(pendingOnes, { status: "joined" }) },
          { key: "decline", label: tr("sc_tu_choi"), variant: "secondary", show: pendingOnes.length > 0, onClick: () => void each(idsOf(pendingOnes), (id) => chatApi.removeMember(room.slug, id)) },
          { key: "mute", label: tr("rm_tat_tieng"), variant: "secondary", show: loosOnes.length > 0, onClick: set(loosOnes, { muted: true }) },
          { key: "unmute", label: tr("rm_bat_tieng"), variant: "secondary", show: mutedOnes.length > 0, onClick: set(mutedOnes, { muted: false }) },
          { key: "kick", label: tr("rm_moi_ra"), variant: "danger", show: chosen.some((m) => m.status === "joined" || m.status === "pending"), onClick: () => setAsk({ kind: "kick", ids: chosenIds }) },
          { key: "ban", label: tr("rm_chan"), variant: "danger", show: chosen.some((m) => m.status !== "banned"), onClick: () => setAsk({ kind: "ban", ids: chosenIds }) },
        ].filter((action) => action.show || chosen.length === 0).map(({ show: showFlag, ...action }) => action) as BulkAction[]
      : statusTerm === "banned"
        ? [{ key: "unban", label: tr("rm_bo_chan"), variant: "primary", onClick: () => void each(chosenIds, (id) => chatApi.changeMember(room.slug, id, { status: "joined" })) }]
        : [{ key: "back", label: tr("rm_them_lai"), variant: "primary", onClick: () => void each(chosenIds, (id) => chatApi.addMember(room.slug, { user_id: id })) }];

  const columns: Column<MemberRow>[] = [
    {
      key: "name",
      label: tr("rm_ten_dang_nhap"),
      sortValue: (member) => member.username,
      render: (member) => (
        <>
          <AvatarImage url={member.avatar} name={member.name || member.username} />
          {member.status === "joined" && (
            <span className="cw-dot" role="img" aria-label={isOnline(member) ? tr("rm_dang_truc_tuyen") : tr("rm_ngoai_tuyen")} style={{ opacity: isOnline(member) ? 1 : 0.25 }} />
          )}
          <Link href={`/chat/people/${encodeURIComponent(member.username)}`}>{member.username}</Link>
          {member.user_id === myId ? ` (${tr("rm_ban")})` : ""}
          {member.virtual && <span className="cw-tag">{tr("sc_ao")}</span>}
          {member.status === "pending" && <span className="cw-tag">{tr("rm_dang_cho_duyet")}</span>}
          {isMuted(member) && <span className="cw-tag">{tr("rm_dang_bi_tat_tieng")}</span>}
        </>
      ),
    },
    { key: "display", label: tr("rm_ho_ten"), sortValue: (member) => member.name ?? "", render: (member) => member.name || "—" },
    { key: "role", label: tr("rm_vai_tro"), narrow: true, sortValue: (member) => roleText(member.role), render: (member) => roleText(member.role) },
  ];

  const askText = (pending: NonNullable<Ask>): string => {
    if (pending.kind === "owner") return tr("rm_doi_chu_phong_hoi_p0", { p0: members.find((member) => member.user_id === pending.ids[0])?.username ?? "" });
    return pending.kind === "ban" ? tr("rm_chan_p0_nguoi_hoi", { p0: pending.ids.length }) : tr("rm_moi_p0_nguoi_ra_hoi", { p0: pending.ids.length });
  };

  const columnChoice = useColumns("members", columns.map((column) => ({ key: column.key, label: column.label })), ["display"]);
  const rows = paging.page(sortRows(listed, columns, sort));

  async function addByName() {
    const wanted = name.trim();
    if (!wanted) return;
    setNotice(null);
    await act(async () => {
      const added = await chatApi.addMember(room.slug, { username: wanted });
      setName("");
      if (added.status === "pending") setNotice(tr("rm_da_moi_cho_duyet"));
    });
  }

  return (
    <section aria-label={tr("rm_thanh_vien")} className="cw-panel">
      <CrudToolbar
        name={tr("rm_thanh_vien")}
        searchLabel={tr("rm_tim_thanh_vien")}
        query=""
        onQuery={() => undefined}
        search={searchTerms}
        createLabel={canAdd ? tr("rm_moi_nguoi") : undefined}
        onCreate={canAdd ? () => setAdding((v) => !v) : undefined}
        creating={adding}
        pickedCount={picked.size}
        controlStyle={CONTROL}
        extra={columnChoice.menu}
        bulk={bulk}
      />
      <TermChips search={searchTerms} total={listed.length} ready />
      {adding && canAdd && (
        <div className="stack cw-create" role="group" aria-label={tr("rm_moi_nguoi")}>
          <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <form className="row" style={{ gap: 6 }} onSubmit={(event) => { event.preventDefault(); void addByName(); }}>
              <TextBox value={name} maxLength={32} autoComplete="off" aria-label={tr("rm_ten_dang_nhap")} placeholder={tr("rm_ten_dang_nhap")} onChange={(event) => setName(event.target.value)} />
              <Button type="submit" size="sm" disabled={!name.trim()}>{tr("rm_them")}</Button>
            </form>
            {room.state === "open" && <AddVirtual slug={room.slug} onAdded={() => { void load(); onChanged(); }} />}
          </div>
        </div>
      )}
      <Alert>{error}</Alert>
      <Alert tone="success">{notice}</Alert>
      <div className="row" style={{ gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        {owner && <SelectAllBar keys={rows.filter(pickable).map((member) => member.user_id)} picked={picked} onPicked={setPicked} />}
        <PageBar paging={paging} total={listed.length} label={tr("rm_thanh_vien")} />
      </div>
      <DataTable
        label={tr("rm_thanh_vien")}
        columns={columns.filter((column) => columnChoice.shown.has(column.key))}
        rows={rows}
        headerSelect={false}
        sort={sort}
        onSort={setSort}
        rowKey={(member) => member.user_id}
        rowLabel={(member) => member.username}
        pickable={pickable}
        picked={picked}
        onPicked={setPicked}
        empty={tr("rm_khong_tim_thay")}
        actions={(member) => {
          if (member.user_id === myId) return null;
          const mine = owner && member.role !== "owner"; // the owner looks after everybody but themself
          const one = (work: (id: number) => Promise<unknown>) => () => void each([member.user_id], work);
          const label = (verb: string) => ({ "aria-label": `${verb} ${member.username}` });
          return (
            <RowMore label={member.username}>
              {member.status === "joined" && (
                <>
                  <Button type="button" size="sm" variant="secondary" onClick={() => onWrite(member.user_id, member.username)}>
                    {tr("rm_nhan")}
                  </Button>
                  <PersonActions username={member.username} menu={false} withMessage={false} withProfile />
                </>
              )}
              {mine && member.status === "pending" && (
                <>
                  <Button type="button" size="sm" {...label(tr("rm_duyet"))} onClick={one((id) => chatApi.changeMember(room.slug, id, { status: "joined" }))}>{tr("rm_duyet")}</Button>
                  <Button type="button" size="sm" variant="secondary" {...label(tr("sc_tu_choi"))} onClick={one((id) => chatApi.removeMember(room.slug, id))}>{tr("sc_tu_choi")}</Button>
                </>
              )}
              {mine && member.status === "joined" && (
                <>
                  <Button type="button" size="sm" variant="secondary" {...label(member.muted ? tr("rm_bat_tieng") : tr("rm_tat_tieng"))} onClick={one((id) => chatApi.changeMember(room.slug, id, { muted: !member.muted }))}>
                    {member.muted ? tr("rm_bat_tieng") : tr("rm_tat_tieng")}
                  </Button>
                  <Button type="button" size="sm" variant="secondary" {...label(tr("rm_dat_chu"))} onClick={() => setAsk({ kind: "owner", ids: [member.user_id] })}>{tr("rm_dat_chu")}</Button>
                  <Button type="button" size="sm" variant="danger" {...label(tr("rm_moi_ra"))} onClick={() => setAsk({ kind: "kick", ids: [member.user_id] })}>{tr("rm_moi_ra")}</Button>
                  <Button type="button" size="sm" variant="danger" {...label(tr("rm_chan"))} onClick={() => setAsk({ kind: "ban", ids: [member.user_id] })}>{tr("rm_chan")}</Button>
                </>
              )}
              {mine && member.status === "banned" && (
                <Button type="button" size="sm" {...label(tr("rm_bo_chan"))} onClick={one((id) => chatApi.changeMember(room.slug, id, { status: "joined" }))}>{tr("rm_bo_chan")}</Button>
              )}
              {mine && (member.status === "left" || member.status === "kicked") && (
                <Button type="button" size="sm" {...label(tr("rm_them_lai"))} onClick={one((id) => chatApi.addMember(room.slug, { user_id: id }))}>{tr("rm_them_lai")}</Button>
              )}
              {mine && (
                <Button type="button" size="sm" variant="secondary" aria-label={`${tr("rm_sua")} ${member.username}`} onClick={() => setEditing(member)}>
                  {tr("rm_sua")}
                </Button>
              )}
            </RowMore>
          );
        }}
      />
      <ConfirmModal
        open={ask !== null}
        message={ask ? askText(ask) : ""}
        confirmLabel={ask?.kind === "kick" ? tr("rm_moi_ra") : ask?.kind === "owner" ? tr("rm_dat_chu") : tr("rm_chan")}
        cancelLabel={tr("rm_huy")}
        onCancel={() => setAsk(null)}
        onConfirm={() => {
          const current = ask;
          setAsk(null);
          if (!current) return;
          void each(current.ids, (id) => (current.kind === "ban" ? chatApi.changeMember(room.slug, id, { status: "banned" }) : current.kind === "owner" ? chatApi.transfer(room.slug, id) : chatApi.removeMember(room.slug, id)));
        }}
      />
      {editing && (
        <RowDialog
          table={MEMBER_TABLE}
          row={memberRow(editing)}
          onClose={() => setEditing(null)}
          onSave={async (changed) => {
            const { body, handOver } = changesOfMember(changed);
            if (Object.keys(body).length > 0) await chatApi.changeMember(room.slug, editing.user_id, body);
            if (handOver) await chatApi.transfer(room.slug, editing.user_id);
            await load();
            onChanged();
          }}
        />
      )}
    </section>
  );
}
