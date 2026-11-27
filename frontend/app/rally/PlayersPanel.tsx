"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import Button from "@sn/elements/Button";
import { API, PeopleResult, errorText } from "./lib";

export const POLL_MILLISECONDS = 2000;

interface PlayersPanelProps {
  matchId: number;
  onResult: (result: PeopleResult) => void;
}

const LABELS: Record<PeopleResult["status"], string> = {
  idle: "The players are not found yet.",
  running: "Finding the players… this takes a few minutes.",
  done: "The players are found.",
  failed: "The players could not be found. Check that the court is marked.",
};

/** Starts the players job of the match and, while it runs, asks for its status until it is done. */
export default function PlayersPanel({ matchId, onResult }: PlayersPanelProps) {
  const [status, setStatus] = useState<PeopleResult["status"]>("idle");
  const [message, setMessage] = useState("");
  const [polling, setPolling] = useState(false);

  // Opening a match shows what is already known: a finished result, or a job still running.
  useEffect(() => {
    let cancelled = false;
    setMessage("");
    setPolling(false);
    apiFetch<PeopleResult>(`${API}/matches/${matchId}/people`)
      .then((result) => {
        if (cancelled) return;
        setStatus(result.status);
        if (result.status === "done") onResult(result);
        if (result.status === "running") setPolling(true);
      })
      .catch(() => {
        if (!cancelled) setStatus("idle");
      });
    return () => {
      cancelled = true;
    };
  }, [matchId, onResult]);

  useEffect(() => {
    if (!polling) return undefined;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const result = await apiFetch<PeopleResult>(`${API}/matches/${matchId}/people`);
        if (cancelled || result.status === "running") return;
        setStatus(result.status);
        setPolling(false);
        if (result.status === "done") onResult(result);
      } catch (failure) {
        if (!cancelled) {
          setMessage(errorText(failure));
          setPolling(false);
        }
      }
    }, POLL_MILLISECONDS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [polling, matchId, onResult]);

  async function start() {
    setMessage("");
    try {
      await apiFetch(`${API}/matches/${matchId}/people`, { method: "POST" });
      setStatus("running");
      setPolling(true);
    } catch (failure) {
      setMessage(errorText(failure));
    }
  }

  return (
    <div className="rally-players">
      <Button onClick={start} disabled={status === "running"}>Find players</Button>
      <span role="status">{message || LABELS[status]}</span>
    </div>
  );
}
