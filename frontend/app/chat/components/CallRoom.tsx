"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

import Button from "@sn/elements/Button";
import { ConnectionState, type Participant, Room, RoomEvent, Track } from "livekit-client";

import type { Meeting } from "../api";
import { errorMessage } from "../errors";
import { tr } from "../i18n";
import type { MemberRow } from "../protocol";
import { useVoicePlayer } from "../voicePlayer";
import AvatarImage from "./AvatarImage";
import { CallBar, TILE_GAP, TILE_RATIO, Tile, type Toggle, noWrap, tileGrid } from "./CallParts";
import MediaCheck, { type CheckHandle, type CheckState, deviceProblem } from "./MediaCheck";
import { useSize } from "./useSize";

/** The most columns, and the widest tile, that fit `count` tiles of TILE_RATIO into width x height. */
export function fitTiles(count: number, width: number, height: number): { columns: number; tileWidth: number } {
  let best = { columns: 1, tileWidth: 0 };
  for (let columns = 1; columns <= Math.max(1, count); columns++) {
    const rows = Math.ceil(count / columns);
    const byWidth = (width - (columns - 1) * TILE_GAP) / columns;
    const byHeight = ((height - (rows - 1) * TILE_GAP) / rows) * TILE_RATIO;
    const tileWidth = Math.floor(Math.min(byWidth, byHeight));
    if (tileWidth > best.tileWidth) best = { columns, tileWidth };
  }
  return best;
}

/** One person of the call: their camera (or their picture), their name, a ring while they speak, a mark when their microphone is off. */
function PersonTile({ participant, local, focused }: { participant: Participant; local: boolean; focused: boolean }) {
  const video = useRef<HTMLVideoElement>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const camera = participant.getTrackPublication(Track.Source.Camera);
  const mic = participant.getTrackPublication(Track.Source.Microphone);
  const cameraTrack = camera?.track && !camera.isMuted ? camera.track : undefined;
  const micTrack = mic?.track;
  useEffect(() => {
    const element = video.current;
    if (element && cameraTrack) {
      cameraTrack.attach(element);
      return () => void cameraTrack.detach(element);
    }
  }, [cameraTrack, focused]);
  useEffect(() => {
    const element = audio.current;
    if (element && micTrack && !local) {
      micTrack.attach(element);
      return () => void micTrack.detach(element);
    }
  }, [micTrack, local]);
  const name = participant.name || participant.identity;
  const off = !mic || mic.isMuted;
  return (
    <Tile focused={focused} speaking={participant.isSpeaking} name={`${off ? "🔇 " : ""}${name}${local ? ` (${tr("rm_ban")})` : ""}`}>
      {cameraTrack ? (
        <video ref={video} autoPlay playsInline muted style={{ width: "100%", height: "100%", objectFit: "contain", background: "var(--line)", transform: local ? "scaleX(-1)" : undefined }} />
      ) : (
        <AvatarImage url={null} name={name} size={focused ? 140 : 72} />
      )}
      {!local && <audio ref={audio} autoPlay />}
    </Tile>
  );
}

/** What somebody shares of their screen. */
function ScreenTile({ participant, focused }: { participant: Participant; focused: boolean }) {
  const video = useRef<HTMLVideoElement>(null);
  const track = participant.getTrackPublication(Track.Source.ScreenShare)?.track;
  useEffect(() => {
    const element = video.current;
    if (element && track) {
      track.attach(element);
      return () => void track.detach(element);
    }
  }, [track, focused]);
  return (
    <Tile focused={focused} name={`🖥 ${participant.name || participant.identity}`}>
      <video ref={video} autoPlay playsInline muted style={{ width: "100%", height: "100%", objectFit: "contain" }} />
    </Tile>
  );
}

/** A virtual person: a tile made by the page (the picture, the name, a ring while they speak). They are not in the video: their voice comes through the room. */
function VirtualTile({ person, speaking, focused }: { person: MemberRow; speaking: boolean; focused: boolean }) {
  const name = person.name || person.username;
  return (
    <Tile focused={focused} speaking={speaking} style={{ background: "var(--solid-1)" }} name={`${name} · ${tr("rm_ao")}`}>
      <AvatarImage url={person.avatar} name={name} size={focused ? 160 : 88} />
    </Tile>
  );
}

/** What a virtual person shares: words on a slide. */
function SlideTile({ slide, focused }: { slide: { name: string; title: string; lines: string[] }; focused: boolean }) {
  return (
    <Tile
      focused={focused}
      style={{ alignItems: "flex-start", justifyContent: "flex-start", background: "var(--solid-0)", color: "var(--line)", padding: 20, flexDirection: "column" }}
      name={`🖥 ${slide.name}`}
    >
      <strong style={{ fontSize: focused ? 30 : 20 }}>{slide.title}</strong>
      <ul style={{ margin: "10px 0 0", paddingLeft: 22, fontSize: focused ? 24 : 16 }}>
        {slide.lines.map((line, index) => <li key={index}>{line}</li>)}
      </ul>
    </Tile>
  );
}

