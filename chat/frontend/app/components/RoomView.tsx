"use client";

import type { ReactNode } from "react";

import type { ConnStatus } from "../useRoomChat";
import { useRoomChat } from "../useRoomChat";
import Composer from "./Composer";
import MessageLog from "./MessageLog";
import Split from "./Split";

const STATUS_TEXT: Record<ConnStatus, string> = {
  connecting: "Đang kết nối…",
  open: "Đã kết nối",
  reconnecting: "Mất kết nối, đang thử lại…",
  closed: "Đã ngắt kết nối",
};

export interface ColumnsControl {
  text: string;
  onChange: (text: string) => void;
  onBlur: () => void;
}

interface FrameProps {
  columns: number;
  control: ColumnsControl;
  grid: ReactNode;
  bottom: ReactNode;
}

/** Right-hand side: Columns + member grid on top, composer + room messages below. */
function Frame({ columns, control, grid, bottom }: FrameProps) {
  return (
    <Split
      id="messageSplitter"
      direction="vertical"
      percent={60}
      containerClass="fullColumnContainer"
      firstClass="columnContainer"
      secondClass="columnContainer"
      first={
        <>
          <div className="rowContainer">
            <label htmlFor="columns-input">Columns:</label>
            <input
              id="columns-input"
              type="number"
              min={1}
              max={10}
              value={control.text}
              onChange={(event) => control.onChange(event.target.value)}
              onBlur={control.onBlur}
            />
          </div>
          <div className="maxGridContainer" style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}>
            {grid}
          </div>
        </>
      }
      second={bottom}
    />
  );
}

/** Nothing joined yet: the same layout with an inert composer. */
export function IdleView({ columns, control }: { columns: number; control: ColumnsControl }) {
  return (
    <Frame
      columns={columns}
      control={control}
      grid={null}
      bottom={
        <>
          <div className="rowContainer">
            <input type="text" placeholder="Enter message..." disabled aria-label="Tin nhắn" />
            <button type="button" style={{ flex: 0, width: 50 }} disabled>
              Send
            </button>
          </div>
          <div className="maxColumnContainer">
            <h3 id="room">Room:</h3>
            <p style={{ lineHeight: 1.5 }}>Chọn một phòng hoặc tạo phòng mới để bắt đầu chat.</p>
          </div>
        </>
      }
    />
  );
}

interface Props {
  room: string;
  columns: number;
  control: ColumnsControl;
}

export default function RoomView({ room, columns, control }: Props) {
  const chat = useRoomChat(room);
  const members = chat.presence?.members ?? [];
  const hidden = chat.presence ? Math.max(0, chat.presence.total - members.length) : 0;

  return (
    <Frame
      columns={columns}
      control={control}
      grid={
        <>
          {members.map((member) => (
            <div key={member.userId} className="grid-item">
              <div className="file-preview" aria-hidden="true" style={{ background: "inherit", aspectRatio: "auto", height: 80 }}>
                <span className="emoji">{member.username.slice(0, 1).toUpperCase()}</span>
              </div>
              <div className="file-name">{member.username}</div>
            </div>
          ))}
          {hidden > 0 && (
            <div className="grid-item">
              <div className="file-name">{`+${hidden} người khác`}</div>
            </div>
          )}
        </>
      }
      bottom={
        <>
          <Composer disabled={chat.status !== "open"} onSend={chat.send} />
          <div className="maxColumnContainer">
            <h3 id="room">{`Room: ${room}`}</h3>
            <p role="status" style={{ fontSize: "0.8em", lineHeight: 1.5, margin: 0 }}>
              {STATUS_TEXT[chat.status]}
            </p>
            {chat.notice && <p role="alert" style={{ lineHeight: 1.5 }}>{chat.notice}</p>}
            {chat.stopped === "session" && (
              <p>
                Hãy <a href="/login">đăng nhập</a> lại để tiếp tục chat.
              </p>
            )}
            {chat.stopped === "refused" && (
              <button type="button" onClick={chat.retry}>
                Thử lại
              </button>
            )}
            <MessageLog messages={chat.messages} system={chat.system} />
          </div>
        </>
      }
    />
  );
}
