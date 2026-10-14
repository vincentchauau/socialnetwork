"use client";

import type { ConnStatus } from "../useRoomChat";
import { useRoomChat } from "../useRoomChat";
import Composer from "./Composer";
import MembersPanel from "./MembersPanel";
import MessageLog from "./MessageLog";

const STATUS_TEXT: Record<ConnStatus, string> = {
  connecting: "Đang kết nối…",
  open: "Đã kết nối",
  reconnecting: "Mất kết nối, đang thử lại…",
  closed: "Đã ngắt kết nối",
};

interface Props {
  room: string;
  username: string;
  columns: number;
}

export default function RoomView({ room, username, columns }: Props) {
  const chat = useRoomChat(room);

  return (
    <div className="room-view stack">
      <span className={`status status-${chat.status}`} role="status">
        {STATUS_TEXT[chat.status]}
      </span>

      {chat.notice && (
        <p role="alert" className="error">
          {chat.notice}
        </p>
      )}
      {chat.stopped === "session" && (
        <p>
          Hãy <a href="/login">đăng nhập</a> lại để tiếp tục chat.
        </p>
      )}
      {chat.stopped === "refused" && (
        <button type="button" className="secondary" onClick={chat.retry}>
          Thử lại
        </button>
      )}

      <Composer disabled={chat.status !== "open"} onSend={chat.send} />
      <MessageLog messages={chat.messages} system={chat.system} username={username} columns={columns} />
      <MembersPanel presence={chat.presence} />
    </div>
  );
}
