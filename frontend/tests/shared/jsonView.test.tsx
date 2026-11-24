import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import JsonView from "@sn/elements/JsonView";

describe("JsonView", () => {
  it("shows every key and value of an array of objects, in plain sight", () => {
    render(<JsonView value={[{ kind: "straight", pick: 5, payout: 0 }]} />);
    expect(screen.getByText("kind")).toBeInTheDocument();
    expect(screen.getByText("straight")).toBeInTheDocument();
    expect(screen.getByText("pick")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("shows null, an empty array and a scalar", () => {
    const { rerender } = render(<JsonView value={{ note: null, items: [] }} />);
    expect(screen.getByText("null")).toBeInTheDocument();
    expect(screen.getByText("[ ]")).toBeInTheDocument();
    rerender(<JsonView value="plain" />);
    expect(screen.getByText("plain")).toBeInTheDocument();
  });
});
