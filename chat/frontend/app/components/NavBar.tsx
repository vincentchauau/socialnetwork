"use client";

import { useState } from "react";

import HelpDialog from "./HelpDialog";

interface Props {
  username: string;
  headerShown: boolean;
  onToggleHeader: () => void;
  onTheme: () => void;
}

export default function NavBar({ username, headerShown, onToggleHeader, onTheme }: Props) {
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <nav className="topnav" aria-label="Điều hướng">
      <button type="button" aria-label="Trợ giúp" aria-haspopup="dialog" onClick={() => setHelpOpen(true)}>
        ?
      </button>
      <span className="user-chip">
        <span>{username}</span>
        <a href="/login">Đổi tài khoản</a>
      </span>
      <button type="button" aria-controls="page-header" aria-expanded={headerShown} onClick={onToggleHeader}>
        {headerShown ? "Hide" : "Show"}
      </button>
      <button type="button" onClick={onTheme}>
        Theme
      </button>
      <a className="nav-link" href="/">
        Home
      </a>
      <a className="nav-link" href="/work">
        File
      </a>
      <a className="nav-link" href="/work">
        Database
      </a>
      {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
    </nav>
  );
}
