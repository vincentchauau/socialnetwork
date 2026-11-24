"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { type Person, socialApi } from "../api";
import { socialError } from "../errors";
import { useOpenChat } from "../useOpenChat";
import ReportDialog from "./ReportDialog";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import { ConfirmModal } from "@sn/compounds/Dialogs";
import { tr } from "../i18n";

/** What the person is called: the name they gave, else the account name. */
const nameOf = (person: Pick<Person, "display_name" | "username">): string => person.display_name || person.username;

/** Every button in one row (a table row has no room for a second line). */
const INLINE = { display: "flex", flexWrap: "nowrap", gap: 6, alignItems: "center", whiteSpace: "nowrap" } as const;

interface Props {
  username: string;
  /** What is known of the person already (a profile, a list row); else it is asked when the actions are first shown. */
  initial?: Person | null;
  /** A small "Actions" button that opens the actions (for a table row), instead of showing them at once. */
  menu?: boolean;
  /** The button that opens a private chat (a page of the person has it; a room's table has its own). */
  withMessage?: boolean;
  /** A link to the profile page among the actions. */
  withProfile?: boolean;
  /** The person changed (a friendship, a block): the new state. */
  onChanged?: (person: Person) => void;
}

/**
 * What I can do about one person: see the profile, ask to be friends or stop, answer a request, block or unblock (asked first), report with a
 * reason, write privately. One piece for the profile page and the members of a room, so the rules are written once.
 */
export default function PersonActions({ username, initial = null, menu = false, withMessage = true, withProfile = false, onChanged }: Props) {
  const [person, setPerson] = useState<Person | null>(initial);
  const [open, setOpen] = useState(!menu);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reporting, setReporting] = useState(false);
  const [confirmBlock, setConfirmBlock] = useState(false);
  const [myReport, setMyReport] = useState<number | null>(null);  // my open report about this person, which I can take back
  const chat = useOpenChat();
  const personId = person?.user_id;

  useEffect(() => {
    if (initial) setPerson(initial);
  }, [initial]);

  const load = useCallback(async () => {
    try {
      setPerson(await socialApi.person(username));
    } catch (caught) {
      setError(socialError(caught));
    }
  }, [username]);

  // The relation is asked only when the actions are looked at (a table of members would otherwise ask for every row).
  useEffect(() => {
    if (open && !person) void load();
  }, [open, person, load]);

  // Have I reported this person already? Asked only when the actions are looked at.
  useEffect(() => {
    if (!open || personId === undefined) return;
    let current = true;
    void (async () => {
      try {
        const mine = await socialApi.myReports();
        if (current) setMyReport(mine.find((row) => row.target_type === "user" && row.target_id === String(personId))?.id ?? null);
      } catch {
        // the button of Report stays: taking back is a help, not worth an error
      }
    })();
    return () => {
      current = false;
    };
  }, [open, personId]);

  async function act(work: () => Promise<unknown>) {
    setError(null);
    setNotice(null);
    try {
      await work();
      const fresh = await socialApi.person(username);
      setPerson(fresh);
      onChanged?.(fresh);
    } catch (caught) {
      setError(socialError(caught));
    }
  }

  async function takeBackReport(reportId: number) {
    await act(async () => {
      await socialApi.unreport(reportId);
      setMyReport(null);
      setNotice(tr("sc_da_huy_bao_cao"));
    });
  }

  const profile = `/chat/people/${encodeURIComponent(username)}`;
  const label = tr("sc_hanh_dong_voi_p0", { p0: person ? nameOf(person) : username });
  return (
    <div className="cw-actions" role="group" aria-label={label} style={menu ? undefined : INLINE}>
      {menu && (
        <Button type="button" size="sm" variant="ghost" aria-expanded={open} aria-label={label} onClick={() => setOpen((shown) => !shown)}>
          {tr("sc_hanh_dong")}
        </Button>
      )}
      {open && (
        <>
          <Alert>{error ?? chat.error}</Alert>
          <Alert tone="success">{notice}</Alert>
          {withProfile && <Link href={profile}>{tr("sc_xem_ho_so")}</Link>}
          {person && (
            <>
              {person.relation === "none" && !person.blocked && <Button type="button" size="sm" onClick={() => void act(() => socialApi.ask(person.user_id))}>{tr("sc_ket_ban")}</Button>}
              {person.relation === "incoming" && (
                <>
                  <Button type="button" size="sm" onClick={() => void act(() => socialApi.accept(person.user_id))}>{tr("sc_chap_nhan")}</Button>
                  <Button type="button" size="sm" variant="secondary" onClick={() => void act(() => socialApi.decline(person.user_id))}>{tr("sc_tu_choi")}</Button>
                </>
              )}
              {person.relation === "requested" && <Button type="button" size="sm" variant="secondary" onClick={() => void act(() => socialApi.unfriend(person.user_id))}>{tr("sc_huy_loi_moi")}</Button>}
              {person.relation === "friends" && <Button type="button" size="sm" variant="secondary" onClick={() => void act(() => socialApi.unfriend(person.user_id))}>{tr("sc_huy_ket_ban")}</Button>}
              {withMessage && !person.blocked && <Button type="button" size="sm" onClick={() => void chat.message(person)}>{tr("sc_nhan_tin")}</Button>}
              {person.blocked ? (
                <Button type="button" size="sm" variant="secondary" onClick={() => void act(() => socialApi.unblock(person.user_id))}>{tr("sc_bo_chan")}</Button>
              ) : (
                <Button type="button" size="sm" variant="secondary" onClick={() => setConfirmBlock(true)}>{tr("sc_chan")}</Button>
              )}
              {myReport !== null ? (
                <Button type="button" size="sm" variant="ghost" onClick={() => void takeBackReport(myReport)}>{tr("sc_huy_bao_cao")}</Button>
              ) : (
                <Button type="button" size="sm" variant="ghost" aria-pressed={reporting} onClick={() => setReporting((shown) => !shown)}>{tr("sc_bao_cao")}</Button>
              )}
              {reporting && myReport === null && (
                <ReportDialog
                  about={nameOf(person)}
                  onClose={() => setReporting(false)}
                  onSend={async (reason, details) => {
                    const made = await socialApi.report({ target_type: "user", target_id: String(person.user_id), reason, details });
                    setMyReport(made?.id ?? null);
                    setNotice(tr("sc_da_bao_cao"));
                  }}
                />
              )}
              <ConfirmModal
                open={confirmBlock}
                message={tr("sc_xac_nhan_chan", { p0: nameOf(person) })}
                confirmLabel={tr("sc_chan")}
                cancelLabel={tr("rm_huy")}
                onCancel={() => setConfirmBlock(false)}
                onConfirm={() => {
                  setConfirmBlock(false);
                  void act(() => socialApi.block(person.user_id));
                }}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}
