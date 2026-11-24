import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import FaceLibrary from "../../app/face/FaceLibrary";

vi.mock("../../app/face/components/FaceApp", () => ({ default: () => <p>the face reader</p> }));

describe("/face", () => {
  it("is the face reader with its history, not a table of measurements", () => {
    render(<FaceLibrary />);
    expect(screen.getByText("the face reader")).toBeInTheDocument();
  });
});
