import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { type FieldSpec, SchemaForm } from "@sn/ui";

const FIELDS: FieldSpec[] = [
  { name: "title", label: "Title", kind: "text", required: true, max: 10 },
  { name: "about", label: "About", kind: "textarea" },
  { name: "salary", label: "Salary", kind: "number", min: 0 },
  { name: "kind", label: "Kind", kind: "select", required: true, value: "full_time", options: [{ value: "full_time", label: "Full time" }, { value: "contract", label: "Contract" }] },
  { name: "remote", label: "Remote", kind: "checkbox" },
  { name: "tags", label: "Tags", kind: "tags" },
];

describe("SchemaForm", () => {
  it("collects typed values and leaves out the optional ones left empty", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<SchemaForm fields={FIELDS} submitLabel="Send" onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText("Title"), "Python dev");
    await user.type(screen.getByLabelText("Salary"), "1200");
    await user.selectOptions(screen.getByLabelText("Kind"), "contract");
    await user.click(screen.getByLabelText("Remote"));
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toEqual({ title: "Python dev", salary: 1200, kind: "contract", remote: true });  // no "about", no "tags"
  });

  it("refuses a missing required field before anything is sent", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<SchemaForm fields={FIELDS} submitLabel="Send" onSubmit={onSubmit} requiredMessage={(label) => `Fill in ${label}`} />);
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Fill in Title");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("starts from the given values, limits the length of a text, and shows the error of the last try", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    const fields: FieldSpec[] = [{ name: "title", label: "Title", kind: "text", required: true, max: 5, value: "abc" }, { name: "tags", label: "Tags", kind: "tags", value: ["x"] }];
    render(<SchemaForm fields={fields} submitLabel="Save" onSubmit={onSubmit} error="Title is too short" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Title is too short");
    await user.type(screen.getByLabelText("Title"), "defgh");
    expect(screen.getByLabelText("Title")).toHaveValue("abcde");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ title: "abcde", tags: ["x"] }));
  });

  it("can be cancelled and is closed to input while it is busy", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<SchemaForm fields={FIELDS} submitLabel="Send" cancelLabel="Never mind" onCancel={onCancel} onSubmit={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Never mind" }));
    expect(onCancel).toHaveBeenCalled();
    rerender(<SchemaForm fields={FIELDS} submitLabel="Send" onSubmit={vi.fn()} busy />);
    expect(screen.getByLabelText("Title")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});


describe("SchemaForm with a file", () => {
  const FILE_FIELDS: FieldSpec[] = [{ name: "file", label: "Photo", kind: "file", required: true, accept: "image/*", max_mb: 1 }, { name: "caption", label: "Caption", kind: "text" }];

  it("sends the chosen file with the other values, and asks for one when there is none", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<SchemaForm fields={FILE_FIELDS} submitLabel="Share" onSubmit={onSubmit} requiredMessage={(label) => `Choose ${label}`} />);
    await user.click(screen.getByRole("button", { name: "Share" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose Photo");
    const file = new File(["x"], "a.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Photo"), file);
    await user.type(screen.getByLabelText("Caption"), "red");
    await user.click(screen.getByRole("button", { name: "Share" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toEqual({ file, caption: "red" });
    expect(screen.getByLabelText("Photo")).toHaveAttribute("accept", "image/*");
  });

  it("refuses a file bigger than the limit before anything is sent", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<SchemaForm fields={FILE_FIELDS} submitLabel="Share" onSubmit={onSubmit} tooBigMessage={(label, mb) => `${label} over ${mb} MB`} />);
    await user.upload(screen.getByLabelText("Photo"), new File([new Uint8Array(1024 * 1024 + 1)], "big.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Share" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Photo over 1 MB");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
