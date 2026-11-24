import { chatApi } from "./api";

/** Where the game of a room is played on a page of its own (the pages of the Werewolf are a part of this app). */
const gamePath = (code: string): string => `/werewolf/room/${code}`;

/**
 * The room's Werewolf game, ready for me: the chat makes it the first time (a seat for each member) and seats me in it, or says
 * why it cannot (a game under way, a full one, too many games, no room left: see `errors.ts`). `follow`: the room's people changed, so the game
 * only follows them (no virtual people are added to fill the seats: that is for the first time).
 */
export async function prepareGame(slug: string, follow = false): Promise<{ code: string; href: string }> {
  const { code } = await chatApi.game(slug, follow);
  return { code, href: gamePath(code) };
}
