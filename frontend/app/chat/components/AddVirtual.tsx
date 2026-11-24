"use client";

import { useId, useState } from "react";

import { chatApi } from "../api";
import { errorMessage } from "../errors";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import Select from "@sn/elements/Select";

const VIRTUAL_CHOICES = [1, 2, 3, 4, 5, 8, 10, 15, 20, 30, 50, 100];

/** The event that says the people of a room changed (the page around the chat may follow, like the Werewolf game of the room). */
export const MEMBERS_CHANGED = "sn:room-members-changed";
/** The event that says who is in the room (or online in it) changed on the server: the views of the people of the room load them again. */
export const PEOPLE_CHANGED = "sn:room-people-changed";

/** Add a number of virtual people to a room at once: they answer what people write there. The room's member list shows who came. */
export default function AddVirtual({ slug, onAdded }: { slug: string; onAdded?: () => void }) {
  const [count, setCount] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectId = useId();

  async function add() {
    setBusy(true);
    setError(null);
    try {
      await chatApi.addVirtual(slug, count);
      onAdded?.();
      window.dispatchEvent(new CustomEvent(MEMBERS_CHANGED, { detail: { slug } }));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cw-add-virtual-box">
      <div className="cw-add-virtual" style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "center" }}>
        <Select id={selectId} aria-label={tr("rm_so_nguoi_ao")} value={count} onChange={(event) => setCount(Number(event.target.value))} disabled={busy}>
          {VIRTUAL_CHOICES.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </Select>
        <Button type="button" size="sm" disabled={busy} style={{ flex: "0 0 auto" }} onClick={() => void add()}>{tr("rm_them_nguoi_ao")}</Button>
      </div>
      <Alert>{error}</Alert>
    </div>
  );
}
