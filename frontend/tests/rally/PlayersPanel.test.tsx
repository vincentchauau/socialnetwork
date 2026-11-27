import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@sn/api";
import PlayersPanel from "../../app/rally/PlayersPanel";
import type { PeopleResult, PeopleSample } from "../../app/rally/lib";

vi.mock("@sn/api", () => ({
  apiFetch: vi.fn(),
  apiForm: vi.fn(),
  errorText: (error: unknown) => String(error),
}));

const FINISHED: PeopleSample[] = [{ t_ms: 0, court: null, shuttle: null, people: [] }];

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
});

describe("PlayersPanel: finding the players of a match", () => {
  it("shows the result of a finished job as soon as the match opens", async () => {
    const onSamples = vi.fn();
    vi.mocked(apiFetch).mockResolvedValue({ status: "done", samples: FINISHED } as PeopleResult);

    render(<PlayersPanel matchId={3} onSamples={onSamples} />);

    await waitFor(() => expect(onSamples).toHaveBeenCalledWith(FINISHED));
    expect(screen.getByRole("status")).toHaveTextContent("The players are found.");
  });

  it("starts the job and reports it running", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ status: "idle", samples: [] } as PeopleResult) // on open
      .mockResolvedValueOnce({ status: "running", samples: [] }); // the start

    render(<PlayersPanel matchId={3} onSamples={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Find players" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Finding the players"));
    expect(apiFetch).toHaveBeenCalledWith("/api/rally/matches/3/people", { method: "POST" });
    expect(screen.getByRole("button", { name: "Find players" })).toBeDisabled();
  });

  it("delivers the samples when the running job is done", async () => {
    const onSamples = vi.fn();
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ status: "running", samples: [] } as PeopleResult) // on open: a job is already running
      .mockResolvedValue({ status: "done", samples: FINISHED } as PeopleResult); // the polls

    render(<PlayersPanel matchId={3} onSamples={onSamples} />);

    await waitFor(() => expect(onSamples).toHaveBeenCalledWith(FINISHED), { timeout: 5000 });
    expect(screen.getByRole("status")).toHaveTextContent("The players are found.");
  });

  it("says so when the job fails", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ status: "idle", samples: [] } as PeopleResult)
      .mockResolvedValueOnce({ status: "running", samples: [] })
      .mockResolvedValue({ status: "failed", samples: [] } as PeopleResult);

    render(<PlayersPanel matchId={3} onSamples={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Find players" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("could not be found"), { timeout: 5000 });
  });
});
