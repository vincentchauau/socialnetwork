"use client";

import { FormEvent, useState } from "react";

import {
  ChatLine,
  GameState,
  MAX_CHAT_LENGTH,
  MIN_PLAYERS,
  actionLabel,
  canTarget,
  describeEvent,
  phaseLabel,
  roleHint,
  roleLabel,
  statusLine,
} from "./game";

export interface RoomBoardProps {
  state: GameState;
  username: string;
  chat: readonly ChatLine[];
  connected: boolean;
  busy: boolean;
  notice: string | null;
  onAction: (target: number) => void;
  onVote: (target: number | null) => void;
  onChat: (content: string) => void;
  onAdvance: () => void;
  onStart: () => void;
  onJoin: () => void;
  onLeave: () => void;
}

const ADVANCE_LABELS: Record<string, string> = {
  night: "Resolve the night now",
  day: "End discussion and vote",
  vote: "Count the votes now",
};

function ChatPanel({ state, chat, onChat }: Pick<RoomBoardProps, "state" | "chat" | "onChat">) {
  const [draft, setDraft] = useState("");
  const scope = state.you?.chat ?? null;

  function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || scope === null) return;
    onChat(content);
    setDraft("");
  }

  return (
    <section className="stack" aria-labelledby="chat-heading">
      <h2 id="chat-heading" style={{ fontSize: "1.1rem", margin: 0 }}>
        Chat
      </h2>
      <ul
        role="log"
        aria-live="polite"
        className="stack card"
        style={{ listStyle: "none", margin: 0, minHeight: 120, maxHeight: 280, overflowY: "auto" }}
      >
        {chat.length === 0 && <li className="muted">No messages yet.</li>}
        {chat.map((line) => (
          <li key={line.key} style={{ overflowWrap: "anywhere" }}>
            {line.scope === "wolves" && <span className="muted">[wolves] </span>}
            <strong>{line.username}</strong>: {line.content}
          </li>
        ))}
      </ul>
      {scope === null ? (
        <p className="muted" style={{ margin: 0 }}>
          You cannot speak right now.
        </p>
      ) : (
        <form className="row" onSubmit={submit}>
          <input
            aria-label={scope === "wolves" ? "Message to the wolves (private)" : "Message"}
            placeholder={scope === "wolves" ? "Wolves only" : "Write a message"}
            maxLength={MAX_CHAT_LENGTH}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button disabled={draft.trim() === ""}>Send</button>
        </form>
      )}
    </section>
  );
}

export default function RoomBoard(props: RoomBoardProps) {
  const { state, username, connected, busy, notice } = props;
  const you = state.you;
  const isHost = you !== null && you.id === state.host_id;
  const isLobby = state.phase === "lobby";
  const advanceLabel = ADVANCE_LABELS[state.phase];

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>{phaseLabel(state.phase)}</h1>
        <a href="/">← Home</a>
      </div>

      <p className="muted" aria-live="polite" style={{ margin: 0 }}>
        {you === null ? "Viewing" : connected ? "Connected" : "Connecting…"} as {username}
        {state.day > 0 && state.phase !== "finished" ? ` · Day ${state.day}` : ""}
      </p>
      {notice && (
        <p role="alert" className="error">
          {notice}
        </p>
      )}

      {you === null && (
        <div className="card stack">
          <p style={{ margin: 0 }}>This game has not started. Join it to play.</p>
          <button disabled={busy || state.players.length >= 12} onClick={props.onJoin}>
            Join this room
          </button>
        </div>
      )}

      {you !== null && !isLobby && (
        <section className="card stack" aria-labelledby="role-heading">
          <h2 id="role-heading" style={{ fontSize: "1.1rem", margin: 0 }}>
            Your role: {roleLabel(you.role)}
          </h2>
          <p style={{ margin: 0 }}>{roleHint(you.role)}</p>
          <p style={{ margin: 0 }} aria-live="polite">
            <strong>{statusLine(state)}</strong>
          </p>
          {you.inspections && you.inspections.length > 0 && (
            <ul style={{ margin: 0 }}>
              {you.inspections.map((result) => {
                const target = state.players.find((p) => p.id === result.id);
                return (
                  <li key={result.id}>
                    {target?.username ?? "Player"} is {result.is_werewolf ? "a werewolf" : "not a werewolf"}.
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      {state.phase === "finished" && (
        <section className="card stack" aria-labelledby="over-heading">
          <h2 id="over-heading" style={{ fontSize: "1.1rem", margin: 0 }}>
            {state.winner === "village" ? "The village wins!" : "The werewolves win!"}
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            All roles are revealed. Your result is saved in your game history.
          </p>
        </section>
      )}

      <section aria-labelledby="players-heading" className="stack">
        <h2 id="players-heading" style={{ fontSize: "1.1rem", margin: 0 }}>
          Players ({state.players.length})
        </h2>
        {state.players.length === 0 && <p className="muted">Nobody is here.</p>}
        <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {state.players.map((player) => {
            const chosen = you?.target === player.id;
            const showTarget = canTarget(state, player);
            return (
              <li
                key={player.id}
                className="card row"
                style={{
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  opacity: player.alive ? 1 : 0.6,
                }}
              >
                <span style={{ overflowWrap: "anywhere" }}>
                  <strong>{player.username}</strong>
                  {player.id === you?.id ? " (you)" : ""}
                  {player.is_host ? " · host" : ""}
                  {!isLobby && !player.alive ? " · dead" : ""}
                  {player.role ? ` · ${roleLabel(player.role)}` : ""}
                </span>
                {you?.pending && showTarget && (
                  <button
                    className={chosen ? undefined : "secondary"}
                    aria-pressed={chosen}
                    disabled={busy}
                    aria-label={`${actionLabel(you.pending)} ${player.username}`}
                    onClick={() =>
                      you.pending === "vote" ? props.onVote(player.id) : props.onAction(player.id)
                    }
                  >
                    {actionLabel(you.pending)}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        {you?.pending === "vote" && (
          <button className="secondary" onClick={() => props.onVote(null)}>
            Abstain
          </button>
        )}
      </section>

      <div className="row" style={{ flexWrap: "wrap" }}>
        {isHost && isLobby && (
          <button
            disabled={busy || state.players.length < MIN_PLAYERS}
            onClick={props.onStart}
            title={state.players.length < MIN_PLAYERS ? `Needs ${MIN_PLAYERS} players` : undefined}
          >
            Start game ({state.players.length}/{MIN_PLAYERS}+)
          </button>
        )}
        {isHost && advanceLabel && (
          <button className="secondary" onClick={props.onAdvance}>
            {advanceLabel}
          </button>
        )}
        {you !== null && (
          <button className="secondary" disabled={busy} onClick={props.onLeave}>
            Leave room
          </button>
        )}
      </div>
      {isHost && isLobby && state.players.length < MIN_PLAYERS && (
        <p className="muted" style={{ margin: 0 }}>
          Waiting for at least {MIN_PLAYERS} players. Share the page address so others can join.
        </p>
      )}

      {you !== null && <ChatPanel state={state} chat={props.chat} onChat={props.onChat} />}

      <section aria-labelledby="log-heading" className="stack">
        <h2 id="log-heading" style={{ fontSize: "1.1rem", margin: 0 }}>
          Game log
        </h2>
        {state.events.length === 0 && <p className="muted">Nothing has happened yet.</p>}
        <ul style={{ margin: 0 }}>
          {state.events.map((event, index) => (
            <li key={index}>{describeEvent(event)}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
