import { useEffect, useState } from "react";

import { tr } from "../i18n";
import { werewolfApi } from "../lib/api";
import { tally } from "../lib/setup";
import { FACTION_ICON } from "../lib/theme";
import type { RoomState, SetupMeta, SetupSeat } from "../lib/types";
import RulesContent from "./RulesContent";
import SeatRow from "./SeatRow";
import Button from "@sn/elements/Button";
import CheckBox from "@sn/elements/CheckBox";

interface Props {
  room: RoomState;
  busy: boolean;
  onStart: () => void;
  onLeave: () => void;
  /** The host deals the roles at random (`{ random: true }`), then changes them seat by seat (`seats`). */
  onRoles: (body: { random?: boolean; seats?: SetupSeat[]; banned?: string[] }) => void;
}

/**
 * Lobby, one box: the host's Random and Start, the roles of every player once they are dealt (the host can change them), and the rules.
 * Everybody online in the chat room plays, so there is no list of members before the roles are dealt.
 */
export default function LobbyView({ room, busy, onStart, onLeave, onRoles }: Props) {
  const [meta, setMeta] = useState<SetupMeta | null>(null);
  const [banned, setBanned] = useState<string[]>([]); // abilities the random deal leaves out
  const [showDetails, setShowDetails] = useState(false); // the rules and the roles are opened with Show, or by Random
  useEffect(() => {
    werewolfApi.meta().then(setMeta, () => undefined);
  }, []);
  const setup = room.setup ?? [];
  const dealt = setup.length > 0 && setup.every(Boolean);
  const seatsOf = (): SetupSeat[] => setup.map((role) => (role ? { faction: role.faction.code, ability: role.ability.code } : { faction: "VILLAGER", ability: "NONE" }));
  const missing = Math.max(0, room.minPlayers - room.members.length);
  const humans = room.members.filter((m) => !m.isBot).length;

  // One button hides or shows everything under the buttons that is detail: the roles of every player and the rules.
  const toggle = (
    <Button variant="secondary" type="button" className="secondary" aria-expanded={showDetails} aria-controls="ww-lobby-details ww-lobby-seats" onClick={() => setShowDetails((v) => !v)}>
      {showDetails ? tr("ww_an_vai") : tr("ww_hien_vai")}
    </Button>
  );

  return (
    <div className="stack ww-lobby">
      <section className="card stack ww-seats-card" aria-label={tr("p0_nguoi", { p0: room.members.length })}>
        {room.isHost ? (
          <>
            {missing > 0 && (
              <p role="status" className="error">
                {tr("can_them")} {missing} {tr("nguoi")}
              </p>
            )}
            <div className="row ww-wrap ww-center">
              <Button variant="secondary" type="button" className="secondary" disabled={busy} onClick={() => { setShowDetails(true); onRoles({ random: true, ...(banned.length > 0 ? { banned } : {}) }); }}>
                🎲 {tr("chia_vai_ngau_nhien")}
              </Button>
              <Button type="button" disabled={busy || missing > 0 || humans < 1} onClick={onStart}>
                ▶ {tr("bat_dau_game")}
              </Button>
              {toggle}
            </div>
            {meta?.bannable && meta.bannable.length > 0 && (
              <details className="ww-center">
                <summary>{tr("ww_cam_chuc_nang")}{banned.length > 0 ? ` (${tr("ww_cam_p0_dang_cam", { p0: banned.length })})` : ""}</summary>
                <p className="muted">{tr("ww_cam_goi_y")}</p>
                <div className="row ww-wrap">
                  {meta.bannable.map((code) => (
                    <label key={code} className="row" style={{ gap: 4, alignItems: "center" }} title={meta.abilities.find((ability) => ability.code === code)?.help}>
                      <CheckBox checked={banned.includes(code)} onChange={(checked) => setBanned((current) => (checked ? [...current, code] : current.filter((item) => item !== code)))} />
                      {meta.abilities.find((ability) => ability.code === code)?.label ?? code}
                    </label>
                  ))}
                </div>
              </details>
            )}
            {dealt && (
              <>
                <ul className="ww-roles" aria-label={tr("so_phe")}>
                  <li>{FACTION_ICON.WOLF} {tr("phe_soi")}: <strong>{tally(seatsOf(), "WOLF")}</strong></li>
                  <li>{FACTION_ICON.GHOST} {tr("phe_ma")}: <strong>{tally(seatsOf(), "GHOST")}</strong></li>
                  <li>{FACTION_ICON.VILLAGER} {tr("phe_dan")}: <strong>{tally(seatsOf(), "VILLAGER")}</strong></li>
                </ul>
                {meta && showDetails && (
                  <ol id="ww-lobby-seats" className="ww-seats" aria-label={tr("bang_ghe")}>
                    {seatsOf().map((seat, index) => (
                      <SeatRow
                        key={index}
                        index={index}
                        seat={seat}
                        meta={meta}
                        name={room.members[index]?.name ?? `Bot ${index + 1}`}
                        isBot={room.members[index]?.isBot ?? true}
                        onChange={(next) => onRoles({ seats: seatsOf().map((current, i) => (i === index ? next : current)) })}
                      />
                    ))}
                  </ol>
                )}
              </>
            )}
          </>
        ) : (
          <div className="ww-guest ww-center">
            <p className="muted" role="status">
              {tr("dang_cho_chu_phong_bat_dau")}
            </p>
            <div className="row ww-wrap ww-center">
              <Button variant="secondary" type="button" className="secondary" onClick={onLeave} disabled={busy}>
                {tr("roi_phong")}
              </Button>
              {toggle}
            </div>
          </div>
        )}
        <div id="ww-lobby-details" hidden={!showDetails} className="stack">
          <RulesContent meta={meta} />
        </div>
      </section>
    </div>
  );
}
