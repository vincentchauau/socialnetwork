"use client";

import { type CSSProperties, type ReactNode } from "react";

import Button from "@sn/elements/Button";
import { tr } from "../i18n";

export const noWrap: CSSProperties = { whiteSpace: "nowrap", flex: "none", width: "auto" };

export type Toggle = "mic" | "camera" | "share";
type Props = {
  title: string;
  mic: boolean;
  camera: boolean;
  share: boolean;
  onToggle: (what: Toggle) => void;
  /** The buttons of the moment: Join before the call; Leave and End in the call. */
  children: ReactNode;
};

/** The bar above the tiles, the same before the call and in it: the title, the three switches, then the buttons of the moment. */
export function CallBar({ title, mic, camera, share, onToggle, children }: Props) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", minWidth: 0, width: "100%" }}>
      <strong>{title}</strong>
      <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <Button type="button" size="sm" style={noWrap} variant={mic ? "primary" : "secondary"} aria-pressed={mic} onClick={() => onToggle("mic")}>
          {mic ? tr("rm_mic_bat") : tr("rm_mic_tat")}
        </Button>
        <Button type="button" size="sm" style={noWrap} variant={camera ? "primary" : "secondary"} aria-pressed={camera} onClick={() => onToggle("camera")}>
          {camera ? tr("rm_cam_bat") : tr("rm_cam_tat")}
        </Button>
        <Button type="button" size="sm" style={noWrap} variant={share ? "primary" : "secondary"} aria-pressed={share} onClick={() => onToggle("share")}>
          {share ? tr("rm_dung_chia_se") : tr("rm_chia_se_man_hinh")}
        </Button>
        {children}
      </span>
    </div>
  );
}

export const TILE_RATIO = 4 / 3; // width : height of a tile (landscape, like most webcams)
export const TILE_GAP = 8;

/** The look of a tile: in the grid it is 4:3 (like a webcam), and on the full screen it takes all of it. */
export const frame = (focused: boolean, extra: CSSProperties = {}): CSSProperties => ({
  position: "relative", borderRadius: focused ? 0 : 8, overflow: "hidden", background: "var(--solid-1)", display: "flex", alignItems: "center", justifyContent: "center",
  border: "2px solid transparent", width: "100%", ...(focused ? { height: "100vh" } : { aspectRatio: "4 / 3" }), ...extra,
});

export const label: CSSProperties = { position: "absolute", left: 8, bottom: 8, padding: "2px 8px", borderRadius: 4, background: "color-mix(in srgb, var(--line) 60%, transparent)", color: "var(--solid-0)", fontSize: 13 };

/** One tile, the same before the call and in it: its frame, its border while it speaks, its name. */
export function Tile({ focused, speaking = false, style, name, children }: {
  focused: boolean;
  speaking?: boolean;
  style?: CSSProperties;
  name: ReactNode;
  children: ReactNode;
}) {
  return (
    <div style={frame(focused, { borderColor: speaking ? "var(--line)" : "transparent", ...style })}>
      {children}
      <span style={label}>{name}</span>
    </div>
  );
}

/** The grid of the tiles: `columns` tiles of `tileWidth` pixels, each 4:3, centred. */
export function tileGrid(columns: number, tileWidth: number): CSSProperties {
  return {
    display: "grid", gap: TILE_GAP, justifyContent: "center",
    gridTemplateColumns: `repeat(${columns}, ${tileWidth}px)`, gridAutoRows: `${(tileWidth * 3) / 4}px`,
  };
}
