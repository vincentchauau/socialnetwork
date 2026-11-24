# Danh sách API

Tổng 155 route (không tính `market`, `job` tạm dừng và route `/records` dùng chung). Moderator chỉ CRU; admin CRUD; user theo quyền từng route.

| Module | File | Method | Đường dẫn | CRUD | Groups có thể gọi |
|---|---|---|---|---|---|
| center | center/routes_account.py | POST | `/password` | C | admin, moderator, user |
| center | center/routes_account.py | POST | `/google` | C | admin, moderator, user |
| center | center/routes_account.py | DELETE | `/google` | D | admin, user |
| center | center/routes_account.py | DELETE | `` | D | admin, user |
| center | center/routes_account.py | POST | `/username` | C | admin, moderator, user |
| center | center/routes_auth.py | GET | `/config` | R | public |
| center | center/routes_auth.py | POST | `/register` | C | public |
| center | center/routes_auth.py | POST | `/login` | C | public |
| center | center/routes_auth.py | POST | `/refresh` | C | public |
| center | center/routes_auth.py | POST | `/logout` | C | public |
| center | center/routes_auth.py | GET | `/me` | R | public |
| center | center/routes_auth.py | POST | `/google` | C | public |
| center | center/routes_biometrics.py | POST | `/login/biometric` | C | public |
| center | center/routes_biometrics.py | PUT | `/me/biometric-2fa` | U | public |
| center | center/routes_email.py | POST | `/me/email` | C | public |
| center | center/routes_email.py | POST | `/email/verify` | C | public |
| center | center/routes_email.py | DELETE | `/me/email` | D | public |
| center | center/routes_email.py | POST | `/email/login/request` | C | public |
| center | center/routes_email.py | POST | `/email/login/verify` | C | public |
| center | center/routes_email.py | POST | `/email/login/magic` | C | public |
| center | center/routes_email.py | POST | `/password/forgot` | C | public |
| center | center/routes_email.py | POST | `/password/reset` | C | public |
| center | center/routes_passkeys.py | POST | `/passkey/options` | C | public |
| center | center/routes_passkeys.py | POST | `/passkey/login` | C | public |
| center | center/routes_passkeys.py | POST | `/register/passkey/options` | C | public |
| center | center/routes_passkeys.py | POST | `/me/passkeys/options` | C | public |
| center | center/routes_passkeys.py | POST | `/me/passkeys` | C | public |
| center | center/routes_passkeys.py | GET | `/me/passkeys` | R | public |
| center | center/routes_passkeys.py | PATCH | `/me/passkeys/{passkey_id}` | U | public |
| center | center/routes_passkeys.py | DELETE | `/me/passkeys/{passkey_id}` | D | public |
| center | center/routes_phone.py | POST | `/me/phone` | C | public |
| center | center/routes_phone.py | POST | `/me/phone/verify` | C | public |
| center | center/routes_phone.py | DELETE | `/me/phone` | D | public |
| center | center/routes_phone.py | POST | `/phone/login/request` | C | public |
| center | center/routes_phone.py | POST | `/phone/login/verify` | C | public |
| center | center/routes_profile.py | GET | `` | R | admin, moderator, user |
| center | center/routes_profile.py | PUT | `` | U | admin, moderator, user |
| center | center/routes_qr.py | POST | `/start` | C | public |
| center | center/routes_qr.py | POST | `/poll` | C | public |
| center | center/routes_qr.py | GET | `/{request_id}` | R | public |
| center | center/routes_qr.py | POST | `/{request_id}/approve` | C | public |
| center | center/routes_qr.py | POST | `/{request_id}/deny` | C | public |
| center | center/routes_reauth.py | GET | `/methods` | R | admin, moderator, user |
| center | center/routes_reauth.py | POST | `/passkey/options` | C | admin, moderator, user |
| center | center/routes_reauth.py | POST | `/passkey/verify` | C | admin, moderator, user |
| center | center/routes_reauth.py | POST | `/google` | C | admin, moderator, user |
| center | center/routes_reauth.py | POST | `/email/request` | C | admin, moderator, user |
| center | center/routes_reauth.py | POST | `/email/verify` | C | admin, moderator, user |
| center | center/routes_sessions.py | GET | `/sessions` | R | admin, moderator, user |
| center | center/routes_sessions.py | POST | `/sessions/revoke-others` | C | admin, moderator, user |
| center | center/routes_sessions.py | DELETE | `/sessions/{sid}` | D | admin, user |
| center | center/routes_totp.py | POST | `/totp/setup` | C | public |
| center | center/routes_totp.py | POST | `/totp/enable` | C | public |
| center | center/routes_totp.py | DELETE | `/totp` | D | public |
| center | center/routes_totp.py | POST | `/totp/recovery-codes` | C | public |
| center | center/routes_totp.py | POST | `/login/totp` | C | public |
| chat | chat/routes_calls.py | POST | `/rooms/{slug}/game` | C | admin, moderator, user |
| chat | chat/routes_inbox.py | GET | `/inbox/summary` | R | admin, moderator, user |
| chat | chat/routes_internal.py | POST | `/game-over` | C | public |
| chat | chat/routes_internal.py | POST | `/call-heard` | C | public |
| chat | chat/routes_meeting.py | POST | `/rooms/{slug}/meeting/start` | C | admin, moderator, user |
| chat | chat/routes_meeting.py | POST | `/rooms/{slug}/meeting/end` | C | admin, moderator, user |
| chat | chat/routes_meeting.py | GET | `/rooms/{slug}/meeting` | R | admin, moderator, user |
| chat | chat/routes_meeting.py | POST | `/rooms/{slug}/voice-message` | C | admin, moderator, user |
| chat | chat/routes_members.py | GET | `/rooms/{slug}/members` | R | admin, moderator, user |
| chat | chat/routes_members.py | GET | `/rooms/{slug}/members/{user_id}` | R | admin, moderator, user |
| chat | chat/routes_members.py | POST | `/rooms/{slug}/members` | C | admin, moderator, user |
| chat | chat/routes_members.py | PATCH | `/rooms/{slug}/members/{user_id}` | U | admin, moderator, user |
| chat | chat/routes_members.py | DELETE | `/rooms/{slug}/members/{user_id}` | D | admin, user |
| chat | chat/routes_members.py | POST | `/rooms/{slug}/virtual` | C | admin, moderator, user |
| chat | chat/routes_messages.py | GET | `/rooms/{slug}/messages` | R | admin, moderator, user |
| chat | chat/routes_messages.py | POST | `/rooms/{slug}/messages` | C | admin, moderator, user |
| chat | chat/routes_messages.py | PATCH | `/rooms/{slug}/messages/{message_id}` | U | admin, moderator, user |
| chat | chat/routes_messages.py | DELETE | `/rooms/{slug}/messages/{message_id}` | D | admin, user |
| chat | chat/routes_messages.py | PUT | `/rooms/{slug}/messages/{message_id}/pin` | U | admin, moderator, user |
| chat | chat/routes_messages.py | DELETE | `/rooms/{slug}/messages/{message_id}/pin` | D | admin, user |
| chat | chat/routes_messages.py | POST | `/rooms/{slug}/cards/{message_id}/submit` | C | admin, moderator, user |
| chat | chat/routes_messages.py | POST | `/rooms/{slug}/cards/{message_id}/act` | C | admin, moderator, user |
| chat | chat/routes_messages.py | POST | `/rooms/{slug}/cards/{message_id}/{action}` | C | admin, moderator, user |
| chat | chat/routes_people.py | GET | `/people/{username}` | R | admin, moderator, user |
| chat | chat/routes_people.py | POST | `/friends/{user_id}` | C | admin, moderator, user |
| chat | chat/routes_people.py | POST | `/friends/{user_id}/accept` | C | admin, moderator, user |
| chat | chat/routes_people.py | POST | `/friends/{user_id}/decline` | C | admin, moderator, user |
| chat | chat/routes_people.py | DELETE | `/friends/{user_id}` | D | admin, user |
| chat | chat/routes_people.py | POST | `/blocks/{user_id}` | C | admin, moderator, user |
| chat | chat/routes_people.py | DELETE | `/blocks/{user_id}` | D | admin, user |
| chat | chat/routes_people.py | POST | `/reports` | C | admin, moderator, user |
| chat | chat/routes_people.py | GET | `/reports/mine` | R | admin, moderator, user |
| chat | chat/routes_people.py | DELETE | `/reports/{report_id}` | D | admin, user |
| chat | chat/routes_people.py | GET | `/reports` | R | admin, moderator, user |
| chat | chat/routes_people.py | PATCH | `/reports/{report_id}` | U | admin, moderator, user |
| chat | chat/routes_rooms.py | POST | `/rooms` | C | admin, moderator, user |
| chat | chat/routes_rooms.py | GET | `/rooms` | R | admin, moderator, user |
| chat | chat/routes_rooms.py | GET | `/rooms/{slug}` | R | admin, moderator, user |
| chat | chat/routes_rooms.py | PATCH | `/rooms/{slug}` | U | admin, moderator, user |
| chat | chat/routes_rooms.py | DELETE | `/rooms/{slug}` | D | admin, user |
| chat | chat/routes_rooms.py | POST | `/rooms/{slug}/join` | C | admin, moderator, user |
| chat | chat/routes_rooms.py | POST | `/rooms/{slug}/leave` | C | admin, moderator, user |
| chat | chat/routes_rooms.py | POST | `/rooms/{slug}/hide` | C | admin, moderator, user |
| chat | chat/routes_rooms.py | POST | `/rooms/{slug}/transfer` | C | admin, moderator, user |
| chat | chat/routes_rooms.py | POST | `/rooms/{slug}/read` | C | admin, moderator, user |
| chat | chat/routes_rooms.py | POST | `/dm` | C | admin, moderator, user |
| chat | chat/routes_rooms.py | POST | `/rooms/{slug}/accept` | C | admin, moderator, user |
| chat | chat/routes_rooms.py | POST | `/rooms/{slug}/decline` | C | admin, moderator, user |
| face | face/measurements.py | POST | `/measurements` | C | admin, moderator, user |
| face | face/measurements.py | GET | `/measurements` | R | admin, moderator, user |
| face | face/measurements.py | PATCH | `/measurements/{measurement_id}` | U | admin, moderator, user |
| face | face/measurements.py | DELETE | `/measurements/{measurement_id}` | D | admin, user |
| face | face/measurements.py | DELETE | `/measurements` | D | admin, user |
| file | file/files.py | GET | `/entries` | R | admin, moderator, user |
| file | file/files.py | POST | `/folder` | C | admin, moderator, user |
| file | file/files.py | POST | `/upload` | C | admin, moderator, user |
| file | file/files.py | GET | `/versions` | R | admin, moderator, user |
| file | file/files.py | POST | `/versions/restore` | C | admin, moderator, user |
| file | file/files.py | DELETE | `/versions` | D | admin, user |
| file | file/files.py | GET | `/download` | R | admin, moderator, user |
| file | file/files.py | DELETE | `/entries` | D | admin, user |
| file | file/files.py | GET | `/trash` | R | admin, moderator, user |
| file | file/files.py | POST | `/trash/restore` | C | admin, moderator, user |
| file | file/files.py | DELETE | `/trash` | D | admin, user |
| file | file/files.py | POST | `/rename` | C | admin, moderator, user |
| file | file/sharing.py | POST | `/share` | C | public |
| file | file/sharing.py | GET | `/shares` | R | public |
| file | file/sharing.py | DELETE | `/share/{token}` | D | public |
| file | file/sharing.py | GET | `/shared/{token}` | R | public |
| file | file/sharing.py | GET | `/shared/{token}/download` | R | public |
| file | file/sharing.py | GET | `/search` | R | public |
| roulette | roulette/play.py | GET | `/wallet` | R | admin, moderator, user |
| roulette | roulette/play.py | POST | `/wallet/refill` | C | admin, moderator, user |
| roulette | roulette/play.py | POST | `/spin` | C | admin, moderator, user |
| roulette | roulette/play.py | GET | `/spins` | R | admin, moderator, user |
| roulette | roulette/play.py | DELETE | `/spins/{spin_id}` | D | admin, user |
| roulette | roulette/play.py | DELETE | `/spins` | D | admin, user |
| roulette | roulette/play.py | GET | `/stats` | R | admin, moderator, user |
| roulette | roulette/play.py | GET | `/board` | R | admin, moderator, user |
| werewolf | werewolf/internal.py | POST | `/ensure` | C | public |
| werewolf | werewolf/internal.py | DELETE | `/rooms/{code}` | D | public |
| werewolf | werewolf/routes.py | GET | `/setup/meta` | R | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | GET | `/rooms` | R | admin, moderator, user |
| werewolf | werewolf/routes.py | GET | `/rooms/{code}` | R | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/join` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/leave` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/start` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/options` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/roles` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/bots` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/action` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/chat` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/force` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/rematch` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | POST | `/rooms/{code}/reset` | C | admin, moderator, user |
| werewolf | werewolf/routes.py | GET | `/rooms/{code}/perspective/{seat}` | R | admin, moderator, user |
| werewolf | werewolf/routes.py | GET | `/leaderboard` | R | admin, moderator, user |
| werewolf | werewolf/routes.py | GET | `/me/history` | R | admin, moderator, user |
