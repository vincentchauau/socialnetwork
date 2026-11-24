"use client";

import { type CSSProperties, useState } from "react";

import Button from "@sn/elements/Button";
import TextBox from "@sn/elements/TextBox";
import { tr } from "../i18n";

/** A round picture of a room or a person: the picture when there is one, else the first letter of the name. */
const hueOf = (name: string): number => [...name].reduce((sum, char) => (sum * 31 + char.charCodeAt(0)) % 360, 7);

export default function AvatarImage({ url, name, size = 24 }: { url?: string | null; name: string; size?: number }) {
  const style: CSSProperties = {
    width: size, height: size, borderRadius: "50%", flex: "none", display: "inline-flex", alignItems: "center", justifyContent: "center", overflow: "hidden",
    border: "1px solid color-mix(in srgb, var(--line) 35%, transparent)", fontSize: Math.round(size * 0.5), fontWeight: 600, verticalAlign: "middle", marginRight: 6,
  };
  // eslint-disable-next-line @next/next/no-img-element -- a picture of somebody's own address, small and decorative (the name stands next to it)
  if (url) return <img src={url} alt="" width={size} height={size} style={{ ...style, objectFit: "cover" }} />;
  return <span aria-hidden="true" style={{ ...style, background: `var(--solid-${1 + (hueOf(name) % 3)})`, color: "var(--line)" }}>{name.trim().charAt(0).toUpperCase()}</span>;
}

const SIDE_PX = 96;

/** A picked image, shrunk to a small square JPEG that is kept inline (an address is not needed). */
export async function shrink(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement("canvas");
  canvas.width = SIDE_PX;
  canvas.height = SIDE_PX;
  const side = Math.min(bitmap.width, bitmap.height);
  canvas.getContext("2d")?.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, SIDE_PX, SIDE_PX);
  return canvas.toDataURL("image/jpeg", 0.8);
}

/** The picture of a room: what it has now (or the letter that stands for it), Upload (from a file), Remove. */
export function AvatarPicker({ value, name, onChange }: { value: string; name: string; onChange: (value: string) => void }) {
  const [error, setError] = useState<string | null>(null);
  async function pick(file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      onChange(await shrink(file));
    } catch {
      setError(tr("rm_anh_khong_doc_duoc"));
    }
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 12, fontWeight: 600 }}>{tr("rm_anh_dai_dien")}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <AvatarImage url={value} name={name || "?"} size={40} />
        <label>
          <span className="sr-only">{tr("rm_tai_anh_len")}</span>
          <TextBox type="file" accept="image/*" aria-label={tr("rm_tai_anh_len")} onChange={(event) => void pick(event.target.files?.[0])} />
        </label>
        {value && <Button type="button" size="sm" variant="secondary" onClick={() => onChange("")}>{tr("rm_go_anh")}</Button>}
      </div>
      {error && <span role="alert" className="cw-room-sub">{error}</span>}
    </div>
  );
}
