"use client";

import { useState } from "react";

import { useFaceTracker } from "../hooks/useFaceTracker";
import { useHistory } from "../hooks/useHistory";
import { defaultFaceDeps } from "../lib/mediapipe";
import type { FaceDeps } from "../lib/mediapipe";
import History from "./History";
import ScorePanel from "./ScorePanel";
import Button from "@sn/elements/Button";
import { tr } from "../i18n";
import Link from "next/link";
import CheckBox from "@sn/elements/CheckBox";
import { useSize } from "../../chat/components/useSize";

export default function FaceApp({ deps = defaultFaceDeps }: { deps?: FaceDeps }) {
  const [drawEnabled, setDrawEnabled] = useState(true);
  const tracker = useFaceTracker(deps, drawEnabled);
  const history = useHistory();
  const { status, scores, error } = tracker;
  const isIdle = status === "idle";
  // The picture is the largest 4:3 that fits the width and the room left in the Page panel, so it never scrolls out of it.
  const [fitRef, fit] = useSize<HTMLDivElement>();
  const stageWidth = fit.height > 0 ? Math.min(fit.width, fit.height * (4 / 3)) : undefined;

  return (
    <div className="stack">
      <section className="face-card face-layout" aria-label="Camera">
      <div className="face-camera">
        <div ref={fitRef} className="face-fit">
          <div className="face-stage" hidden={isIdle} style={{ width: stageWidth ?? "auto" }}>
            <video ref={tracker.videoRef} className="face-video" playsInline muted autoPlay aria-hidden="true" />
            <canvas ref={tracker.canvasRef} className="face-canvas" role="img" aria-label={tr("hinh_camera_kem_duong_net_khuon")} />
          </div>
        </div>
      </div>

      <div className="stack">
        <div className="face-actions">
          {isIdle ? (
            <Button type="button" onClick={() => void tracker.start()}>{tr("bat_camera")}</Button>
          ) : (
            <Button type="button" onClick={tracker.stop}>{tr("tat_camera")}</Button>
          )}
          <CheckBox checked={drawEnabled} onChange={setDrawEnabled} label={tr("bat_ve")} />
        </div>
        {isIdle && <p className="muted">{tr("camera_dang_tat")}</p>}
        {status === "starting" && <p role="status" className="muted">{tr("dang_bat_camera_va_tai_mo")}</p>}
        {error && <p role="alert" className="error">{error}</p>}
        <ScorePanel scores={scores} />

        <section className="face-card" aria-label={tr("luu_ket_qua")}>
          <Button type="button" disabled={!scores || history.isSaving} onClick={() => scores && void history.save(scores)}>
            {history.isSaving ? tr("dang_luu") : tr("luu_ket_qua")}
          </Button>
          <p className="muted">{tr("chi_luu_cac_con_so_khong")}</p>
          {history.justSaved && <p role="status">{tr("da_luu_ket_qua")}</p>}
        </section>

        <History history={history} />
      </div>
      </section>
    </div>
  );
}
