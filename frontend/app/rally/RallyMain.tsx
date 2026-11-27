"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { apiFetch, apiForm } from "@sn/api";
import Button from "@sn/elements/Button";
import CourtPicker from "./CourtPicker";
import {
  API,
  MatchDetail,
  MatchSummary,
  NO_MARKS,
  Marks,
  Point,
  Side,
  canSave,
  errorText,
  formatMs,
  hitsOf,
  MAX_HITS,
} from "./lib";

/** Milliseconds of the video's current time, rounded. */
function currentMs(video: HTMLVideoElement | null): number {
  return Math.round((video?.currentTime ?? 0) * 1000);
}

export default function RallyMain() {
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [matchId, setMatchId] = useState<number | null>(null);
  const [detail, setDetail] = useState<MatchDetail | null>(null);
  const [marks, setMarks] = useState<Marks>(NO_MARKS);
  const [hits, setHits] = useState("0");
  const [winner, setWinner] = useState<Side>("A");
  const [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  // A new array only when the match is loaded again: the court picker resets its corners when this changes.
  const court = useMemo<Point[] | null>(
    () => (detail?.court ? detail.court.map(([x, y]) => [x, y] as Point) : null),
    [detail?.court],
  );

  const loadMatches = useCallback(async (selectId?: number) => {
    try {
      const list = await apiFetch<MatchSummary[]>(`${API}/matches`);
      setMatches(list);
      const chosen = selectId ?? list[0]?.id ?? null;
      setMatchId(chosen);
    } catch (failure) {
      setError(errorText(failure));
    }
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    try {
      setDetail(await apiFetch<MatchDetail>(`${API}/matches/${id}`));
    } catch (failure) {
      setError(errorText(failure));
    }
  }, []);

  useEffect(() => {
    loadMatches();
  }, [loadMatches]);

  useEffect(() => {
    if (matchId === null) {
      setDetail(null);
      return;
    }
    setMarks(NO_MARKS);
    loadDetail(matchId);
  }, [matchId, loadDetail]);

  async function upload(form: HTMLFormElement) {
    const data = new FormData(form);
    setError("");
    try {
      const created = await apiForm<MatchSummary>(`${API}/matches`, data);
      form.reset();
      await loadMatches(created.id);
    } catch (failure) {
      setError(errorText(failure));
    }
  }

  async function saveRally() {
    if (matchId === null || !canSave(marks) || marks.startMs === null || marks.endMs === null) return;
    setError("");
    try {
      await apiFetch(`${API}/matches/${matchId}/rallies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start_ms: marks.startMs, end_ms: marks.endMs, hits: hitsOf(hits), winner }),
      });
      setMarks(NO_MARKS);
      await loadDetail(matchId);
    } catch (failure) {
      setError(errorText(failure));
    }
  }

  async function deleteRally(rallyId: number) {
    if (matchId === null) return;
    try {
      await apiFetch(`${API}/matches/${matchId}/rallies/${rallyId}`, { method: "DELETE" });
      await loadDetail(matchId);
    } catch (failure) {
      setError(errorText(failure));
    }
  }

  function markEnd() {
    const endMs = currentMs(video.current);
    if (marks.startMs === null || endMs <= marks.startMs) {
      setError("Mark the start first, then an end after it.");
      return;
    }
    setError("");
    setMarks({ startMs: marks.startMs, endMs });
  }

  return (
    <div className="rally">
      <div className="rally-bar">
        <select aria-label="Match" value={matchId ?? ""} onChange={(event) => setMatchId(Number(event.target.value))}>
          {matches.map((match) => (
            <option key={match.id} value={match.id}>{match.name}</option>
          ))}
        </select>
      </div>

      <form
        className="rally-upload"
        onSubmit={(event) => {
          event.preventDefault();
          upload(event.currentTarget);
        }}
      >
        <input name="name" type="text" required maxLength={100} placeholder="Match name" aria-label="Match name" />
        <input name="video" type="file" required accept="video/mp4,video/webm,video/quicktime" aria-label="Video file" />
        <Button type="submit" variant="primary">Upload match</Button>
      </form>

      {matchId !== null && (
        <>
          <CourtPicker
            matchId={matchId}
            src={`${API}/matches/${matchId}/video`}
            initial={court}
            videoRef={video}
          />
          <div className="rally-marks">
            <Button onClick={() => setMarks({ startMs: currentMs(video.current), endMs: null })}>
              Mark start ({marks.startMs === null ? "-" : formatMs(marks.startMs)})
            </Button>
            <Button onClick={markEnd}>Mark end at current time</Button>
            <label>
              Hits
              <input type="number" min={0} max={MAX_HITS} value={hits} onChange={(event) => setHits(event.target.value)} />
            </label>
            <label>
              Winner
              <select value={winner} onChange={(event) => setWinner(event.target.value as Side)}>
                <option value="A">Side A</option>
                <option value="B">Side B</option>
              </select>
            </label>
            <Button variant="primary" disabled={!canSave(marks)} onClick={saveRally}>Save rally</Button>
          </div>
        </>
      )}

      {error && <p className="rally-error" role="alert">{error}</p>}

      {detail && (
        <>
          <div className="rally-stats">
            <span>Rallies <b>{detail.stats.rallies}</b></span>
            <span>Score A <b>{detail.stats.score.A}</b></span>
            <span>Score B <b>{detail.stats.score.B}</b></span>
            <span>Avg hits <b>{detail.stats.avg_hits}</b></span>
            <span>Max hits <b>{detail.stats.max_hits}</b></span>
          </div>
          <table className="rally-table">
            <thead>
              <tr><th>#</th><th>Start</th><th>End</th><th>Duration</th><th>Hits</th><th>Winner</th><th /></tr>
            </thead>
            <tbody>
              {detail.rallies.map((rally) => (
                <tr key={rally.id}>
                  <td>{rally.number}</td>
                  <td>{formatMs(rally.start_ms)}</td>
                  <td>{formatMs(rally.end_ms)}</td>
                  <td>{formatMs(rally.end_ms - rally.start_ms)}</td>
                  <td>{rally.hits}</td>
                  <td>{rally.winner}</td>
                  <td><Button size="sm" onClick={() => deleteRally(rally.id)}>Delete</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
