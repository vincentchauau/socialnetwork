import { abilityIcon, FACTION_ICON } from "../lib/theme";
import type { RoomState } from "../lib/types";
import Avatar from "./Avatar";
import HelpSheet from "./HelpSheet";

interface Props {
  room: RoomState;
  busy: boolean;
  onAddBots: (count: number) => void;
  onStart: () => void;
  onLeave: () => void;
}

/** Lobby: who is seated (only your own role is shown), host controls, leave. */
export default function LobbyView({ room, busy, onAddBots, onStart, onLeave }: Props) {
  const missing = Math.max(0, room.minPlayers - room.members.length);
  const full = room.members.length >= room.maxPlayers;
  const humans = room.members.filter((m) => !m.isBot).length;

  return (
    <div className="stack">
      <header className="ww-hero">
        <span className="ww-big" aria-hidden="true">
          🏕️
        </span>
        <h1>{room.title || `Phòng ${room.code}`}</h1>
        <p className="ww-code" aria-label={`Mã phòng ${room.code.split("").join(" ")}`}>
          🔑 {room.code}
        </p>
        <p className="muted">Chia mã này cho bạn bè để họ vào phòng.</p>
        <p className="muted">
          {room.timer ? `⏱ ${room.timer}s/lượt` : "⏱ Không giới hạn"} · {room.events ? "🎴 Có thẻ sự kiện" : "Không thẻ sự kiện"} ·{" "}
          {room.deadTalk ? "💀 Người chết chat chung" : "💀 Người chết chat riêng"} · {room.listed ? "📣 Công khai" : "🔒 Chỉ vào bằng mã"}
        </p>
      </header>

      <section className="card" aria-label={`${room.members.length} người`}>
        <h2>👥 {room.members.length} người</h2>
        <ul className="ww-members ww-plain-list">
          {room.members.map((member) => (
            <li key={member.seat} className="ww-member">
              <Avatar
                name={member.name}
                size={56}
                tone={member.isYou ? member.faction?.code.toLowerCase() : undefined}
                badge={member.isYou && member.faction ? FACTION_ICON[member.faction.code] : undefined}
              />
              <span className="ww-tile-name">{member.isYou ? `${member.name} ★` : member.name}</span>
              <span aria-hidden="true">
                {member.isHost ? "👑" : ""}
                {member.isBot ? "🤖" : ""}
              </span>
              <span className="sr-only">
                {member.isHost ? "chủ phòng " : ""}
                {member.isBot ? "bot " : ""}
                {member.isYou ? "bạn" : ""}
              </span>
              {member.isYou && member.faction && member.ability && (
                <span className="muted">
                  {FACTION_ICON[member.faction.code]} {member.faction.label} · {abilityIcon(member.ability.code)} {member.ability.label}
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>

      {room.isHost ? (
        <section className="card stack" aria-label="Chủ phòng">
          <h2>👑 Chủ phòng</h2>
          {missing > 0 ? (
            <p role="status" className="error">
              ⚠️ Cần thêm {missing} người
            </p>
          ) : (
            <p role="status">✔ Đủ người</p>
          )}
          <div className="row ww-wrap">
            <button type="button" className="secondary" disabled={busy || full} onClick={() => onAddBots(1)}>
              🤖 +1 Bot
            </button>
            {missing > 0 && (
              <button type="button" className="secondary" disabled={busy || full} onClick={() => onAddBots(missing)}>
                🤖 +{missing} Bot
              </button>
            )}
          </div>
          <button type="button" disabled={busy || missing > 0 || humans < 1} onClick={onStart}>
            ▶ Bắt đầu game
          </button>
        </section>
      ) : (
        <p className="muted ww-center" role="status">
          ⏳ Đang chờ chủ phòng bắt đầu
        </p>
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
