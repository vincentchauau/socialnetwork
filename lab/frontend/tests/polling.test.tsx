import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "../app/hooks/usePolling";

function Probe({ task, ms }: { task: () => Promise<void>; ms: number }) {
  const refresh = usePolling(task, ms);
  return <button onClick={refresh}>go</button>;
}

const setHidden = (hidden: boolean) => {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event("visibilitychange"));
};
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  setHidden(false);
  vi.useRealTimers();
});

describe("usePolling", () => {
  it("runs at once, then after each interval", async () => {
    const task = vi.fn().mockResolvedValue(undefined);
    render(<Probe task={task} ms={1000} />);
    await advance(0);
    expect(task).toHaveBeenCalledTimes(1);
    await advance(1000);
    expect(task).toHaveBeenCalledTimes(2);
    await advance(2000);
    expect(task).toHaveBeenCalledTimes(4);
  });

  it("never overlaps: the next run waits for the previous one", async () => {
    let release: () => void = () => {};
    const task = vi.fn(() => new Promise<void>((resolve) => { release = resolve; }));
    const { getByText } = render(<Probe task={task} ms={1000} />);
    await advance(10_000);
    expect(task).toHaveBeenCalledTimes(1);
    act(() => getByText("go").click());
    expect(task).toHaveBeenCalledTimes(1);
    release();
    await advance(999);
    expect(task).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(task).toHaveBeenCalledTimes(2);
  });

  it("stops on unmount", async () => {
    const task = vi.fn().mockResolvedValue(undefined);
    const { unmount } = render(<Probe task={task} ms={1000} />);
    await advance(1000);
    const calls = task.mock.calls.length;
    unmount();
    await advance(10_000);
    expect(task).toHaveBeenCalledTimes(calls);
  });

  it("pauses while the tab is hidden and resumes at once when visible", async () => {
    const task = vi.fn().mockResolvedValue(undefined);
    render(<Probe task={task} ms={1000} />);
    await advance(0);
    setHidden(true);
    await advance(10_000);
    expect(task).toHaveBeenCalledTimes(1);
    setHidden(false);
    await advance(0);
    expect(task).toHaveBeenCalledTimes(2);
  });

  it("does not schedule a new run when the tab got hidden during a run", async () => {
    let release: () => void = () => {};
    const task = vi.fn(() => new Promise<void>((resolve) => { release = resolve; }));
    render(<Probe task={task} ms={1000} />);
    await advance(0);
    setHidden(true);
    release();
    await advance(10_000);
    expect(task).toHaveBeenCalledTimes(1);
  });

  it("manual refresh runs the task immediately", async () => {
    const task = vi.fn().mockResolvedValue(undefined);
    const { getByText } = render(<Probe task={task} ms={60_000} />);
    await advance(0);
    act(() => getByText("go").click());
    await advance(0);
    expect(task).toHaveBeenCalledTimes(2);
  });
});
