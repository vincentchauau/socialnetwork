"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { werewolfApi } from "../lib/api";
import { errorText } from "../lib/errors";
import {
  buildCreateBody,
  clampCount,
  DEFAULT_COUNT,
  normalizeCode,
  QUICK_COUNTS,
  ROOM_CODE_LENGTH,
  ROOM_NAME_MAX,
  tally,
  TIMER_LABEL,
  validateSetup,
} from "../lib/setup";
import { FACTION_ICON } from "../lib/theme";
import type { CreateBody, SetupMeta, SetupSeat } from "../lib/types";
import FieldLabel from "./FieldLabel";
import SeatRow from "./SeatRow";
import SizeInput from "./SizeInput";

const RANDOM_COUNT_MAX = 20;

interface Props {
  meta: SetupMeta;
  username: string;
  busy: boolean;
  notify: (text: string) => void;
  onCreate: (body: CreateBody) => void;
}

/** Room creation form: seat count and table, timer, switches, room name/code; start now or open a lobby. */
export default function SetupForm({ meta, username, busy, notify, onCreate }: Props) {
  const [seats, setSeats] = useState<SetupSeat[]>([]);
  const [roomName, setRoomName] = useState("");
  const [roomCode, setRoomCode] = useState("");
  const [timerSeconds, setTimerSeconds] = useState(0);
  const [events, setEvents] = useState(true);
  const [deadTalk, setDeadTalk] = useState(true);
  const [listed, setListed] = useState(true);
  const [showSeats, setShowSeats] = useState(false);
  const [rolling, setRolling] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const ticket = useRef(0);

  /** Deals `count` seats from the server; a stale answer (a newer roll started) is dropped. */
  const roll = useCallback(
    async (count: number): Promise<SetupSeat[] | null> => {
      const mine = ++ticket.current;
      setRolling(true);
      try {
        const { seats: dealt } = await werewolfApi.random(count);
        if (mine !== ticket.current) return null;
        setSeats(dealt);
        return dealt;
      } catch (error) {
        if (mine === ticket.current) notify(errorText(error));
        return null;
      } finally {
        if (mine === ticket.current) setRolling(false);
      }
    },
    [notify],
  );

  useEffect(() => {
    void roll(DEFAULT_COUNT);
  }, [roll]);

  const count = seats.length;
  const quick = QUICK_COUNTS.filter((n) => n >= meta.minPlayers && n <= meta.maxPlayers);

  const setCount = (value: number) => {
    const next = clampCount(meta, value);
    if (next !== count) void roll(next);
  };

  const randomizeAll = async () => {
    const top = Math.min(RANDOM_COUNT_MAX, meta.maxPlayers);
    const n = meta.minPlayers + Math.floor(Math.random() * (top - meta.minPlayers + 1));
    const dealt = await roll(n);
    if (dealt) {
      setSummary(
        `🎲 Đã xáo ${dealt.length} người · ${FACTION_ICON.WOLF} ${tally(dealt, "WOLF")} · ${FACTION_ICON.GHOST} ${tally(dealt, "GHOST")} · ${FACTION_ICON.VILLAGER} ${tally(dealt, "VILLAGER")}`,
      );
    }
  };

  const updateSeat = (index: number, next: SetupSeat) =>
    setSeats((old) => old.map((seat, i) => (i === index ? next : seat)));

  const create = (start: boolean) => {
    const options = { seats, roomName, roomCode, timerSeconds, events, deadTalk, listed };
    const reason = validateSetup(meta, options);
    setProblem(reason);
    if (!reason) onCreate(buildCreateBody(options, start));
  };

  const disabled = busy || rolling || count === 0;

  return (
    <section className="card stack" aria-labelledby="ww-setup-title">
      <h2 id="ww-setup-title">🏕️ Tạo phòng</h2>

      <div className="ww-two">
        <div>
          <FieldLabel htmlFor="ww-room-name" text="🏷️ Tên phòng" hint="(để trống = ngẫu nhiên)" />
          <input
            id="ww-room-name"
            value={roomName}
            maxLength={ROOM_NAME_MAX}
            onChange={(event) => setRoomName(event.target.value)}
            placeholder="Làng của tôi"
          />
        </div>
        <div>
          <FieldLabel htmlFor="ww-room-code" text="🔑 Mã phòng" hint="(5 chữ cái, để trống = tự tạo)" hintId="ww-room-code-hint" />
          <input
            id="ww-room-code"
            value={roomCode}
            maxLength={ROOM_CODE_LENGTH}
            aria-describedby="ww-room-code-hint"
            autoCapitalize="characters"
            onChange={(event) => setRoomCode(normalizeCode(event.target.value))}
            placeholder="WOLFS"
          />
        </div>
      </div>

      <fieldset className="ww-fieldset">
        <legend>⏱ Thời gian mỗi lượt đêm (ban ngày gấp đôi)</legend>
        <div className="ww-chips" role="radiogroup" aria-label="Thời gian mỗi lượt">
          {meta.timerOptions.map((seconds) => (
            <button
              key={seconds}
              type="button"
              role="radio"
              aria-checked={timerSeconds === seconds}
              className={`ww-chip ${timerSeconds === seconds ? "" : "secondary"}`}
              onClick={() => setTimerSeconds(seconds)}
            >
              {TIMER_LABEL(seconds)}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="stack">
        <label className="ww-check">
          <input type="checkbox" checked={events} onChange={(event) => setEvents(event.target.checked)} /> 🎴 Thẻ sự kiện ngẫu nhiên mỗi đêm
        </label>
        <label className="ww-check">
          <input type="checkbox" checked={deadTalk} onChange={(event) => setDeadTalk(event.target.checked)} /> 💀 Người chết chat chung với người sống
        </label>
        <label className="ww-check">
          <input type="checkbox" checked={listed} onChange={(event) => setListed(event.target.checked)} /> 📣 Hiện trong danh sách phòng công khai
        </label>
      </div>

      <div className="ww-count">
        <FieldLabel htmlFor="ww-count" text="👥 Số người chơi" hint={`(${meta.minPlayers}–${meta.maxPlayers})`} />
        <div className="row ww-count-row">
          <button type="button" className="secondary" aria-label="Bớt một người" disabled={disabled || count <= meta.minPlayers} onClick={() => setCount(count - 1)}>
            −
          </button>
          <SizeInput id="ww-count" value={count || DEFAULT_COUNT} min={meta.minPlayers} max={meta.maxPlayers} onChange={setCount} />
          <button type="button" className="secondary" aria-label="Thêm một người" disabled={disabled || count >= meta.maxPlayers} onClick={() => setCount(count + 1)}>
            +
          </button>
        </div>
        <div className="ww-chips" role="group" aria-label="Chọn nhanh số người">
          {quick.map((n) => (
            <button key={n} type="button" className={`ww-chip ${count === n ? "" : "secondary"}`} aria-pressed={count === n} disabled={rolling} onClick={() => setCount(n)}>
              {n}
            </button>
          ))}
        </div>
        <p className="muted" aria-live="polite">
          {FACTION_ICON.WOLF} {tally(seats, "WOLF")} · {FACTION_ICON.GHOST} {tally(seats, "GHOST")} · {FACTION_ICON.VILLAGER} {tally(seats, "VILLAGER")}
        </p>
      </div>

      <div className="row ww-wrap">
        <button type="button" className="secondary" disabled={disabled} onClick={() => void randomizeAll()}>
          🎲 Ngẫu nhiên tất cả
        </button>
        <button type="button" className="secondary" aria-expanded={showSeats} aria-controls="ww-seats" onClick={() => setShowSeats((v) => !v)}>
          {showSeats ? "Thu gọn ▴" : "Chỉnh phe và chức năng ▾"}
        </button>
      </div>
      {summary && (
        <p role="status" className="ww-summary">
          {summary}
        </p>
      )}

      {showSeats && (
        <ol id="ww-seats" className="ww-seats" aria-label="Bảng ghế">
          {seats.map((seat, index) => (
            <SeatRow key={index} index={index} seat={seat} meta={meta} name={index === 0 ? username : null} onChange={(next) => updateSeat(index, next)} />
          ))}
        </ol>
      )}

      {problem && (
        <p role="alert" className="error">
          {problem}
        </p>
      )}
      <div className="stack">
        <button type="button" disabled={disabled} onClick={() => create(true)}>
          🎮 Bắt đầu ngay (còn lại là bot)
        </button>
        <button type="button" className="secondary" disabled={disabled} onClick={() => create(false)}>
          🚪 Tạo phòng chờ người khác vào
        </button>
      </div>
    </section>
  );
}
