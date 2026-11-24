import { AuthGate } from "@sn/compounds/AuthGate";
import ChatDock from "../../app/chat/dock/ChatDock";

export default function ChatPage() {
  return <AuthGate title="Chat">{() => <ChatDock app="chat" fill start={{ rooms: true, members: true, messages: true }} />}</AuthGate>;
}
