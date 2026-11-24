"use client";

import { useState } from "react";

import { chatApi } from "../api";
import { type ChatMessage } from "../protocol";
import { type UploadSpec, runUpload } from "../upload";
import { errorMessage } from "../errors";
import Button from "@sn/elements/Button";
import FaceCard from "./FaceCard";
import SchemaForm, { type FieldSpec, type FormValues } from "@sn/compounds/SchemaForm";
import { tr } from "../i18n";

interface CardAction {
  label: string;
}

interface CardItem {
  title: string;
  subtitle?: string;
  href?: string;
  image?: string;
  actions?: CardAction[];
}

interface Card {
  type: "list" | "detail" | "confirm" | "form" | "camera" | "done" | "error";
  title?: string;
  upload?: UploadSpec;
  video?: string;
  items?: CardItem[];
  lines?: string[];
  image?: string;
  actions?: CardAction[];
  fields?: FieldSpec[];
  submit?: string;
  error?: string;
  summary?: string;
  href?: string;
  status?: "pending" | "running" | "done" | "failed" | "cancelled";
  for?: number;
}

/** The content of a card message, or null when it is not one this page knows (it is then shown as plain text). */
export function parseCard(content: string): Card | null {
  try {
    const card = JSON.parse(content) as Card;
    return card && typeof card === "object" && ["list", "detail", "confirm", "form", "camera", "done", "error"].includes(card.type) ? card : null;
  } catch {
    return null;
  }
}

/** Only an address of this site is linked: a card is written by a program, so it is never trusted to point elsewhere. */
const safeHref = (href: string | undefined): string | undefined => (href && /^\/(?!\/)[A-Za-z0-9/_.-]*$/.test(href) ? href : undefined);

/**
 * A card the assistant of the room put in the conversation: a list of what it found, a question that only the person asked can
 * answer (the buttons are theirs; the answer arrives as the same message, changed), what was done, or why it could not be.
 */
