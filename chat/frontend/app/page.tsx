"use client";

import AuthGate from "./AuthGate";
import ChatApp from "./components/ChatApp";

export default function ChatPage() {
  return (
    <AuthGate title="Chat">
      {(user) => (
        <div className="stack">
          <div className="page-head">
            <h1>Chat</h1>
            <span className="muted">{user.username}</span>
            <a href="/">← Trang chủ</a>
          </div>
          <ChatApp username={user.username} />
        </div>
      )}
    </AuthGate>
  );
}
