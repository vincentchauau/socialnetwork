"use client";

interface Props {
  username: string;
  headerShown: boolean;
  onToggleHeader: () => void;
  onTheme: () => void;
}

const go = (path: string) => () => window.location.assign(path);

/** The ChatWork nav row: avatar, Hide/Show, Theme, Home, File, Database. */
export default function NavBar({ username, headerShown, onToggleHeader, onTheme }: Props) {
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
      <button type="button" onClick={go("/")}>Home</button>
      <button type="button" onClick={go("/work")}>File</button>
      <button type="button" onClick={go("/work")}>Database</button>
    </nav>
  );
}
