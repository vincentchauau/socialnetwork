"use client";

import { FormEvent, useId, useState } from "react";

import { type NewRoom, chatApi } from "../api";
import { errorMessage } from "../errors";
import type { Room } from "../protocol";
import { AvatarPicker } from "./AvatarImage";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import Select from "@sn/elements/Select";
import LabelTextBox, { NumberBox } from "@sn/compounds/LabelTextBox";
import { tr } from "../i18n";

type Draft = Omit<NewRoom, "slug"> & { slug: string };

const EMPTY_DRAFT: Draft = {
  title: "",
  slug: "",
  category: "",
  avatar: "",
  visibility: "public",
  join_policy: "open",
  capacity: 200,
};

/** The body of a "make a room" request from what was typed: a blank address is left out, a blank time is no time. */
function newRoomOf(draft: Draft): NewRoom {
  const { slug, ...rest } = draft;
  return { ...rest, title: draft.title.trim(), ...(slug.trim() ? { slug: slug.trim() } : {}) };
}

/** The fields of "make a room": a name, an address (chosen now, never later), a label, a picture, its status and how many people it takes. */
function RoomFields({ draft, onChange }: { draft: Draft; onChange: (next: Draft) => void }) {
  const base = useId();
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => onChange({ ...draft, [key]: value });
  const text = (key: keyof Draft) => (event: { target: { value: string } }) => set(key, event.target.value as never);
  return (
    <>
      <div className="cw-fields">
        <LabelTextBox label={tr("rm_ten_phong")} name="title" value={draft.title} required onChange={text("title")} />
        <LabelTextBox label={tr("rm_dia_chi_phong")} name="slug" value={draft.slug} onChange={text("slug")} />
      </div>
      <div className="cw-fields">
        <LabelTextBox label={tr("rm_nhom_nhan")} name="category" value={draft.category} onChange={text("category")} />
        <AvatarPicker value={draft.avatar} name={draft.title} onChange={(value) => set("avatar", value as never)} />
      </div>
      <div className="cw-fields">
        <div className="cw-field">
          <label htmlFor={`${base}-join`}>{tr("rm_trang_thai")}</label>
          <Select id={`${base}-join`} value={draft.join_policy} onChange={(event) => set("join_policy", event.target.value as Draft["join_policy"])}>
            <option value="open">{tr("rm_cong_khai")}: {tr("rm_cong_khai_mo_ta")}</option>
            <option value="approval">{tr("rm_rieng_tu")}: {tr("rm_rieng_tu_mo_ta")}</option>
          </Select>
        </div>
        <div className="cw-field">
          <label htmlFor={`${base}-capacity`}>{tr("rm_so_nguoi_toi_da")}</label>
          <NumberBox id={`${base}-capacity`} value={draft.capacity} min={2} max={200} onChange={(value) => set("capacity", value)} />
        </div>
      </div>
    </>
  );
}

interface Props {
  onSaved: (room: Room) => void;
  onCancel: () => void;
}

/** The form to make a room (changing one is the Edit form of its row, as in the Table pane). */
export default function RoomForm({ onSaved, onCancel }: Props) {
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!draft.title.trim()) return setError(tr("rm_hay_nhap_ten_phong"));
    setBusy(true);
    setError(null);
    try {
      onSaved(await chatApi.create(newRoomOf(draft)));
    } catch (caught) {
      setError(errorMessage(caught));
      setBusy(false);
    }
  }

  return (
    <form className="cw-form" onSubmit={submit} aria-label={tr("rm_tao_phong")} noValidate>
      <h2>{tr("rm_tao_phong_chat")}</h2>
      <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 12 }}>
        <RoomFields draft={draft} onChange={setDraft} />
      </fieldset>
      <Alert>{error}</Alert>
      <div className="cw-actions">
        <Button type="submit" loading={busy} loadingLabel={tr("dang_xu_ly")}>
          {tr("rm_tao_phong")}
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={onCancel}>
          {tr("rm_huy")}
        </Button>
      </div>
    </form>
  );
}
