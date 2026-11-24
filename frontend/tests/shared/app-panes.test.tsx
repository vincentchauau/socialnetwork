import type React from "react";
import SplitPanel from "@sn/compounds/SplitPanel";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { appPanes } from "../../app/chat/dock/ChatDock";

const panes = (page: string, pageLabel: string | undefined, Library: (() => React.JSX.Element) | undefined, extra: Parameters<typeof appPanes>[3]) => (
  <SplitPanel panes={appPanes(<p>{page}</p>, pageLabel, Library, extra)} label="Tables" storageKey="test_app_panes" />
);

describe("appPanes: the panes of an app beside its page", () => {
  it("shows the page alone when the app has no library and no extra pane", () => {
    render(panes("the page", undefined, undefined, []));
    expect(screen.getByText("the page")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Grid" })).toBeNull();
  });

  it("shows the page, the library and a visible extra pane at first; a hidden pane stays closed", async () => {
    const Library = () => <p>the library</p>;
    render(
      panes("the page", undefined, Library, [
        { key: "x", label: "Extra pane", node: <p>extra body</p>, defaultVisible: true },
        { key: "y", label: "Hidden pane", node: <p>hidden body</p> },
      ]),
    );
    expect(screen.getByText("the page")).toBeVisible();
    expect(screen.getByText("the library")).toBeVisible();
    expect(screen.getByText("extra body")).toBeVisible();
    expect(screen.queryByText("hidden body")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Grid" }));
    expect(screen.getByText("the library")).not.toBeVisible();
  });

  it("gives the page a button only when it has a label", () => {
    const { unmount } = render(panes("the page", "Database", undefined, []));
    expect(screen.getByRole("button", { name: "Database" })).toBeInTheDocument();
    unmount();
    render(panes("the page", undefined, undefined, []));
    expect(screen.queryByRole("button", { name: "Database" })).toBeNull();
  });
});
