import { pick, faceWidthOf } from "./geometry";
import {
  EAR_ANCHORS, EYE_LEFT, EYE_RIGHT, FACE_OVAL, MOUTH_INNER, MOUTH_OUTER,
  NOSE_CENTER, NOSE_LEFT, NOSE_RIGHT,
} from "./landmarks";
import type { Point } from "./types";

// The overlay is drawn in the theme's line colour (black or white, whichever the theme picked), with alpha for the softer parts.
let INK = "rgba(0,0,0,0.95)";
let INK_SOFT = "rgba(0,0,0,0.6)";
let INK_FILL = "rgba(0,0,0,0.18)";

/** Reads --line from the page and turns it into the canvas colours (a canvas takes rgba, not color-mix). */
function readInk(): void {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();
  const hex = /^#([0-9a-f]{6})$/i.exec(raw)?.[1];
  const [r, g, b] = hex ? [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)) : [0, 0, 0];
  INK = `rgba(${r},${g},${b},0.95)`;
  INK_SOFT = `rgba(${r},${g},${b},0.6)`;
  INK_FILL = `rgba(${r},${g},${b},0.18)`;
}
const EAR_OFFSET_FRAC = 0.18;
const CENTER_EXTEND_FRAC = 0.35;
const NODE_RADIUS = 3;

type Pts = readonly (Point | undefined)[];

function trace(ctx: CanvasRenderingContext2D, group: readonly Point[]) {
  ctx.beginPath();
  ctx.moveTo(group[0].x, group[0].y);
  for (const p of group.slice(1)) ctx.lineTo(p.x, p.y);
}

function drawPath(ctx: CanvasRenderingContext2D, pts: Pts, indices: readonly number[], opts: { color: string; width: number; closed: boolean; fill?: boolean }) {
  const group = pick(pts, indices);
  if (group.length < 2) return;
  ctx.strokeStyle = opts.color;
  ctx.lineWidth = opts.width;
  trace(ctx, group);
  if (opts.closed) ctx.closePath();
  if (opts.fill) {
    ctx.fillStyle = INK_FILL;
    ctx.fill();
  }
  ctx.stroke();
}

function drawEar(ctx: CanvasRenderingContext2D, pts: Pts, side: "left" | "right", faceWidth: number) {
  const a = EAR_ANCHORS[side];
  const top = pts[a.top];
  const mid = pts[a.mid];
  const bottom = pts[a.bottom];
  if (!top || !mid || !bottom) return;
  const dir = side === "left" ? -1 : 1;
  ctx.strokeStyle = INK;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(top.x, top.y);
  ctx.quadraticCurveTo(mid.x + dir * faceWidth * EAR_OFFSET_FRAC, mid.y, bottom.x, bottom.y);
  ctx.stroke();
}

/**
 * Where the ray first + t * d (t < 0 backwards, t > 1 forwards) leaves the face oval.
 * Returns the nearest crossing in each direction, if any.
 */
export function ovalCrossings(pts: Pts, first: Point, d: Point): { back?: number; forward?: number } {
  const back: number[] = [];
  const forward: number[] = [];
  for (let i = 0; i < FACE_OVAL.length; i++) {
    const pa = pts[FACE_OVAL[i]];
    const pb = pts[FACE_OVAL[(i + 1) % FACE_OVAL.length]];
    if (!pa || !pb) continue;
    const r = { x: pb.x - pa.x, y: pb.y - pa.y };
    const denom = d.x * r.y - d.y * r.x;
    if (Math.abs(denom) < 1e-6) continue;
    const diff = { x: pa.x - first.x, y: pa.y - first.y };
    const t = (diff.x * r.y - diff.y * r.x) / denom;
    const u = (diff.x * d.y - diff.y * d.x) / denom;
    if (u < -1e-6 || u > 1 + 1e-6) continue;
    if (t < 0) back.push(t);
    if (t > 1) forward.push(t);
  }
  return {
    back: back.length ? Math.max(...back) : undefined,
    forward: forward.length ? Math.min(...forward) : undefined,
  };
}

function drawCenterLine(ctx: CanvasRenderingContext2D, pts: Pts, faceWidth: number) {
  const group = pick(pts, NOSE_CENTER);
  if (group.length < 2) return;
  const first = group[0];
  const last = group[group.length - 1];
  const d = { x: last.x - first.x, y: last.y - first.y };
  const len = Math.hypot(d.x, d.y) || 1;
  const ext = faceWidth * CENTER_EXTEND_FRAC;
  const { back, forward } = ovalCrossings(pts, first, d);
  const start = back === undefined
    ? { x: first.x - (d.x / len) * ext, y: first.y - (d.y / len) * ext }
    : { x: first.x + back * d.x, y: first.y + back * d.y };
  const end = forward === undefined
    ? { x: last.x + (d.x / len) * ext, y: last.y + (d.y / len) * ext }
    : { x: first.x + forward * d.x, y: first.y + forward * d.y };
  const seg = (a: Point, b: Point, color: string) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  };
  seg(start, first, INK);
  seg(first, last, INK);
  seg(last, end, INK);
}

/** Draws the face overlay (oval, ears, eyes, nose, centre line, mouth) on a 2D context. */
export function drawFaceOverlay(ctx: CanvasRenderingContext2D, pts: Pts): void {
  readInk();
  const oval = pick(pts, FACE_OVAL);
  if (oval.length < 2) return;
  const faceWidth = faceWidthOf(pts);

  ctx.strokeStyle = INK;
  ctx.lineWidth = 2;
  trace(ctx, oval);
  ctx.closePath();
  ctx.stroke();
  ctx.fillStyle = INK;
  for (const p of oval) {
    ctx.beginPath();
    ctx.arc(p.x, p.y, NODE_RADIUS, 0, 2 * Math.PI);
    ctx.fill();
  }

  drawEar(ctx, pts, "left", faceWidth);
  drawEar(ctx, pts, "right", faceWidth);
  drawPath(ctx, pts, EYE_LEFT, { color: INK, width: 2, closed: true, fill: true });
  drawPath(ctx, pts, EYE_RIGHT, { color: INK, width: 2, closed: true, fill: true });
  drawPath(ctx, pts, NOSE_LEFT, { color: INK, width: 2, closed: false });
  drawPath(ctx, pts, NOSE_RIGHT, { color: INK, width: 2, closed: false });
  drawCenterLine(ctx, pts, faceWidth);
  drawPath(ctx, pts, MOUTH_OUTER, { color: INK, width: 2, closed: true });
  drawPath(ctx, pts, MOUTH_INNER, { color: INK_SOFT, width: 1.5, closed: true });
}
