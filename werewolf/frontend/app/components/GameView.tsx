import { abilityIcon, FACTION_ICON, PHASE_INFO } from "../lib/theme";
import type { Game, RoomState } from "../lib/types";
import ActionPanel, { type PickKind } from "./ActionPanel";
import Avatar from "./Avatar";
import ChatPanel from "./ChatPanel";
import Countdown from "./Countdown";
import EventBanner from "./EventBanner";
import HelpSheet from "./HelpSheet";
import PerspectivePanel from "./PerspectivePanel";
import PlayerTile from "./PlayerTile";
import RecapCard from "./RecapCard";
import ResultView from "./ResultView";

export interface GameHandlers {
  onPick: (target: number, kind: PickKind) => void;
  onForce: () => void;
  onRematch: () => void;
  onReset: () => void;
  onLeave: () => void;
  onSendChat: (text: string, target: number) => Promise<boolean>;
}

interface Props extends GameHandlers {
  room: RoomState;
  game: Game;
  busy: boolean;
}

function PhaseBanner({ room, game }: { room: RoomState; game: Game }) {
  const info = PHASE_INFO[game.phase] ?? PHASE_INFO.settle;
  return (
    <header className={`ww-phase ww-phase-${info.tone}`}>
      <span className="ww-big" aria-hidden="true">
        {info.icon}
      </span>
      <h1>{info.title(game.night)}</h1>
      <p className="muted">
        {room.title} · 🔑 {room.code}
      </p>
      {game.timer && !game.gameOver && <Countdown timer={game.timer} />}
    </header>
  );
}

function RoleCard({ game }: { game: Game }) {
  const { me } = game;
  return (
    <section className="card ww-role" aria-label="Vai của bạn">
      <Avatar name={me.name} size={64} tone={me.faction.code.toLowerCase()} badge={FACTION_ICON[me.faction.code]} dead={!me.alive} />
      <div>
        <h2>🎭 {me.name}</h2>
        <p>
          {FACTION_ICON[me.faction.code]} {me.faction.label} · {abilityIcon(me.ability.code)} {me.ability.label}
          {me.alive ? "" : " · 💀 Đã chết"}
        </p>
      </div>
    </section>
  );
}

function PlayerGrid({ game }: { game: Game }) {
  const alive = game.players.filter((p) => p.alive).length;
  return (
    <section className="card" aria-label="Người chơi">
      <h2>
        👥 {alive}/{game.players.length} còn sống
      </h2>
      <ul className="ww-tiles ww-plain-list">
        {game.players.map((p) => (
          <PlayerTile key={p.id} player={p} isYou={p.id === game.me.id} />
        ))}
      </ul>
    </section>
  );
}

export default function GameView({ room, game, busy, onPick, onForce, onRematch, onReset, onLeave, onSendChat }: Props) {
  return (
    <div className="stack ww-game">
      <PhaseBanner room={room} game={game} />
      <div className="ww-columns">
        <div className="stack">
          <RecapCard recap={game.recap} />
          {game.gameOver ? (
            <ResultView room={room} game={game} busy={busy} onRematch={onRematch} onReset={onReset} />
          ) : (
            <>
              <EventBanner event={game.event} />
              <ActionPanel game={game} busy={busy} onPick={onPick} />
            </>
          )}
          <RoleCard game={game} />
        </div>
        <PlayerGrid game={game} />
      </div>
      <ChatPanel game={game} onSend={onSendChat} />
      <PerspectivePanel code={room.code} game={game} />
      {room.isHost && !game.gameOver && (
        <button type="button" className="danger" disabled={busy || game.waitingFor === 0} onClick={onForce}>
          ⏭ Bỏ qua người chưa chọn
        </button>
      )}
      <div className="row ww-wrap ww-center">
        <HelpSheet />
        <button type="button" className="secondary" onClick={onLeave} disabled={busy}>
          🚪 Rời phòng
        </button>
      </div>
    </div>
  );
}
