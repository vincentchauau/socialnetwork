"use client";

export type View = "file" | "database" | "calls";

interface Props {
  username: string;
  view: View;
  isAdmin: boolean;
  headerShown: boolean;
  onToggleHeader: () => void;
  onTheme: () => void;
  onView: (view: View) => void;
}

const go = (path: string) => () => window.location.assign(path);

/** The ChatWork nav row. File and Database switch the page area; Home and Chat leave it. */
export default function NavBar({ username, view, isAdmin, headerShown, onToggleHeader, onTheme, onView }: Props) {
  return (
    <nav className="rowContainer" aria-label="Điều hướng">
      <div id="signin_container" style={{ display: "flex", width: 220, height: 40 }}>
        <div
          id="signin_avatar"
          aria-hidden="true"
          style={{ width: 40, height: 40, display: "grid", placeItems: "center", fontWeight: "bold" }}
        >
          {username.slice(0, 1).toUpperCase()}
        </div>
        <button type="button" onClick={go("/login")} title="Đổi tài khoản">
          {username}
        </button>
      </div>
      <button type="button" aria-controls="page-header page-footer" onClick={onToggleHeader}>
        {headerShown ? "Hide" : "Show"}
      </button>
      <button type="button" onClick={onTheme}>
        Theme
      </button>
      <button type="button" onClick={go("/")}>
        Home
      </button>
      <button type="button" onClick={go("/chat")}>
        Chat
      </button>
      <button type="button" aria-pressed={view === "file"} onClick={() => onView("file")}>
        File
      </button>
      <button type="button" aria-pressed={view === "database"} onClick={() => onView("database")}>
        Database
      </button>
      {isAdmin && (
        <button type="button" aria-pressed={view === "calls"} onClick={() => onView("calls")}>
          Calls
        </button>
      )}
    </nav>
  );
}
