import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCommand } from "../../app/werewolf/hooks/useCommand";
import { useCountdown } from "../../app/werewolf/hooks/useCountdown";
import { TOAST_MS, useToast } from "../../app/werewolf/hooks/useToast";
import { ApiError } from "@sn/api";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useToast", () => {
  it("shows one message and clears it after a while", () => {
    const { result } = renderHook(() => useToast());
    act(() => result.current.notify("Lỗi 1"));
    expect(result.current.message).toBe("Lỗi 1");
    act(() => result.current.notify("Lỗi 2"));
    act(() => vi.advanceTimersByTime(TOAST_MS - 1));
    expect(result.current.message).toBe("Lỗi 2");
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.message).toBeNull();
  });

  it("can be dismissed and cleans its timer on unmount", () => {
    const { result, unmount } = renderHook(() => useToast());
    act(() => result.current.notify("x"));
    act(() => result.current.dismiss());
    expect(result.current.message).toBeNull();
    act(() => result.current.notify("y"));
    unmount();
    expect(() => vi.advanceTimersByTime(TOAST_MS)).not.toThrow();
  });
});

describe("useCommand", () => {
  it("maps a thrown error to Vietnamese text and frees the busy flag", async () => {
    const notify = vi.fn();
    const { result } = renderHook(() => useCommand(notify));
    let value: unknown = "unset";
    await act(async () => {
      value = await result.current.run(() => Promise.reject(new ApiError(429, "slow")));
    });
    expect(value).toBeUndefined();
    expect(notify).toHaveBeenCalledWith("Bạn thao tác quá nhanh, hãy chờ một chút.");
    expect(result.current.busy).toBe(false);
  });

  it("returns the value and refuses a second call while one is running", async () => {
    const notify = vi.fn();
    const { result } = renderHook(() => useCommand(notify));
    let release: (v: string) => void = () => undefined;
    const slow = () => new Promise<string>((resolve) => (release = resolve));
    let first: Promise<string | undefined> = Promise.resolve(undefined);
    act(() => {
      first = result.current.run(slow);
    });
    expect(result.current.busy).toBe(true);
    const second = jobResult(await result.current.run(async () => "second"));
    expect(second).toBeUndefined();
    await act(async () => {
      release("done");
      await first;
    });
    expect(await first).toBe("done");
    expect(result.current.busy).toBe(false);
    expect(notify).not.toHaveBeenCalled();
  });
});

function jobResult<T>(value: T) {
  return value;
}

describe("useCountdown", () => {
  it("counts down locally from the snapshot and resets on a new one", () => {
    const { result, rerender } = renderHook(({ timer }) => useCountdown(timer), {
      initialProps: { timer: { total: 60, secondsLeft: 41.5 } as { total: number; secondsLeft: number } | null },
    });
    expect(result.current).toBeCloseTo(41.5, 1);
    act(() => vi.advanceTimersByTime(10_000));
    expect(result.current).toBeCloseTo(31.5, 0);
    rerender({ timer: { total: 60, secondsLeft: 20 } });
    expect(result.current).toBeCloseTo(20, 0);
    act(() => vi.advanceTimersByTime(30_000));
    expect(result.current).toBe(0);
  });

  it("is null without a timer", () => {
    const { result } = renderHook(() => useCountdown(null));
    expect(result.current).toBeNull();
  });
});
