"use client";

import { type ReactNode, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { useSession } from "@sn/lib/useSession";
import { errorText } from "@sn/api";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import Select from "@sn/elements/Select";
import { type Cv, getCv } from "../lib/cv";
import { tr } from "../i18n";

/** The three layouts of a CV: classic (one column, rules), modern (two columns), minimal (one column, no ornament). */
export const CV_STYLES = ["classic", "modern", "minimal"] as const;
export type CvStyle = (typeof CV_STYLES)[number];

/** A CV. `?u=<name>` shows that person's CV; without it, the signed-in person's own CV. */
export default function CvView() {
  const params = useSearchParams();
  const auth = useSession();
  const requested = params.get("u")?.trim() || null;
  const ownName = auth.status === "signed-in" ? auth.user.username : null;
  const username = requested ?? ownName;
  const [cv, setCv] = useState<Cv | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [style, setStyle] = useState<CvStyle>("classic");

  const load = async (name: string) => {
    setError(null);
    try {
      setCv(await getCv(name));
    } catch (failure) {
      setError(errorText(failure, tr("cv_loi")));
    }
  };

  useEffect(() => {
    if (auth.status === "loading") return;
    if (!username) {
      setCv(null);
      return;
    }
    void load(username);
  }, [username, auth.status]);

  if (auth.status === "loading") return <p role="status">{tr("loading")}</p>;
  if (!username) return <p>{tr("cv_can_dang_nhap")}</p>;
  if (!cv) return error ? <Alert>{error}</Alert> : <p role="status">{tr("loading")}</p>;

  const hidden = (part: string) => cv.hidden.includes(part);
  const place = [cv.city, cv.region, cv.country].filter(Boolean).join(", ");
  const blocks = buildBlocks(cv, hidden, style);
  const ornate = style !== "minimal";

  return (
    <article aria-label={tr("cv_cua")} className={`cv-sheet cv-${style}`} style={sheetStyle(style)}>
      <style>{`@page { margin: 12mm; }
@media print {
  body * { visibility: hidden !important; }
  article.cv-sheet, article.cv-sheet * { visibility: visible !important; }
  article.cv-sheet { position: absolute !important; left: 0; top: 0; width: 100% !important; max-width: none !important; margin: 0 !important; padding: 0 !important; border: none !important; border-radius: 0 !important; background: #fff !important; color: #000 !important; gap: 14px !important; }
  .no-print { display: none !important; }
  section, h2, .cv-entry { break-inside: avoid; page-break-inside: avoid; }
  h2 { break-after: avoid; page-break-after: avoid; }
}`}</style>

      <header style={{ display: "flex", flexDirection: "column", gap: 6, paddingBottom: 16, borderBottom: ornate ? "2px solid currentColor" : "none" }}>
        {!hidden("avatar") && cv.avatar_url ? <img src={cv.avatar_url} alt="" width={72} height={72} style={{ width: 72, height: 72, borderRadius: "50%", objectFit: "cover" }} /> : null}
        <h1 style={{ margin: 0, fontSize: style === "minimal" ? "1.8rem" : "2rem", lineHeight: 1.15, letterSpacing: "-0.01em", fontWeight: style === "minimal" ? 400 : 700 }}>
          {hidden("name") ? tr("cv_an") : cv.name || cv.username}
        </h1>
        {!hidden("headline") && cv.headline ? <p style={{ margin: 0, fontSize: "1.1rem", opacity: 0.85 }}>{cv.headline}</p> : null}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px", marginTop: 4, fontSize: "0.9rem", opacity: 0.8 }}>
          {!hidden("location") && place ? <span>{place}</span> : null}
          {!hidden("birth_date") && cv.birth_date ? <span>{cv.birth_date}</span> : null}
          {!hidden("address") && cv.address ? <span>{cv.address}</span> : null}
          {!hidden("contact") && cv.phone ? <span>{cv.phone}</span> : null}
        </div>
      </header>

      {style === "modern" ? (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr)", gap: 28 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>{blocks.side}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>{blocks.main}</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: style === "minimal" ? 16 : 22 }}>{blocks.main}</div>
      )}

      {error ? <Alert>{error}</Alert> : null}

      <div className="no-print" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
        <Button type="button" onClick={() => window.print()}>{tr("cv_xuat_pdf")}</Button>
        <Select aria-label={tr("cv_kieu")} value={style} onChange={(event) => setStyle(event.target.value as CvStyle)} style={{ maxWidth: 200 }}>
          {CV_STYLES.map((name) => (
            <option key={name} value={name}>{tr(`cv_kieu_${name}`)}</option>
          ))}
        </Select>
      </div>
    </article>
  );
}

function sheetStyle(style: CvStyle): React.CSSProperties {
  const base: React.CSSProperties = { width: "100%", boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 22 };
  if (style === "minimal") return { ...base, padding: "36px 44px", gap: 16 };
  if (style === "modern") return { ...base, padding: "28px 36px", border: "1px solid color-mix(in srgb, var(--line) 25%, transparent)", borderRadius: 12, background: "color-mix(in srgb, var(--line) 3%, transparent)" };
  return { ...base, padding: "28px 36px", border: "1px solid color-mix(in srgb, var(--line) 25%, transparent)", borderRadius: 12, background: "color-mix(in srgb, var(--line) 3%, transparent)" };
}