interface Cell {
  key: string;
  /** The name for the button that makes it big. */
  name: string;
  render: (focused: boolean) => ReactNode;
}

/** A tile: pressed, it fills the whole screen (the browser's full screen; Escape or pressing it again goes back to the grid). */
function CellView({ cell }: { cell: Cell }) {
  const holder = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === holder.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function press() {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void holder.current?.requestFullscreen?.();
  }

  return (
    <div ref={holder} style={{ background: full ? "var(--line)" : undefined, display: full ? "flex" : undefined, alignItems: "center", justifyContent: "center" }}>
      <div
        role="button"
        tabIndex={0}
        aria-label={tr("rm_toan_man_hinh_p0", { p0: cell.name })}
        title={tr("rm_toan_man_hinh_p0", { p0: cell.name })}
        onClick={press}
        onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && (event.preventDefault(), press())}
        style={{ cursor: full ? "zoom-out" : "zoom-in", width: "100%" }}
      >
        {cell.render(full)}
      </div>
    </div>
  );
}

interface Props {
  /** Null until the person joins: the page then shows the checks and the Join button. */
  meeting: Meeting | null;
  onJoin?: () => void;
  joinLabel?: string;
  joinDisabled?: boolean;
  /** Shown under the grid, before joining (the people in the room). */
  extra?: ReactNode;
  /** The virtual people of the room: they have a tile each. */
  virtualPeople: MemberRow[];
  /** The starter and the owner can end the call for everybody. */
  canEnd: boolean;
  onLeave: () => void;
  onEnd: () => void;
}

/**
 * The call of a room, and the check before it: the same bar, the same tiles and the same grid in both. In the call, the webcam and the
 * shared screen of each person come from LiveKit (the camera and the microphone are switched on when the person is in, and when one cannot
 * be taken the page says why), with a tile for each virtual person and the slide one of them shares. Before the call, the tiles are the
 * person's own camera and screen share, taken by the page with nothing sent. A tile is pressed to fill the screen.
 */
