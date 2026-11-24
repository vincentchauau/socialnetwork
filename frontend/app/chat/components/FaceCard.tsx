"use client";

import { useState } from "react";

import { type FaceDeps, defaultFaceDeps } from "../../face/lib/mediapipe";
import { positionHint } from "../../face/lib/geometry";
import type { Scores } from "../../face/lib/types";
import { useFaceTracker } from "../../face/hooks/useFaceTracker";
import Alert from "@sn/elements/Alert";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import CheckBox from "@sn/elements/CheckBox";

const pct = (value: number | null): string => (value === null ? "–" : `${value}%`);

/**
 * The face-symmetry meter in a card: the camera and the model run in this browser and nothing of the picture leaves it. Only the
 * numbers are kept, and only when the person presses the button.
 */
export default function FaceCard({ title, saving, error, onSave, deps = defaultFaceDeps }: {
  title: string;
  saving: boolean;
  error: string | null;
  onSave: (scores: Scores) => void;
  deps?: FaceDeps;
}) {
  const [draw, setDraw] = useState(true);
  const tracker = useFaceTracker(deps, draw);
  const { status, scores } = tracker;
  const idle = status === "idle";
  const rows: [string, string][] = scores
    ? [
        [tr("fc_doi_xung"), pct(scores.symmetry)],
        [tr("fc_mat_2"), pct(scores.eye)],
        [tr("fc_mui_2"), pct(scores.nose)],
        [tr("fc_mieng_2"), pct(scores.mouth)],
        [tr("fc_goc"), scores.angle === null ? "–" : `${scores.angle}°`],
        [tr("fc_vi_tri"), positionHint(scores.angle) === "ok" ? tr("fc_ban_ngoi_thang") : tr("fc_hay_ngoi_thang_nhin_thang_vao")],
      ]
    : [];
  return (
    <div className="cw-bubble cw-card" role="group" aria-label={title}>
      <strong>{title}</strong>
      <div hidden={idle} className="cw-face-stage">
        <video ref={tracker.videoRef} playsInline muted autoPlay aria-hidden="true" className="cw-face-video" />
        <canvas ref={tracker.canvasRef} role="img" aria-label={tr("fc_hinh_camera")} className="cw-face-canvas" />
      </div>
      {status === "starting" && <p role="status" className="cw-room-sub">{tr("fc_dang_bat_camera")}</p>}
      <Alert>{tracker.error ?? error}</Alert>
      {scores ? (
        <dl className="cw-face-scores">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        !idle && status === "running" && <p className="cw-room-sub">{tr("fc_chua_thay_khuon_mat")}</p>
      )}
      <p className="cw-room-sub">{tr("fc_chi_luu_con_so")}</p>
      <div className="cw-card-actions">
        {idle ? (
          <Button type="button" size="sm" onClick={() => void tracker.start()}>{tr("fc_bat_camera")}</Button>
        ) : (
          <Button type="button" size="sm" variant="secondary" onClick={tracker.stop}>{tr("fc_tat_camera")}</Button>
        )}
        <Button type="button" size="sm" disabled={!scores || saving} onClick={() => scores && onSave(scores)}>{saving ? tr("fc_dang_luu") : tr("fc_luu_ket_qua")}</Button>
        <CheckBox checked={draw} onChange={setDraw} label={tr("fc_ve_duong_net")} />
      </div>
    </div>
  );
}
