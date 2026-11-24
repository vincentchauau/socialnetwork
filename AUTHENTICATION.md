# Authentication flows by message sequence

Notation:

- **A**: the device or browser that wants to sign in (the requester).
- **S**: the server (`center` backend).
- **B**: the witness: a second device, app, mailbox, SIM, secure chip or identity provider that vouches for the user.
- **G**: Google (identity provider).
- `→` travels over the network. `⇢` travels through the user's eyes or hands (reading a code, scanning a QR, typing a value).

## Mechanisms grouped by sequence

| Sequence | Mechanisms | Security level | Characteristics |
|---|---|---|---|
| `A → S` | Password, webcam (face), voice | Password: Medium. Webcam, voice: Low | One step, no separate B. The proof goes straight to the server |
| `B ⇢ A → S` | TOTP, recovery codes | TOTP: Fair. Recovery codes: Medium | B makes no network call. The user reads a value on B and types it into A |
| `A → S → B ⇢ A → S` | Email, SMS | Email: Medium. SMS: Low | The server sends a one-time code to B. The user carries the code back and types it into A |
| `A → G → A → S` | Google | Fair | B is Google. A signed token passes through A to the server |
| `A → S → A → B → A → S` | Passkey | High | The server sends a challenge. B (the secure chip in the device) signs it. The signature passes through A back to the server |
| `A → S → A ⇢ B → S → A` | QR code | Medium | B reads the QR from A's screen, then **B calls the server directly**. The server issues the session to A |

## Security level

| Level | Why |
|---|---|
| **High** | Passkey. Phishing-resistant (bound to the site's origin), the server stores only a public key, user verification is required |
| **Fair** | TOTP (a user can still be tricked into typing a live code into a fake page), Google (as safe as the user's Google account) |
| **Medium** | Password (can be leaked or guessed), email (depends on the mailbox), QR code (a user can approve an attacker's request, mitigated by the typed 4-character code and device details), recovery codes (single use, safe only if stored well) |
| **Low** | SMS (SIM swap, number recycling). Webcam and voice (a photo, video or recording can fool them; webcam has a best-effort liveness challenge, voice has none; not tested with real people) |
