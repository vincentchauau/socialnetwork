"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "@sn/api";
import Button from "@sn/elements/Button";
import Card from "@sn/elements/Card";
import { TabPanel } from "@sn/compounds/SplitPanel";
import BetTable from "./BetTable";
import { tr } from "./i18n";
import { betLabel } from "./betLabel";
import { API, CHIP_VALUES, Leader, NumberCount, SpinResult, Stats, Wallet, addChip, doubled, errorText, placedFrom, toBets, totalOf } from "./lib";

const SPIN_MILLISECONDS = 1200; // the ball turns at least this long before the number is shown

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

const STRIP_RECENT = 12;
const STRIP_TOP = 3;

function Balls({ title, numbers }: { title: string; numbers: readonly NumberCount[] }) {
  return (
    <div className="strip-group">
      <span className="muted">{title}</span>
      <ul className="strip-balls" aria-label={title}>
        {numbers.map((entry, index) => (
          <li key={`${entry.number}-${index}`} className={`mini ${entry.colour}`} title={entry.count ? `${entry.count} ${tr("times")}` : undefined} aria-label={entry.count ? `${entry.number} (${entry.count} ${tr("times")})` : String(entry.number)}>
            {entry.number}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The last numbers, and the ones that came most and least often: a line to look at before a bet. */
function NumberStrip({ recent, stats }: { recent: readonly SpinResult[]; stats: Stats | null }) {
  if (recent.length === 0 || !stats) return null;
  const latest = recent.slice(0, STRIP_RECENT).map((spinRecord) => ({ number: spinRecord.number, colour: spinRecord.colour, count: 0 }));
  return (
    <div className="strip">
      <Balls title={tr("recent")} numbers={latest} />
      <Balls title={tr("hot")} numbers={stats.hot.slice(0, STRIP_TOP)} />
      <Balls title={tr("cold")} numbers={stats.cold.slice(0, STRIP_TOP)} />
    </div>
  );
}

export default function RouletteGame() {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [placed, setPlaced] = useState<Record<string, number>>({});
  const [chip, setChip] = useState<number>(CHIP_VALUES[1]);
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState<SpinResult | null>(null);
  const [history, setHistory] = useState<SpinResult[]>([]);
  const [board, setBoard] = useState<Leader[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const [nextWallet, spins, leaders, counted] = await Promise.all([
        apiFetch<Wallet>(`${API}/wallet`),
        apiFetch<SpinResult[]>(`${API}/spins`),
        apiFetch<Leader[]>(`${API}/board`),
        apiFetch<Stats>(`${API}/stats`),
      ]);
      if (!alive.current) return;
      setWallet(nextWallet);
      setHistory(spins);
      setBoard(leaders);
      setStats(counted);
    } catch (problem) {
      if (alive.current) setError(errorText(problem));
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void refresh();
    return () => {
      alive.current = false;
    };
  }, [refresh]);

  const chips = wallet?.chips ?? 0;
  const staked = totalOf(placed);

  async function spin() {
    setError(null);
    setSpinning(true);
    setResult(null);
    try {
      const [outcome] = await Promise.all([
        apiFetch<SpinResult>(`${API}/spin`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ bets: toBets(placed) }) }),
        wait(SPIN_MILLISECONDS),
      ]);
      if (!alive.current) return;
      setResult(outcome);
      setWallet((current) => (current ? { ...current, chips: outcome.balance_after } : current));
      setHistory((current) => [outcome, ...current]);
      setPlaced({});
      void refresh();
    } catch (problem) {
      if (alive.current) setError(errorText(problem));
    } finally {
      if (alive.current) setSpinning(false);
    }
  }

  async function act(path: string, method: string, after?: () => void) {
    setError(null);
    try {
      await apiFetch(`${API}${path}`, { method });
      after?.();
      await refresh();
    } catch (problem) {
      setError(errorText(problem));
    }
  }

  const maxBet = wallet?.max_bet ?? 0;
  const lastSpin = history[0];
  const rebet = (spinRecord: SpinResult) => setPlaced(placedFrom(spinRecord.bets, maxBet, chips));
  const net = result ? result.payout - result.stake : 0;
  const verdict = result ? (net > 0 ? tr("you_won") : net < 0 ? tr("you_lost") : tr("even_money")) : null;

  const tableView = (
      <Card stack>
        <div className="row">
          <div className={`ball ${spinning ? "spinning idle" : result ? result.colour : "idle"}`} aria-live="polite" data-testid="ball">
            {spinning ? "…" : result ? result.number : "?"}
          </div>
          <div>
            <div><strong>{tr("chips")}: {wallet ? chips : tr("loading")}</strong></div>
            <div className="muted">{tr("on_table")}: {staked}</div>
            {result && verdict ? (
              <div role="status" className={net > 0 ? "gain" : net < 0 ? "loss" : ""}>
                {tr("ball_stopped_at")} {result.number} · {verdict}{net !== 0 ? ` ${Math.abs(net)}` : ""}
              </div>
            ) : null}
          </div>
        </div>
        <div className="row" role="group" aria-label={tr("chip_value")}>
          {CHIP_VALUES.map((value) => (
            <Button key={value} type="button" size="sm" variant="secondary" className="chip" aria-pressed={chip === value} onClick={() => setChip(value)}>
              {value}
            </Button>
          ))}
        </div>
        <BetTable
          placed={placed}
          winner={result ? result.number : null}
          disabled={spinning || !wallet}
          onPlace={(key) => setPlaced((current) => addChip(current, key, chip, wallet?.max_bet ?? 0, chips))}
        />
        <NumberStrip recent={history} stats={stats} />
        <div className="row">
          <Button type="button" onClick={() => void spin()} disabled={spinning || staked === 0} loading={spinning} loadingLabel={tr("spinning")}>
            {tr("spin")}
          </Button>
          <Button type="button" variant="secondary" onClick={() => setPlaced({})} disabled={spinning || staked === 0}>
            {tr("clear_bets")}
          </Button>
          <Button type="button" variant="secondary" onClick={() => lastSpin && rebet(lastSpin)} disabled={spinning || !lastSpin || chips === 0}>
            {tr("rebet")}
          </Button>
          <Button type="button" variant="secondary" onClick={() => setPlaced((current) => doubled(current, maxBet, chips))} disabled={spinning || staked === 0}>
            {tr("double")}
          </Button>
          {staked === 0 && chips > 0 ? <span className="muted">{tr("place_a_bet")}</span> : null}
        </div>
        {wallet && chips === 0 ? (
          <div className="row">
            <span>{tr("out_of_chips")}</span>
            <Button type="button" onClick={() => void act("/wallet/refill", "POST")}>{tr("refill")}</Button>
          </div>
        ) : null}
        {error ? <p role="alert" className="error">{error}</p> : null}
      </Card>
  );
  const historyView = (
      <Card as="section" stack aria-labelledby="roulette-history">
        <div className="row">
          <h2 id="roulette-history" className="section-title">{tr("history")}</h2>
          {history.length > 0 ? (
            <Button type="button" size="sm" variant="ghost" onClick={() => void act("/spins", "DELETE")}>{tr("clear_history")}</Button>
          ) : null}
        </div>
        {history.length === 0 ? (
          <p className="muted">{tr("no_spins")}</p>
        ) : (
          <ul className="spins">
            {history.map((spinRecord) => {
              const gain = spinRecord.payout - spinRecord.stake;
              return (
                <li key={spinRecord.id}>
                  <span className={`mini ${spinRecord.colour}`}>{spinRecord.number}</span>
                  <span className={gain > 0 ? "gain" : gain < 0 ? "loss" : "muted"}>{gain > 0 ? `+${gain}` : gain}</span>
                  <span className="muted">→ {spinRecord.balance_after}</span>
                  <Button type="button" size="sm" variant="ghost" aria-label={`${tr("rebet_spin")} #${spinRecord.id}`} disabled={spinning || chips === 0} onClick={() => rebet(spinRecord)}>
                    {tr("rebet")}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" aria-label={`${tr("delete")} #${spinRecord.id}`} onClick={() => void act(`/spins/${spinRecord.id}`, "DELETE")}>
                    {tr("delete")}
                  </Button>
                  <details className="bets">
                    <summary>{tr("bets")} ({spinRecord.bets.length})</summary>
                    <ul>
                      {spinRecord.bets.map((placedBet, index) => (
                        <li key={index}>
                          {betLabel(placedBet.kind, placedBet.pick)} · {placedBet.amount}
                          {placedBet.payout > 0 ? <span className="gain"> → {placedBet.payout} {tr("won_back")}</span> : <span className="loss"> → 0</span>}
                        </li>
                      ))}
                    </ul>
                  </details>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
  );
  const boardView = (
      <Card as="section" stack aria-labelledby="roulette-board">
        <h2 id="roulette-board" className="section-title">{tr("board")}</h2>
        <ol className="board-list">
          {board.map((leader) => (
            <li key={leader.username}>
              <span className="board-name">{leader.username}</span>
              <span className="board-chips">{leader.chips}</span>
            </li>
          ))}
        </ol>
      </Card>
  );

  return (
    <div className="stack">
      <h1 className="page-title">{tr("roulette")}</h1>
      <p className="muted">{tr("play_money")}</p>
      <TabPanel
        aria-label={tr("roulette")}
        data={[
          { key: "table", label: tr("table") },
          { key: "history", label: tr("history") },
          { key: "leaderboard", label: tr("leaderboard") },
        ]}
        panels={{ table: tableView, history: historyView, leaderboard: boardView }}
      />
    </div>
  );
}