export default function CallRoom({ meeting, virtualPeople, canEnd, onLeave, onEnd, onJoin, joinLabel = "", joinDisabled = false, extra }: Props) {
  const [, rerender] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [micProblem, setMicProblem] = useState<string | null>(null);
  const [cameraProblem, setCameraProblem] = useState<string | null>(null);
  const [checkProblem, setCheckProblem] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const roomRef = useRef<Room | null>(null);
  const voice = useVoicePlayer();
  // Before joining: the checks are the tiles of the grid, and the same bar switches them.
  const checkRef = useRef<CheckHandle>(null);
  const [checks, setChecks] = useState<CheckState>({ camera: false, mic: false, share: false, level: 0 });

  useEffect(() => {
    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;
    const refresh = () => rerender((n) => n + 1);
    const events = [
      RoomEvent.ParticipantConnected, RoomEvent.ParticipantDisconnected, RoomEvent.TrackSubscribed, RoomEvent.TrackUnsubscribed, RoomEvent.TrackMuted,
      RoomEvent.TrackUnmuted, RoomEvent.LocalTrackPublished, RoomEvent.LocalTrackUnpublished, RoomEvent.ActiveSpeakersChanged,
    ];
    events.forEach((event) => room.on(event, refresh));
    room.on(RoomEvent.Disconnected, () => setConnected(false));
    let gone = false;
    if (!meeting) return () => room.disconnect();
    (async () => {
      try {
        await room.connect(meeting.server, meeting.token);
        if (gone) return;
        setConnected(room.state === ConnectionState.Connected);
        await room.localParticipant.setMicrophoneEnabled(true).catch((caught: unknown) => !gone && setMicProblem(deviceProblem(caught, "mic")));
        await room.localParticipant.setCameraEnabled(true).catch((caught: unknown) => !gone && setCameraProblem(deviceProblem(caught, "camera")));
        if (!gone && !room.localParticipant.isMicrophoneEnabled) setMicProblem((was) => was ?? tr("rm_mic_dang_tat"));
        refresh();
      } catch (caught) {
        if (!gone) setError(errorMessage(caught));
      }
    })();
    return () => {
      gone = true;
      void room.disconnect();
      roomRef.current = null;
    };
  }, [meeting?.server, meeting?.token]);

  const room = roomRef.current;
  const people: Participant[] = room ? [room.localParticipant, ...Array.from(room.remoteParticipants.values())] : [];
  const mine = room?.localParticipant;
  const micOn = !!mine?.isMicrophoneEnabled;
  const cameraOn = !!mine?.isCameraEnabled;
  const sharing = !!mine?.isScreenShareEnabled;
  const joined = meeting !== null;

  async function toggle(what: "mic" | "camera" | "screen") {
    if (!mine) return;
    try {
      if (what === "mic") {
        await mine.setMicrophoneEnabled(!micOn);
        setMicProblem(null);
      } else if (what === "camera") {
        await mine.setCameraEnabled(!cameraOn);
        setCameraProblem(null);
      } else {
        await mine.setScreenShareEnabled(!sharing);
      }
    } catch (caught) {
      if (what === "mic") setMicProblem(deviceProblem(caught, "mic"));
      else if (what === "camera") setCameraProblem(deviceProblem(caught, "camera"));
      else setError(errorMessage(caught));
    }
    rerender((n) => n + 1);
  }

  function onToggle(what: Toggle) {
    if (joined) void toggle(what === "share" ? "screen" : what);
    else void checkRef.current?.toggle(what);
  }

  const [gridBox, gridSize] = useSize<HTMLDivElement>();
  const cells: Cell[] = [];
  for (const participant of people) {
    const name = participant.name || participant.identity;
    if (participant.getTrackPublication(Track.Source.ScreenShare)?.track) {
      cells.push({ key: `${participant.sid}-screen`, name: `${name} (${tr("rm_man_hinh")})`, render: (focused) => <ScreenTile participant={participant} focused={focused} /> });
    }
    cells.push({ key: participant.sid, name, render: (focused) => <PersonTile participant={participant} local={participant === mine} focused={focused} /> });
  }
  if (voice.slide) {
    const slide = voice.slide;
    cells.push({ key: "slide", name: `${slide.name} (${tr("rm_man_hinh")})`, render: (focused) => <SlideTile slide={slide} focused={focused} /> });
  }
  for (const person of virtualPeople) {
    cells.push({
      key: `virtual-${person.user_id}`, name: person.name || person.username,
      render: (focused) => <VirtualTile person={person} speaking={voice.speakingUserId === person.user_id} focused={focused} />,
    });
  }
  // Before the call the grid holds the camera and the share checks only (at least one slot, so the grid keeps its size).
  const shownCount = joined ? cells.length : Math.max(1, (checks.camera ? 1 : 0) + (checks.share ? 1 : 0));
  const fit = fitTiles(shownCount, gridSize.width || 960, gridSize.height > 0 ? gridSize.height : 480);
  const problems = [error, micProblem, cameraProblem, checkProblem].filter((text): text is string => !!text);

  return (
    <section aria-label={tr("rm_cuoc_hop_phong")} style={{ display: "flex", flexDirection: "column", gap: 8, height: "100%", minHeight: 0, overflow: "hidden" }}>
      <CallBar
        title={tr("rm_cuoc_hop_phong")}
        mic={joined ? micOn : checks.mic}
        camera={joined ? cameraOn : checks.camera}
        share={joined ? sharing : checks.share}
        onToggle={onToggle}
      >
        {joined ? (
          <>
            <Button type="button" size="sm" style={noWrap} variant="secondary" onClick={onLeave}>{tr("rm_roi_cuoc_hop")}</Button>
            {canEnd && <Button type="button" size="sm" style={noWrap} variant="secondary" onClick={onEnd}>⏹ {tr("rm_ket_thuc_cho_moi_nguoi")}</Button>}
          </>
        ) : (
          <Button type="button" size="sm" style={noWrap} variant="primary" disabled={joinDisabled} onClick={onJoin}>{joinLabel}</Button>
        )}
      </CallBar>
      {problems.map((text) => <p key={text} role="alert" className="cw-notice" style={{ margin: 0 }}>{text}</p>)}
      {joined && !connected && !error && <p role="status" className="muted" style={{ margin: 0 }}>{tr("rm_dang_noi")}</p>}
      <div ref={gridBox} style={{ height: gridSize.height > 0 ? gridSize.height : undefined, minHeight: 0, overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={tileGrid(fit.columns, fit.tileWidth)}>
          {joined ? cells.map((cell) => <CellView key={cell.key} cell={cell} />) : <MediaCheck ref={checkRef} onState={setChecks} onProblem={setCheckProblem} />}
        </div>
      </div>
      {!joined && checks.mic && (
        <div style={{ width: 240, height: 14, background: "var(--line)", borderRadius: 7, overflow: "hidden", alignSelf: "center" }} aria-label={tr("rm_mic_bat")}>
          <div style={{ height: "100%", width: `${Math.round(checks.level * 100)}%`, background: "var(--line)", transition: "width 60ms linear" }} />
        </div>
      )}
      {!joined && extra}
      {joined && voice.subtitle && (
        <p role="status" aria-live="polite" style={{ margin: 0, padding: "6px 10px", borderRadius: 6, background: "color-mix(in srgb, var(--line) 55%, transparent)", color: "var(--solid-0)" }}>
          <b>{voice.subtitle.name}:</b> {voice.subtitle.text}
        </p>
      )}
    </section>
  );
}
