"use client";

import AuthGate from "./AuthGate";
import ChatApp from "./components/ChatApp";

export default function ChatPage() {
  return <AuthGate title="Chat">{(user) => <ChatApp username={user.username} />}</AuthGate>;
}
