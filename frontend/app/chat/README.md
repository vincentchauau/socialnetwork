# chatwork

The pages of the chat and work backends (`backend/api/chat`, `backend/api/file or /api/database`), a folder of the one frontend `frontend`.

| Address | Page |
|---|---|
| `/chat` | the full chat (rooms, messages, over `/api/chat`); not in the menu: the chat of each app is the dock under its page |
| `/chat/people` | people: search, friend requests, companions, friends, notices, blocked (not in the menu; the old `/social` redirects here) |
| `/chat/people/<username>` | the profile of one person, with the actions (friend, block, report, message) |
| `/chat/werewolf` | the Werewolf: the chat limited to the rooms of the category `werewolf` (a game starts with the button of a room), with the rules and the history |
| `/chat/werewolf/room/<code>`, `/chat/werewolf/history` | the game of a room, and the games played |

Code: here (`components/`, `dock/`, the hooks and `api.ts`), `PersonActions` (the buttons of a person in the members table of a room, over `socialApi` in `api.ts`, `/api/chat`), and the apps `werewolf/` and `face/`. A folder without a `page.tsx` is not a route. Tests: `frontend/tests/chat`.
