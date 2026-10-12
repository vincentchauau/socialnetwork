export interface ChatMessage {
  id: number;
  room: string;
  username: string;
  content: string;
  created_at: string;
}

export type ServerEvent = ChatMessage | { error: string };

/** Merge two lists of messages, dropping duplicates by id and keeping id order. */
export function mergeMessages(
  history: readonly ChatMessage[],
  live: readonly ChatMessage[],
): ChatMessage[] {
  const byId = new Map<number, ChatMessage>();
  for (const message of [...history, ...live]) byId.set(message.id, message);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

/** Parse a server frame; null when it is not a message or an error object. */
export function parseServerEvent(raw: string): ServerEvent | null {
  try {
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return null;
    if ("error" in data && typeof data.error === "string") return { error: data.error };
    if ("id" in data && "content" in data) return data as ChatMessage;
  } catch {
    // not JSON
  }
  return null;
}
