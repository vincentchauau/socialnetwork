"use client";

import { useState } from "react";

import { useFaceTracker } from "../hooks/useFaceTracker";
import { useHistory } from "../hooks/useHistory";
import { defaultFaceDeps } from "../lib/mediapipe";
import type { FaceDeps } from "../lib/mediapipe";
import History from "./History";
import ScorePanel from "./ScorePanel";

export default function FaceApp({ deps = defaultFaceDeps }: { deps?: FaceDeps }) {
  const [drawEnabled, setDrawEnabled] = useState(true);
  const tracker = useFaceTracker(deps, drawEnabled);
  const history = useHistory();
  const { status, scores, error } = tracker;
  const isIdle = status === "idle";

  return (
    <div className="stack">
      <h1>Phân tích đối xứng khuôn mặt</h1>
      <p className="muted">Hình ảnh không rời khỏi thiết bị của bạn. Chỉ các điểm số bạn chủ động lưu mới được gửi lên máy chủ.</p>

      <section className="face-card" aria-label="Camera">
        <div className="face-stage" hidden={isIdle}>
          <video ref={tracker.videoRef} className="face-video" playsInline muted autoPlay aria-hidden="true" />
          <canvas ref={tracker.canvasRef} className="face-canvas" role="img" aria-label="Hình camera kèm đường nét khuôn mặt" />
        </div>
        {isIdle && <p className="muted">Camera đang tắt.</p>}
        {status === "starting" && <p role="status" className="muted">Đang bật camera và tải mô hình…</p>}
        {error && <p role="alert" className="error">{error}</p>}
        <div className="face-actions">
          {isIdle ? (
            <button type="button" onClick={() => void tracker.start()}>Bật camera</button>
          ) : (
            <button type="button" onClick={tracker.stop}>Tắt camera</button>
          )}
          <label className="face-toggle">
            <input type="checkbox" checked={drawEnabled} onChange={(e) => setDrawEnabled(e.target.checked)} />
            Bật vẽ
          </label>
        </div>
      </section>

      <ScorePanel scores={scores} />

      <section className="face-card" aria-label="Lưu kết quả">
        <button type="button" disabled={!scores || history.isSaving} onClick={() => scores && void history.save(scores)}>
          {history.isSaving ? "Đang lưu…" : "Lưu kết quả"}
        </button>
        <p className="muted">Chỉ lưu các con số, không lưu hình ảnh. Nút sáng lên khi đã nhận diện được khuôn mặt.</p>
        {history.justSaved && <p role="status">Đã lưu kết quả.</p>}
      </section>

      <History history={history} />
      <a href="/">← Trang chủ</a>
    </div>
  );
}
