"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";

import { chatApi } from "../api";
import { errorMessage } from "../errors";
import type { ChatMessage } from "../protocol";
import Alert from "@sn/elements/Alert";
import CrudToolbar from "@sn/complex/CrudToolbar";
import { CONTROL } from "./TableControls";
import { MESSAGE_FIELDS, has, splitTerms } from "./searchTerms";
import { TermChips, useSearchTerms } from "@sn/compounds/InputBox";
import { tr } from "../i18n";
import { intlLocale } from "@sn/lib/i18n";

const dayOf = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString(intlLocale(), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};

interface Props {
  slug: string;
  /** How many messages are picked in the table. */
  pickedCount: number;
  /** Delete the picked ones (only a sender picks their own; the owner of the room, any). */
  onDelete: () => void;
  /** The Columns menu of the table of messages. */
  extra?: ReactNode;
}

const NOTHING_ASKED = (): void => undefined;

/** The bar of the messages (the same as the rooms' and the members'): search the room (words, `from:name`), Columns, delete the ones picked. */
export default function MessageToolbar({ slug, pickedCount, onDelete, extra }: Props) {
  const searchTerms = useSearchTerms(NOTHING_ASKED);
  const { words, named } = useMemo(() => splitTerms(searchTerms.terms, MESSAGE_FIELDS), [searchTerms.terms]);
  const [hits, setHits] = useState<ChatMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    searchTerms.clear();
    setHits(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  useEffect(() => {
    if (!words.trim()) {
      setHits(null);
      setError(null);
      return;
    }
    let current = true;
    chatApi.searchMessages(slug, words).then(
      (found) => {
        if (current) {
          setHits(found);
          setError(null);
        }
      },
      (caught) => current && setError(errorMessage(caught)),
    );
    return () => {
      current = false;
    };
  }, [words, slug]);

  const shown = hits === null ? null : hits.filter((message) => has(message.username, named.from ?? ""));
  return (
    <div className="stack cw-panel-head">
      <CrudToolbar
        name={tr("rm_tin_nhan")}
        searchLabel={tr("rm_tim_tin_nhan")}
        query=""
        onQuery={() => undefined}
        search={searchTerms}
        extra={extra}
        controlStyle={CONTROL}
        pickedCount={pickedCount}
        bulk={[{ key: "delete", label: tr("rm_xoa"), variant: "danger", onClick: onDelete }]}
      />
      <TermChips search={searchTerms} total={shown?.length ?? 0} ready={shown !== null} />
      <Alert>{error}</Alert>
      {shown !== null &&
        (shown.length === 0 ? (
          <p className="cw-empty" role="status">{tr("rm_khong_tim_thay")}</p>
        ) : (
          <ul className="cw-members" aria-label={tr("rm_ket_qua_tim_kiem")} style={{ maxHeight: 160, overflowY: "auto", margin: 0 }}>
            {[...shown].reverse().map((message) => (
              <li key={message.id} className="cw-member">
                <b>{message.username}</b>
                <span className="cw-room-sub">{dayOf(message.created_at)}</span>
                <span>{message.content}</span>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