/** The sections of the CV, each once; the layout decides which column each one goes in. */
function buildBlocks(cv: Cv, hidden: (part: string) => boolean, style: CvStyle): { main: ReactNode[]; side: ReactNode[] } {
  const ornate = style !== "minimal";
  const list = (items: string[]) => (style === "minimal" ? <p style={{ margin: 0 }}>{items.join(", ")}</p> : <Chips items={items} />);
  const main: Array<[string, ReactNode]> = [];
  const side: Array<[string, ReactNode]> = [];

  if (!hidden("summary") && cv.summary) main.push(["summary", <Section key="summary" title={tr("cv_gioi_thieu")} ornate={ornate}><p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{cv.summary}</p></Section>]);
  if (!hidden("experience") && cv.experience.length > 0)
    main.push(["experience", <Section key="experience" title={tr("cv_kinh_nghiem")} ornate={ornate}>
      {cv.experience.map((item, index) => (
        <Entry key={index} title={String(item.title ?? "")} sub={[item.company, item.location, item.type ? tr(`cv_loai_${String(item.type)}`) : ""].filter(Boolean).map(String).join(" · ")} when={range(item.start, item.end)} text={String(item.description ?? "")} />
      ))}
    </Section>]);
  if (!hidden("education") && cv.education.length > 0)
    main.push(["education", <Section key="education" title={tr("cv_hoc_van")} ornate={ornate}>
      {cv.education.map((item, index) => (
        <Entry key={index} title={String(item.school ?? "")} sub={String(item.degree ?? "")} when={range(item.start, item.end)} text={[item.field, item.grade].filter(Boolean).map(String).join(" · ")} />
      ))}
    </Section>]);
  if (!hidden("projects") && cv.projects.length > 0)
    main.push(["projects", <Section key="projects" title={tr("cv_du_an")} ornate={ornate}>
      {cv.projects.map((item, index) => (
        <Entry key={index} title={String(item.name ?? "")} sub={String(item.role ?? "")} when={range(item.start, item.end)} text={String(item.description ?? "")} url={String(item.url ?? "")} />
      ))}
    </Section>]);
  if (!hidden("skills") && cv.skills.length > 0)
    side.push(["skills", <Section key="skills" title={tr("cv_ky_nang")} ornate={ornate}>
      {list(cv.skills.map((item) => [item.name, item.level ? tr(`cv_muc_${String(item.level)}`) : "", item.years ? `${String(item.years)} ${tr("cv_nam")}` : ""].filter(Boolean).map(String).join(" · ")))}
    </Section>]);
  if (!hidden("languages") && cv.languages.length > 0)
    side.push(["languages", <Section key="languages" title={tr("cv_ngon_ngu")} ornate={ornate}>
      {list(cv.languages.map((item) => `${String(item.language ?? item.name ?? "")} · ${String(item.proficiency ?? "")}`))}
    </Section>]);
  if (!hidden("certifications") && cv.certifications.length > 0)
    side.push(["certifications", <Section key="certifications" title={tr("cv_chung_chi")} ornate={ornate}>
      {cv.certifications.map((item, index) => (
        <Entry key={index} title={String(item.name ?? "")} sub={String(item.issuer ?? "")} when={range(item.issued, item.expires)} text="" url={String(item.url ?? "")} />
      ))}
    </Section>]);
  if (!hidden("links") && cv.links.length > 0)
    side.push(["links", <Section key="links" title={tr("cv_lien_ket")} ornate={ornate}>
      {cv.links.map((item, index) => (
        <a key={index} href={String(item.url ?? "")} rel="noopener noreferrer" target="_blank" style={{ display: "block" }}>
          {String(item.label || item.url || "")}
          {item.label && item.url ? <span className="muted"> · {String(item.url)}</span> : null}
        </a>
      ))}
    </Section>]);

  // Classic and minimal keep the reading order in one column; modern puts the side sections on the left.
  if (style === "modern") return { main: main.map(([, node]) => node), side: side.map(([, node]) => node) };
  return { main: [...main, ...side].map(([, node]) => node), side: [] };
}

/** A date range; an open end reads as "present". */
function range(start: unknown, end: unknown): string {
  const from = start ? String(start) : "";
  const to = end ? String(end) : from ? tr("cv_hien_tai") : "";
  return from || to ? `${from}${from && to ? " – " : ""}${to}` : "";
}

function Section({ title, children, ornate }: { title: string; children: ReactNode; ornate: boolean }) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <h2 style={{ margin: 0, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.08em", paddingBottom: 4, borderBottom: ornate ? "1px solid color-mix(in srgb, var(--line) 30%, transparent)" : "none" }}>{title}</h2>
      {children}
    </section>
  );
}

function Entry({ title, sub, when, text, url = "" }: { title: string; sub: string; when: string; text: string; url?: string }) {
  const dates = when.trim() && when.trim() !== "–" ? when : "";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <span>
          <strong>{title}</strong>
          {sub ? <span style={{ opacity: 0.8 }}> · {sub}</span> : null}
        </span>
        {dates ? <span style={{ fontSize: "0.85rem", opacity: 0.7, whiteSpace: "nowrap" }}>{dates}</span> : null}
      </div>
      {text ? <p style={{ margin: 0, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{text}</p> : null}
      {url ? <a href={url} rel="noopener noreferrer" target="_blank" style={{ fontSize: "0.85rem", wordBreak: "break-all" }}>{url}</a> : null}
    </div>
  );
}

function Chips({ items }: { items: string[] }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {items.map((item, index) => (
        <span key={index} style={{ padding: "3px 10px", borderRadius: 999, border: "1px solid color-mix(in srgb, var(--line) 35%, transparent)", fontSize: "0.85rem" }}>{item}</span>
      ))}
    </div>
  );
}