export default function CardMessage({ message, slug, myId }: { message: ChatMessage; slug: string; myId: number }) {
  const card = parseCard(message.content);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  if (!card) return <div className="cw-bubble">{message.content}</div>;
  const mine = card.for === myId;

  async function press(action: number, item?: number) {
    setBusy(true);
    setProblem(null);
    try {
      await chatApi.actCard(slug, message.id, action, item);
    } catch {
      setProblem(tr("rm_the_khong_xu_ly_duoc"));
    } finally {
      setBusy(false);
    }
  }

  async function send(values: FormValues) {
    setBusy(true);
    setProblem(null);
    try {
      // A form with a file first makes its calls to the services as the person; then the chat is told what was made.
      const sent = card?.upload ? await runUpload(card.upload, values) : values;
      await chatApi.submitCard(slug, message.id, sent);
    } catch (caught) {
      setProblem(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  /** The buttons of a card or of one row of a list: only the person it is for sees them. */
  const buttons = (actions: CardAction[] | undefined, item?: number) =>
    mine && actions && actions.length > 0 ? (
      <span className="cw-card-actions">
        {actions.map((button, index) => (
          <Button key={index} type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void press(index, item)}>{button.label}</Button>
        ))}
      </span>
    ) : null;

  async function answer(action: "confirm" | "cancel") {
    setBusy(true);
    setProblem(null);
    try {
      await chatApi.answerCard(slug, message.id, action);
    } catch {
      setProblem(tr("rm_the_khong_xu_ly_duoc"));
    } finally {
      setBusy(false);
    }
  }

  if (card.type === "list") {
    const link = (item: CardItem) => (safeHref(item.href) ? <a href={safeHref(item.href)}>{item.title}</a> : item.title);
    return (
      <div className="cw-bubble cw-card" role="group" aria-label={card.title}>
        <strong>{card.title}</strong>
        {card.items && card.items.length > 0 ? (
          <ul>
            {card.items.map((item, index) => (
              <li key={index}>
                {safeHref(item.image) && <img src={safeHref(item.image)} alt="" className="cw-card-thumb" />}
                {link(item)}
                {item.subtitle && <span className="cw-room-sub"> · {item.subtitle}</span>}
                {buttons(item.actions, index)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="cw-empty">{tr("rm_the_khong_co_ket_qua")}</p>
        )}
      </div>
    );
  }

  if (card.type === "detail") {
    const picture = safeHref(card.image);
    return (
      <div className="cw-bubble cw-card" role="group" aria-label={card.title}>
        <strong>{card.title}</strong>
        {picture && <img src={picture} alt="" className="cw-card-image" />}
        {safeHref(card.video) && <video src={safeHref(card.video)} controls preload="metadata" className="cw-card-image" />}
        {(card.lines ?? []).map((line, index) => <p key={index} className="cw-room-sub">{line}</p>)}
        {buttons(card.actions)}
        {problem && <p role="alert">{problem}</p>}
      </div>
    );
  }

  if (card.type === "camera") {
    if (card.status === "pending" && mine) {
      return (
        <FaceCard
          title={card.title ?? ""}
          saving={busy}
          error={problem ?? card.error ?? null}
          onSave={(scores) => void send({ ...scores } as unknown as FormValues)}
        />
      );
    }
    return (
      <div className="cw-bubble cw-card" role="group" aria-label={card.title}>
        <strong>{card.title}</strong>
        {card.status === "pending" ? <p className="cw-room-sub">{tr("rm_the_cho_nguoi_hoi_tra_loi")}</p> : card.status && <p className="cw-room-sub">{tr(`rm_the_${card.status}`)}</p>}
      </div>
    );
  }

  if (card.type === "form") {
    return (
      <div className="cw-bubble cw-card" role="group" aria-label={card.title}>
        <strong>{card.title}</strong>
        {card.status === "pending" && mine && (
          <SchemaForm
            fields={card.fields ?? []}
            submitLabel={card.submit ?? tr("rm_the_gui")}
            busy={busy}
            error={problem ?? card.error ?? null}
            requiredMessage={(label) => tr("rm_the_can_dien", { p0: label })}
            tooBigMessage={(label, megabytes) => tr("rm_the_file_qua_lon", { p0: label, p1: megabytes })}
            onSubmit={send}
          />
        )}
        {card.status === "pending" && !mine && <p className="cw-room-sub">{tr("rm_the_cho_nguoi_hoi_tra_loi")}</p>}
        {card.status && card.status !== "pending" && <p className="cw-room-sub">{tr(`rm_the_${card.status}`)}</p>}
      </div>
    );
  }

  if (card.type === "confirm") {
    return (
      <div className="cw-bubble cw-card" role="group" aria-label={card.summary}>
        <strong>{card.summary}</strong>
        {card.status === "pending" && mine && (
          <div className="cw-card-actions">
            <Button type="button" size="sm" disabled={busy} onClick={() => void answer("confirm")}>{tr("rm_the_xac_nhan")}</Button>
            <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void answer("cancel")}>{tr("rm_the_bo_qua")}</Button>
          </div>
        )}
        {card.status === "pending" && !mine && <p className="cw-room-sub">{tr("rm_the_cho_nguoi_hoi_tra_loi")}</p>}
        {card.status && card.status !== "pending" && <p className="cw-room-sub">{tr(`rm_the_${card.status}`)}</p>}
        {problem && <p role="alert">{problem}</p>}
      </div>
    );
  }

  const href = safeHref(card.href);
  return (
    <div className={`cw-bubble cw-card${card.type === "error" ? " cw-card-error" : ""}`} role={card.type === "error" ? "alert" : "status"}>
      {card.type === "done" && "✓ "}
      {card.summary}
      {href && card.type === "done" && <> · <a href={href}>{tr("rm_the_mo")}</a></>}
    </div>
  );
}
