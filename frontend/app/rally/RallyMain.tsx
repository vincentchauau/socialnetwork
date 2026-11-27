"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { apiFetch, apiForm } from "@sn/api";
import Button from "@sn/elements/Button";
import CourtPicker from "./CourtPicker";
import PlayersPanel from "./PlayersPanel";
import { API, MatchSummary, PeopleSample, errorText, sampleAt } from "./lib";

export default function RallyMain() {
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [matchId, setMatchId] = useState<number | null>(null);
  const [samples, setSamples] = useState<PeopleSample[]>([]);
  const [nowMs, setNowMs] = useState(0);
  const [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const sample = useMemo(() => sampleAt(samples, nowMs), [samples, nowMs]);

  const loadMatches = useCallback(async (selectId?: number) => {
    try {
      const list = await apiFetch<MatchSummary[]>(`${API}/matches`);
      setMatches(list);
      setMatchId(selectId ?? list[0]?.id ?? null);
    } catch (failure) {
      setError(errorText(failure));
    }
  }, []);

  useEffect(() => {
    loadMatches();
  }, [loadMatches]);

  useEffect(() => {
    setSamples([]);
    setNowMs(0);
  }, [matchId]);

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
            src={`${API}/matches/${matchId}/video`}
            videoRef={video}
            sample={sample}
            onTime={setNowMs}
          />
          <PlayersPanel matchId={matchId} onSamples={setSamples} />
        </>
      )}

      {error && <p className="rally-error" role="alert">{error}</p>}
    </div>
  );
}
