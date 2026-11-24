import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmModal, LabelTextBox, TagBox } from "@sn/ui";

describe("ConfirmModal", () => {
  it("renders nothing while closed", () => {
    const { container } = render(<ConfirmModal open={false} message="Sure?" onConfirm={() => {}} onCancel={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("confirms, cancels, and cancels on Escape or a backdrop click", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<ConfirmModal open message="Delete this?" onConfirm={onConfirm} onCancel={onCancel} />);
    expect(screen.getByRole("alertdialog", { name: "Delete this?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.mouseDown(screen.getByTestId("confirm-backdrop"));
    expect(onCancel).toHaveBeenCalledTimes(3);
  });

  it("a click inside the dialog does not cancel, and the labels can be changed", () => {
    const onCancel = vi.fn();
    render(<ConfirmModal open message="Xóa?" confirmLabel="Xóa" cancelLabel="Hủy" onConfirm={() => {}} onCancel={onCancel} />);
    fireEvent.mouseDown(screen.getByRole("alertdialog"));
    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Hủy" })).toBeInTheDocument();
  });
});

describe("LabelTextBox", () => {
  it("ties the label to the field and reports changes", () => {
    const onChange = vi.fn();
    render(<LabelTextBox label="Name" name="name" value="Ann" onChange={onChange} />);
    const input = screen.getByLabelText("Name");
    expect(input).toHaveValue("Ann");
    fireEvent.change(input, { target: { value: "Bob" } });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("renders a textarea, keeps zero, and passes the flags through", () => {
    render(<LabelTextBox label="Bio" name="bio" value={0} type="textarea" rows={4} required readOnly />);
    const area = screen.getByLabelText("Bio");
    expect(area.tagName).toBe("TEXTAREA");
    expect(area).toHaveValue("0");
    expect(area).toBeRequired();
    expect(area).toHaveAttribute("readonly");
  });

  it("treats null as empty", () => {
    render(<LabelTextBox label="Name" name="name" value={null} />);
    expect(screen.getByLabelText("Name")).toHaveValue("");
  });
});

describe("TagBox", () => {
  function setup(initial: string[] = [], suggestions: string[] = []) {
    const onChange = vi.fn();
    render(<TagBox label="Tags" value={initial} onChange={onChange} suggestions={suggestions} />);
    return { onChange, input: screen.getByLabelText("Tags", { selector: "input" }) };
  }

  it("adds a tag on Enter and on comma, trimmed", () => {
    const { onChange, input } = setup();
    fireEvent.change(input, { target: { value: "  art " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenLastCalledWith(["art"]);
    fireEvent.change(input, { target: { value: "ink" } });
    fireEvent.keyDown(input, { key: "," });
    expect(onChange).toHaveBeenLastCalledWith(["ink"]);
  });

  it("does not add duplicates or empty tags", () => {
    const { onChange, input } = setup(["art"]);
    fireEvent.change(input, { target: { value: "art" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("removes the last tag with Backspace on an empty box and any tag with its button", () => {
    const { onChange, input } = setup(["a", "b"]);
    fireEvent.keyDown(input, { key: "Backspace" });
    expect(onChange).toHaveBeenLastCalledWith(["a"]);
    fireEvent.click(screen.getByRole("button", { name: "Remove a" }));
    expect(onChange).toHaveBeenLastCalledWith(["b"]);
  });

  it("filters suggestions, hides ones already chosen, and picks one with the mouse", () => {
    const { onChange, input } = setup(["oil"], ["oil paint", "ink", "ink wash", "acrylic"]);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: "ink" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["ink", "ink wash"]);
    fireEvent.mouseDown(screen.getByRole("option", { name: "ink wash" }));
    expect(onChange).toHaveBeenLastCalledWith(["oil", "ink wash"]);
  });

  it("matches suggestions case-insensitively", () => {
    const { input } = setup([], ["Watercolor"]);
    fireEvent.change(input, { target: { value: "WATER" } });
    expect(screen.getByRole("option", { name: "Watercolor" })).toBeInTheDocument();
  });
});
