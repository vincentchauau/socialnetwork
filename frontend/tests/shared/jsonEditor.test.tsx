import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import JsonEditor, { jsonProblem } from "@sn/compounds/JsonEditor";

describe("JsonEditor", () => {
  it("reports text that is not valid json, and accepts an empty text as no value", () => {
    expect(jsonProblem('{"a": 1}', "links")).toBeNull();
    expect(jsonProblem("", "links")).toBeNull();
    expect(jsonProblem("{a:", "links")).not.toBeNull();
  });

  it("shows the problem when the text is not valid json", () => {
    render(<JsonEditor label="links" value="{a:" onChange={vi.fn()} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("shows the json only, without an editor, when read-only", () => {
    render(<JsonEditor label="links" value='{"a":1}' readOnly />);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByLabelText("links")).toHaveTextContent('{"a":1}');
  });
});
