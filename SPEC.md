# socialnetwork

_Updated to match the code on 2026-11-23._

Modular monolith: one FastAPI process, one Next.js app, one Postgres database, one nginx gateway.

Order of work: Requirements → Database → Backend → Backend test (unit test) → Frontend → Frontend test (UI test) → Local setup and deploy.

## How to write this document

- **Requirements:** describe at least the main features of each app.
- **Database:** describe every table and its columns, at least for each app.
- **Backend:** describe the shared functions, at least; describe every API, at least for each app.
- **Backend test:** the results of the unit tests.
- **Frontend:** describe the shared components, at least; describe every component, at least for each app.
- **Frontend test:** the results of the UI tests.
- **Local setup and deploy:** how to run the project locally and how to deploy it.

## Working rules

- **Split and merge:** split a piece of logic that is used two or more times, or that is too long; merge a piece used once, or too short.
- **Size limits:** a function is at most 100 lines; a file is at most 1000 lines.
- **Errors:** always use try/except.
- **Names:** no leading underscore (`_`) in names.
- **Language:** code and comments in English.
- **Features:** as few features as possible.
- **Tables and columns:** as few tables and columns as possible.
- **APIs:** as few APIs as possible.
- **Components:** as few components as possible.
- **Tests before merge:** run the unit tests before merging into `main`.
- **Tests after merge:** run the UI tests after merging into `main`.

# 1. Requirements

Human needs and the apps that serve them.

| Need | Apps |
|---|---|
| Eating | Market (Shop, Cart, Pay, My orders) |
| Sleeping | None |
| Learning | Market (books, materials), Chat (group rooms and calls), File (documents) |
| Working | Jobs (search, apply, post jobs), Market (Sell), Chat |
| Social | Chat (rooms, messages, friends, calls), Werewolf, Roulette, Rally (match videos), Users (profile) |
| Self-awareness | Users (profile), Face (symmetry score and history) |

## Users (center)

Each person has one account.

### Authentication flows by message sequence

Notation:

- **A**: the device or browser that wants to sign in (the requester).
- **S**: the server (`center` backend).
- **B**: the witness: a second device, app, mailbox, SIM, secure chip or identity provider that vouches for the user.
- **G**: Google (identity provider).
- `→` travels over the network. `⇢` travels through the user's eyes or hands (reading a code, scanning a QR, typing a value).

#### Mechanisms grouped by sequence

| Sequence | Mechanisms | Security level | Characteristics |
|---|---|---|---|
| `A → S` | Password, webcam (face), voice | Password: Medium. Webcam, voice: Low | One step, no separate B. The proof goes straight to the server |
| `B ⇢ A → S` | TOTP, recovery codes | TOTP: Fair. Recovery codes: Medium | B makes no network call. The user reads a value on B and types it into A |
| `A → S → B ⇢ A → S` | Email, SMS | Email: Medium. SMS: Low | The server sends a one-time code to B. The user carries the code back and types it into A |
| `A → G → A → S` | Google | Fair | B is Google. A signed token passes through A to the server |
| `A → S → A → B → A → S` | Passkey | High | The server sends a challenge. B (the secure chip in the device) signs it. The signature passes through A back to the server |
| `A → S → A ⇢ B → S → A` | QR code | Medium | B reads the QR from A's screen, then **B calls the server directly**. The server issues the session to A |

#### Security level

| Level | Why |
|---|---|
| **High** | Passkey. Phishing-resistant (bound to the site's origin), the server stores only a public key, user verification is required |
| **Fair** | TOTP (a user can still be tricked into typing a live code into a fake page), Google (as safe as the user's Google account) |
| **Medium** | Password (can be leaked or guessed), email (depends on the mailbox), QR code (a user can approve an attacker's request, mitigated by the typed 4-character code and device details), recovery codes (single use, safe only if stored well) |
| **Low** | SMS (SIM swap, number recycling). Webcam and voice (a photo, video or recording can fool them; webcam has a best-effort liveness challenge, voice has none; not tested with real people) |

### Sign up

1. A username, a password, an email, a phone, Google, a passkey, voice, face, or several of these together. A profile can be filled in at the same time.
   - Planned: the username may be left empty and the system makes one.
   - Current code: `POST /auth/register` requires `username`.
2. The email is verified.
3. After sign-up, the person is told once: the username made for them (if they left it empty), the address the confirmation mail went to, and any profile part that did not save.

### Sign in

1. With a password, an emailed code or link, an SMS code, Google, a passkey, voice, face, or a QR code approved on a phone that is already signed in.
2. Second factor: TOTP with recovery codes, or voice or face (liveness optional).
3. A forgotten password is reset through a link sent by email.
4. Signing out ends the current session.

### Update (signed in)

1. Change the password (set or change), link or unlink Google, add, verify and remove an email and a phone, add, rename and remove passkeys, manage second factors, change the username, edit the profile, and delete the account.
2. Sessions: each device is a session. A person can see all sessions, end one, or end all the others.
3. Username: changed at most once in 30 days. The old name is reserved for its previous owner for 30 days. Uniqueness does not depend on case.
4. A risky change (password, email, phone, username, second factor, or account deletion) asks the person to sign in again first.
5. Profile: name, headline, summary, birth date, address, city, region, country, picture, links, experience, education, skills, languages, certifications, projects, and the visibility of each part.
6. CV: the page `/user/cv` shows your own CV in full, and `/user/cv?u=<name>` shows someone else's, with only the parts the visibility setting allows for that viewer (owner; any signed-in person sees "employers" and "public"; anyone sees "public"). A hidden part is shown as hidden.
7. CV export: to PDF only, through the browser print dialog ("Save as PDF"). There is no JSON export and no CV import (PDF or DOCX import is not supported).
8. Delete account: an account event is published, and every module removes or anonymizes its rows. The deleted user is id `0`.

---

## Chat

### Rooms

1. A room is a chat (many people) or a chat of two. A room is Public (anyone can join) or Private (the owner approves people). A room is open or closed, and has a category and a capacity.
2. Every room has one owner: its maker. A chat of two is always Private. There are no moderators.
3. A person can join, leave, open or close a room. The owner can edit the room, approve or decline people, close or reopen it, and hand over ownership.
4. The owner cannot leave while others are in the room until ownership is handed over. The last person to leave closes the room. An ownerless room goes to the next person who joins.
5. Changing a room from Public to Private keeps the pending people. Changing it from Private to Public lets them in.
6. A deleted room is kept until its owner erases it.

### Members

1. A member can add or remove a friend, report or unreport a person, block or unblock a person, message, share a link, and invite people. The owner can mute or unmute, hand over ownership, ban or unban, and kick.
2. Invite by name: in a Public room the person joins at once; in a Private room the owner decides. A kicked person returns only if the owner brings them back.
3. Friends: a friend request is accepted or declined. A virtual person is a friend at once. Blocking stops the two people from seeing each other and ends their chat of two. A report goes to the admins and can be withdrawn while it is open.
4. Chat of two: named after the other person for each viewer. A friend can open it at once. A stranger sends a request: up to 3 messages are allowed meanwhile, a refusal is final, and at most 20 requests wait.
5. A virtual person behaves like a real one: friend at once, can be written to, muted, banned, kicked, made owner, reported and blocked, and always shows as online.

### Messages

1. A member can send, edit or remove their own message, reply, report someone else's message, and pin any message.
2. The owner can remove any message.
3. A member sees unread counts, can mute notices, and can hide a room.
4. Virtual people answer in the room. They never answer each other, and only a few answer any one message.
5. A virtual person's commands run with the asker's own authority. A read-only command runs at once. A change needs the asker's confirmation before it runs. Commands cover the market (search, product, cart, orders, add to cart, checkout, pay), jobs (apply, saved, applicants), selling, posting jobs, documents and questions, scripts, face and profile.
6. Presence is shared across copies of the chat. The system account posts the announcements of what happens in a room.

### Calls

1. A call belongs to a room. Before the call starts, nothing is shown.
2. A member starts a call and gets a ticket valid for 2 hours for a video room with a random name.
3. In a call, a member can turn the microphone and camera on or off, share the screen, and leave. Each person in the call is shown with their name; virtual people are marked as virtual.
4. The owner can end the call for everyone. This closes the room.
5. If another application holds the camera, the member is told to release it.

### Agent

1. A virtual person writes replies to the people in a room. Its tools act as the person who asked: face, and allow-listed web and MCP tools (market and jobs tools are paused). At most 120 replies per hour per caller.
2. Groups are the roles `user`, `moderator` and `admin`. Each virtual person has its own persona.
3. Replies are text only.

---

## Market

The tabs, in order: CRUD products (the seller's products), Create order (buy), Update order (what is about to be bought), Pay order (the orders waiting for payment), My orders (the buyer's orders).

### CRUD products

1. Sellers see their products and sales.

### Create order

1. A product has a name (at most 120 characters), a description (at most 4000), a price in cents (USD), stock, a category and a picture.
2. One review after delivery: a rating from 1 to 5, at most 1000 characters.

### Update order

1. A cart is an open order. Each buyer has at most one open cart.
2. A cart holds at most 50 products, with at most 99 of each.

### Pay order

1. An order is placed from the cart. A repeated submit does not create a second order. A buyer has at most 5 pending orders. A pending order expires after 15 minutes and its stock returns. Payment is a stub with a fake reference.
2. The order discount: one percent, `ORDER_DISCOUNT_PERCENT` (0 to 90, 0 = none), read from the environment at start-up, comes off the whole order. The total is the subtotal minus the discount, fixed when the order is placed. Only the buyer sees the discount; a seller sees their own lines at full price.

### My orders

1. An order goes from paid, to shipped, to delivered. It can be cancelled while it is pending or paid. The buyer cancels and confirms delivery; the seller ships.
2. Within 14 days of delivery, the buyer can ask for a return. The seller accepts (refund, stock back) or refuses.

---

## Jobs

The tabs, in order: CRUD descriptions (the employer's job descriptions), Create application (find jobs and apply), Update application (change an application before it is reviewed), Approve application (the employer moves applicants along the steps), My applications (read and withdraw). The page opens on Create application.

### CRUD descriptions

1. A posting has a title, company, type, place, salary range, required and preferred skills (from the shared skill list), languages and description. A person can have at most 50 open postings.
2. The owner can edit, close, reopen and delete a posting. Deleting a posting deletes its applications.

### Create application

1. Search ranks by title (weight 4), tags (weight 2) and description (weight 1). Results can be filtered by type and place.
2. A person applies from a result with a copy of their profile.

### Update application

1. The applicant changes the cover letter and the contact email of an application while the employer has not reviewed it yet (status `submitted`). After that it cannot be changed.

### Approve application

1. The employer sees the applicants of every posting in one list and moves them along the steps: submitted, reviewing, shortlisted, interview, offer, hired (or rejected). A step the flow does not allow is refused.
2. A skill match is shown for each applicant. Notes to the applicant are private to the employer.

### My applications

1. An application moves through submitted, reviewing, shortlisted, interview, offer and hired. Steps can be skipped. An application can be rejected at any step.
2. The applicant can withdraw an application, except after it is hired.
3. A skill match is shown for each application. Comments can be made on an application.

---

## Face

### My webcam

1. Camera landmarks are read in the browser and give a symmetry score.

### Current score

1. The symmetry score of the current capture is shown.

### Save results

1. A person can save each measurement with its numbers, a note of at most 200 characters, and the time. At most 200 measurements per person. A trend is shown.

### Delete all

1. A person can delete all saved results.

---

## Werewolf

### Setup

1. The host deals roles at random or by hand. A game has 5 to 40 players. Factions are Villagers, Wolves and Ghosts (from 12 players).
2. When roles are dealt at random, some abilities are banned (all except None, Transform and Kill; each group keeps at least one). The host chooses which abilities the random deal leaves out.
3. The host can start the game, add bots, force a phase, rematch or reset.

### Rules

1. Abilities: none (day vote only), block effects, reverse effects, block ability, reverse ability, kill, kill on death, see faction, see ability, reveal on death, transform (Ghost).
2. At night, abilities act and wolves vote. By day, everyone votes one player out.
3. Villagers win when no wolf is left. Wolves win when they are at least as many as the villagers. Ghosts win when they are at least half of those alive. If several sides qualify, the larger side wins. If nobody is alive, it is a draw. If the last night ends, the side with the most alive players wins.
4. Each player sees only their own view. The result is stored with each role and fate; the winner and the public log go to the room.

### Game history

1. A person can see their latest games: result, role, team, room, number of players and nights, and the list of players.

### Leaderboard

1. The top 10 players by wins among the latest 2000 games, this month by default or all time (`GET /leaderboard?season=month|all`), shown on the Werewolf page.

---

## Roulette

### Table

1. A wheel of 37 pockets. Each player starts with 1000 chips and is refilled when empty.
2. Bets: single, split, street, corner, line, dozen, column, red/black, odd/even, low/high. At most 20 bets per spin, and at most 500 chips per bet. Usual odds.
3. The 5 hottest and 5 coldest numbers are shown.

### Game history

1. The last 50 spins are shown.

### Leaderboard

1. The top 10 players by chips, shown on the Roulette page (`GET /board`), with each player's chips.

---

## Rally

Finds the players, the court and the shuttle in a badminton match video, and shows them over the video. Rallies, hits and scores are not built yet.

### Matches

1. A person uploads a match: a name (1–100 characters) and a video (mp4, webm or mov, at most 2 GB). The video is kept on disk in `RALLY_UPLOAD_DIR`, the file name is made safe and unique.
2. Only the owner sees a match. Another person gets 404 (the match is not revealed), for the video too.
3. The video streams with HTTP Range, so the player can seek.

### Court (found by itself)

1. The court is found on each sampled frame: the green floor is the largest green region, and its outline gives four corners. A frame with no full court in view (the outline covers less than 20% of the frame) is skipped, so a close-up never places players on a wrong court.
2. The outline is the floor, not the lines: it is close to the doubles court, not exact. There is no manual court.

### Players

1. Uploading a match starts the players job by itself. "Find players" (`POST /people`) starts it again when it is not running; one job runs per match at a time. The job samples the video twice a second, finds the court on each frame, runs a person detector (YOLOv8n, ONNX, OpenCV, model in `backend/data/models`, `RALLY_MODEL_PATH`) and places each person whose feet are on the court by its side: near or far, left or right.
2. The status is `idle`, `running`, `done` or `failed`; the page polls while it runs.
3. Labels: each player gets P1 to P4 and keeps it from one sample to the next by where they stand on the court (`identity.py`: the nearest known player within 2.5 m). A new player takes a free label. The labels are not tied to a person's name; two labels can swap when players switch ends mid-rally.
4. The video shows the players at the current time: a box around each person, labelled P1 to P4 (yellow, pink, cyan, green).
5. Not done yet: rally detection, hits, score per player and shuttle speed. Hits need ground truth to check them.

### Shuttle

1. The shuttle is found without training (`shuttle.py`): every frame is compared with the one before, and a bright spot that moved is a candidate. Candidates on a player's box, at the frame edge, or larger than 30 pixels are dropped.
2. Candidates are linked into tracks that move at a steady speed (the next position is predicted from the last two). A track must be straight (at least 0.7 of the walked distance is the straight distance) to be the shuttle, and the longest such track is the shuttle at that time.
3. The video shows a red ring where the shuttle is found. It is not checked against ground truth yet: the ring was checked by eye on two frames, one of them near the net.

### Account events

1. Deleting an account deletes its matches, their stored rallies (rows left from before the rally marking was removed) and their video files.

---

## Files

### Folders

1. A tree at most 6 levels deep, with 1000 entries and names of at most 100 characters.
2. Folder search in the Explorer searches the current folder and below, up to 200 hits.
3. Trash: items are kept 30 days, at most 100 items and 200 MB; the oldest go first. A person can restore an item (to its folder, or to the top if the folder is gone, with a new name if taken) or erase it. Admin deletes in the data area have no trash.

### Files

1. 20 MB per file, 100 MB per person. Upload, download, rename and delete, several at once.
2. Replacing a file (same name, after confirmation) keeps the old file as a version: at most 5 per file, kept 90 days, 200 MB in total. A version can be restored or erased.
3. A link: random token, valid 1 to 365 days or until taken back, at most 50 files, one link per file (a new link replaces the old). The link shows the name and size and allows download without sign-in. It stops working when the file is moved, deleted or expired.

---

## Database

### Database

1. The Database app works on the tables of every module (each app's data), through `/records`. It keeps no tables and no SQL console.
2. An admin sees every row of every table. Anyone else sees only their own rows (a table with an owner) or the rows its scope allows.
3. The home page (`/`) shows the Table and Grid panes for an admin; anyone else sees their own data.
4. A column can be read-only. `roulette_spins.user_id` (the owner of a spin) is read-only for everyone, admins included.

### Table

1. Rows are edited in a spreadsheet-like table: click a cell to change it; the Columns menu shows or hides columns (`id`, `title` and `cover` included).
   - A json cell shows its content as a readable list of keys and values, and is edited in place as text. Invalid json is not saved.
2. A reference cell opens the referenced table in this tab to pick a record; the work in the origin table is kept, and its record dialog opens again.
3. A file cell opens the file chooser at once. Each file has a × to remove it; several files can be added to one cell.
4. Add rows imports a folder with `data.xlsx` at its root, and its files; rows that already exist are asked about (overwrite or skip).
5. Checkboxes select rows to delete many at once; double-click a row opens its record dialog.

### Grid

1. The same rows as cards: title, cover (the first picture), and the other columns as chips.
2. Click a chip or the title to change it in place; a file opens the chooser at once; double-click a card opens its record dialog.
3. A json field is shown the same way as in the table, and is edited in place as text.

### Record dialog

1. Full screen. Edit the fields, add files (`+`), remove a file (×), pick references, save, or delete the row.
2. Save adds the files first: a refused file stops the save and nothing changes. A failed value save after the files were added says so.

---

# 2. Database

Every table, with its columns. Taken from the models in `backend/api/*/models.py`; update it when a model changes. `id*` marks the primary key; `->` marks a foreign key.

Tables of the modules (28 tables, generated from the models):

- `users`: `id*`, `username`, `password_hash`, `created_at`, `email`, `google_sub`, `group`, `kind`, `token_version`, `audio_embedding`, `face_embedding`, `voice_login`, `webcam_login`, `biometric_2fa`, `email_verified`, `email_from_google`, `phone`, `phone_verified`, `totp_enabled`, `totp_secret`, `totp_pending_secret`, `totp_last_step`, `username_changed_at`, `name`, `address`, `headline`, `summary`, `birth_date`, `city`, `region`, `country`, `avatar_url`, `links`, `experience`, `education`, `skills`, `languages`, `certifications`, `projects`, `interests`, `persona_role`, `speaking_style`, `visibility`
- `passkeys`: `id*`, `user_id`, `credential_id`, `public_key`, `sign_count`, `user_handle`, `transports`, `name`, `backed_up`, `created_at`, `last_used_at`
- `verification_codes`: `id*`, `user_id`, `purpose`, `channel`, `target`, `token_hash`, `code_hash`, `attempts`, `expires_at`, `used_at`
- `recovery_codes`: `id*`, `user_id`, `code_hash`, `used_at`, `created_at`
- `user_sessions`: `sid*`, `user_id`, `created_at`, `last_seen_at`, `ip`, `user_agent`, `method`, `revoked_at`
- `account_events`: `id*`, `type`, `user_id`, `payload`, `created_at`, `published_at`
- `reserved_usernames`: `username*`, `user_id`, `until`
- `qr_logins`: `id*`, `poll_hash`, `verify_code`, `status`, `user_id`, `approver_sid`, `requester_sid`, `requester_ip`, `requester_user_agent`, `attempts`, `created_at`, `expires_at`, `approved_at`
- `rooms`: `id*`, `slug`, `kind`, `title`, `category`, `avatar`, `user_id`, `visibility`, `join_policy`, `capacity`, `state`
- `room_members`: `room_id*`, `user_id*`, `status`, `status_reason`, `last_read_message_id`, `notify`, `hidden_at`
- `messages`: `id*`, `room_id`, `user_id`, `content`, `reply_to_id`, `pinned_at`, `deleted_at`, `edited_at`, `created_at`
- `meetings`: `id*`, `room_id`, `room_name`, `started_by`, `started_at`, `ended_at`
- `edges`: `src_id*`, `dst_id*`, `kind*`, `status`, `released_at`
- `reports`: `id*`, `reporter_id`, `target_type`, `target_id`, `reason`, `details`, `status`, `created_at`
- `notifications`: `id*`, `user_id`, `actor_id`, `kind`, `payload`, `read_at`, `created_at`
- `measurements`: `id*`, `user_id`, `created_at`, `symmetry`, `eye`, `nose`, `mouth`, `ear`, `angle`, `note`
- `job_descriptions`: `id*`, `owner_id`, `title`, `company`, `department`, `location`, `remote`, `company_about`, `domain`, `work_mode`, `timezone`, `working_hours`, `employment_type`, `contract_until`, `seniority`, `openings`, `people_managed`, `nationality_required`, `experience_min_years`, `education_min`, `skills_required`, `skills_preferred`, `skill_keys`, `tags`, `languages`, `responsibilities`, `requirements`, `nice_to_have`, `hiring_process`, `application_requirements`, `benefits`, `salary_min`, `salary_max`, `currency`, `salary_period`, `description`, `status`, `expires_at`, `created_at`
- `job_applications`: `id*`, `job_description_id`, `user_id`, `status`, `cover_letter`, `resume`, `contact_email`, `employer_note`, `history`
- `market_products`: `id*`, `seller_id`, `name`, `description`, `price_cents`, `stock`, `image_url`, `category`, `is_active`, `created_at`
- `cart_items`: `id*`, `user_id`, `product_id`, `quantity`
- `market_orders`: `id*`, `buyer_id`, `status`, `total_cents`, `payment_reference`, `created_at`, `items`, `seller_ids`, `idempotency_key`, `pay_key`, `discount_cents`, `delivered_at`
- `brands`: `id*`, `name`, `logo`
- `showcases`: `id*`, `seller_id`, `title`, `brand_id`, `cover`, `audio`, `video`
- `roulette_wallets`: `user_id*`, `chips`
- `roulette_spins`: `id*`, `user_id`, `number`, `bets`, `stake`, `payout`, `balance_after`, `created_at`
- `rally_matches`: `id*`, `user_id`, `name`, `video_name`, `video_path`, `created_at`
- `rally_rallies`: `id*`, `match_id` (deleted with the match), `number`, `start_ms`, `end_ms`, `hits`, `winner`
- `games`: `id*`, `room_code`, `status`, `state`, `winner`, `days`, `size`, `finished_at`, `players`, `player_ids`
- `comments`: `id*`, `object_type`, `object_id`, `user_id`, `content`, `rating`, `once`, `created_at`, `edited_at`
- `skills`: `key*`, `name`
- `users` (directory, read-only view of the same table): `id*`, `username`, `kind`, `name`, `headline`, `summary`, `region`, `city`, `avatar_url`, `birth_date`, `interests`, `persona_role`, `speaking_style`, `skills`, `visibility`

Rules for the tables:

- **One database** for every module. Tables of a module start with its name when the name would be unclear alone (`market_*`, `job_*`); existing tables keep their names, and new tables follow the same rule.
- **Foreign keys** are declared in the models and added to tables made before them at start-up (`ensure_foreign_key` in `sn_shared/db.py`, PostgreSQL only). Deleting a row that others refer to is refused unless the code deletes those rows first.
- **Migrations:** start-up steps that are safe to repeat (`ensure_columns`, `ensure_foreign_key`, `rename_table`). Alembic is not used: the schema is small and changes are additive.
- **Planned, not done:** biometric embeddings to their own table (`users` keeps none), and skills to a link table so they can be searched. Until then they stay in `users` (as bytes and as JSON).

The `file` module keeps no tables: its files are stored on disk. The Database app keeps no tables: it works on the other modules' tables through `/records`. `users` appears twice: the `center` model owns it; the shared directory maps the same table for the names other modules read.

# 3. Backend

One FastAPI process (`backend/api/main.py`) mounts one router per module. Shared libraries live in `shared/backend/sn_shared`.

## 3.1 Shared functions (`shared/backend/sn_shared`)

One library for every backend. Each function is written once here; no app copies it.

- **Who may call what**: `deps` (`require_groups`, `access_dependencies`, `get_current_user`, the group checks on every route), `access` (the rule an app applies to what a person owns), `origin` (the allow-list of origins for the unsafe routes), `servicesig` (a signature for a call from one service to another, for a person who has no token to give).
- **Tokens and keys**: `jwtkeys` (the Ed25519 keys of `sn_token`; only `center` holds the private key), `security` (password hashing, JWT helpers), `tokens` (hashes of one-time tokens; only the hash is stored), `revocation` (immediate revocation of access tokens through an optional Redis).
- **People**: `directory` (the people of the platform, read from `users`), `columns` (the columns every table writes the same way), `userlock` (one operation at a time for each user).
- **Data and admin**: `db` (engine and session dependency), `admincrud` (`records_router`: the admin CRUD of any table, and its owner-scoped twin), `recordfiles` (files kept with the rows of a table), `media` (the route that replaces the file behind a row), `states` (the steps a thing goes through and which step may follow which).
- **Vocabularies**: `skills`, `tags` (the words a thing is found by), `facets` (the counts behind a filter tree), `textsearch`, `comments` (what people say about a thing and the stars they give it).
- **Events and messaging**: `events` (consumes account events from a Redis Stream), `consumer` (starts and stops that consumer the same way for every app), `messaging` (queues for a module that needs a broker; optional).
- **Limits and time**: `limits` (the sliding-window limit: at most N events in W seconds, in memory per process), `clock` (the one clock: UTC).
- **Testing**: `testing` (one Ed25519 keypair per process for tests).

## 3.2 APIs of each app

The routes of each module, as the running app serves them (the full path, including the router prefix). Each module also serves the admin CRUD under `/records` (see 3.1, `admincrud`) and the documentation pages, which are not listed here. Internal routes between services are not listed.

## center (69)

- `DELETE /auth/me`
- `DELETE /auth/me/email`
- `DELETE /auth/me/google`
- `DELETE /auth/me/passkeys/{passkey_id}`
- `DELETE /auth/me/phone`
- `DELETE /auth/me/voice`
- `DELETE /auth/me/webcam`
- `DELETE /auth/sessions/{sid}`
- `DELETE /auth/totp`
- `GET /auth/config`
- `GET /auth/cv/{username}`
- `GET /auth/liveness/challenge`
- `GET /auth/me`
- `GET /auth/me/passkeys`
- `GET /auth/me/profile`
- `GET /auth/qr/{request_id}`
- `GET /auth/reauth/methods`
- `GET /auth/sessions`
- `GET /health`
- `PATCH /auth/me/passkeys/{passkey_id}`
- `POST /auth/email/login/magic`
- `POST /auth/email/login/request`
- `POST /auth/email/login/verify`
- `POST /auth/email/verify`
- `POST /auth/google`
- `POST /auth/liveness/challenge`
- `POST /auth/login`
- `POST /auth/login/biometric`
- `POST /auth/login/totp`
- `POST /auth/login/voice`
- `POST /auth/login/webcam`
- `POST /auth/logout`
- `POST /auth/me/email`
- `POST /auth/me/google`
- `POST /auth/me/passkeys`
- `POST /auth/me/passkeys/options`
- `POST /auth/me/password`
- `POST /auth/me/phone`
- `POST /auth/me/phone/verify`
- `POST /auth/me/username`
- `POST /auth/me/voice`
- `POST /auth/me/webcam`
- `POST /auth/passkey/login`
- `POST /auth/passkey/options`
- `POST /auth/password/forgot`
- `POST /auth/password/reset`
- `POST /auth/phone/login/request`
- `POST /auth/phone/login/verify`
- `POST /auth/qr/poll`
- `POST /auth/qr/start`
- `POST /auth/qr/{request_id}/approve`
- `POST /auth/qr/{request_id}/deny`
- `POST /auth/reauth/email/request`
- `POST /auth/reauth/email/verify`
- `POST /auth/reauth/google`
- `POST /auth/reauth/passkey/options`
- `POST /auth/reauth/passkey/verify`
- `POST /auth/refresh`
- `POST /auth/register`
- `POST /auth/register/combined`
- `POST /auth/register/passkey/options`
- `POST /auth/register/voice`
- `POST /auth/register/webcam`
- `POST /auth/sessions/revoke-others`
- `POST /auth/totp/enable`
- `POST /auth/totp/recovery-codes`
- `POST /auth/totp/setup`
- `PUT /auth/me/biometric-2fa`
- `PUT /auth/me/profile`

## chat (47)

- `DELETE /blocks/{user_id}`
- `DELETE /friends/{user_id}`
- `DELETE /reports/{report_id}`
- `DELETE /rooms/{slug}`
- `DELETE /rooms/{slug}/members/{user_id}`
- `DELETE /rooms/{slug}/messages/{message_id}`
- `DELETE /rooms/{slug}/messages/{message_id}/pin`
- `GET /health`
- `GET /inbox/summary`
- `GET /people/{username}`
- `GET /reports`
- `GET /reports/mine`
- `GET /rooms`
- `GET /rooms/{slug}`
- `GET /rooms/{slug}/meeting`
- `GET /rooms/{slug}/members`
- `GET /rooms/{slug}/members/{user_id}`
- `GET /rooms/{slug}/messages`
- `PATCH /reports/{report_id}`
- `PATCH /rooms/{slug}`
- `PATCH /rooms/{slug}/members/{user_id}`
- `PATCH /rooms/{slug}/messages/{message_id}`
- `POST /blocks/{user_id}`
- `POST /dm`
- `POST /friends/{user_id}`
- `POST /friends/{user_id}/accept`
- `POST /friends/{user_id}/decline`
- `POST /reports`
- `POST /rooms`
- `POST /rooms/{slug}/accept`
- `POST /rooms/{slug}/cards/{message_id}/act`
- `POST /rooms/{slug}/cards/{message_id}/submit`
- `POST /rooms/{slug}/cards/{message_id}/{action}`
- `POST /rooms/{slug}/decline`
- `POST /rooms/{slug}/game`
- `POST /rooms/{slug}/hide`
- `POST /rooms/{slug}/join`
- `POST /rooms/{slug}/leave`
- `POST /rooms/{slug}/meeting/end`
- `POST /rooms/{slug}/meeting/start`
- `POST /rooms/{slug}/members`
- `POST /rooms/{slug}/messages`
- `POST /rooms/{slug}/read`
- `POST /rooms/{slug}/transfer`
- `POST /rooms/{slug}/virtual`
- `POST /rooms/{slug}/voice-message`
- `PUT /rooms/{slug}/messages/{message_id}/pin`

## werewolf (19)

- `GET /health`
- `GET /leaderboard`
- `GET /me/history`
- `GET /rooms`
- `GET /rooms/{code}`
- `GET /rooms/{code}/perspective/{seat}`
- `GET /setup/meta`
- `POST /rooms`
- `POST /rooms/{code}/action`
- `POST /rooms/{code}/bots`
- `POST /rooms/{code}/chat`
- `POST /rooms/{code}/force`
- `POST /rooms/{code}/join`
- `POST /rooms/{code}/leave`
- `POST /rooms/{code}/options`
- `POST /rooms/{code}/rematch`
- `POST /rooms/{code}/reset`
- `POST /rooms/{code}/roles`
- `POST /rooms/{code}/start`

## file (21)

- `DELETE /entries`
- `DELETE /share/{token}`
- `DELETE /trash`
- `DELETE /versions`
- `GET /download`
- `GET /entries`
- `GET /health`
- `GET /search-folder`
- `GET /shared/{token}`
- `GET /shared/{token}/download`
- `GET /shares`
- `GET /trash`
- `GET /versions`
- `POST /copy`
- `POST /folder`
- `POST /move`
- `POST /rename`
- `POST /share`
- `POST /trash/restore`
- `POST /upload`
- `POST /versions/restore`

## face (6)

- `DELETE /measurements`
- `DELETE /measurements/{measurement_id}`
- `GET /health`
- `GET /measurements`
- `PATCH /measurements/{measurement_id}`
- `POST /measurements`

## roulette (9)

- `DELETE /spins`
- `DELETE /spins/{spin_id}`
- `GET /board`
- `GET /health`
- `GET /spins`
- `GET /stats`
- `GET /wallet`
- `POST /spin`
- `POST /wallet/refill`

## rally (7)

Paths below are the module's own; the gateway sends `/api/rally/...` here as `/...`.

- `GET /health`
- `GET /matches`
- `GET /matches/{match_id}`
- `GET /matches/{match_id}/people`
- `GET /matches/{match_id}/video`
- `POST /matches`
- `POST /matches/{match_id}/people`

## market (23)

- `DELETE /cart`
- `DELETE /cart/items/{product_id}`
- `DELETE /orders/{order_id}`
- `DELETE /products/{product_id}`
- `DELETE /reviews/{comment_id}`
- `GET /cart`
- `GET /categories`
- `GET /health`
- `GET /me/products`
- `GET /orders`
- `GET /orders/{order_id}`
- `GET /products`
- `GET /products/{object_id}/reviews`
- `GET /products/{product_id}`
- `GET /sales`
- `PATCH /orders/{order_id}/status`
- `PATCH /reviews/{comment_id}`
- `POST /orders`
- `POST /orders/{order_id}/pay`
- `POST /products`
- `POST /products/{object_id}/reviews`
- `PUT /cart/items/{product_id}`
- `PUT /products/{product_id}`

## job (19)

- `DELETE /applications/{application_id}`
- `DELETE /comments/{comment_id}`
- `DELETE /jobs/{job_id}`
- `GET /facets`
- `GET /health`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/applications`
- `GET /jobs/{object_id}/comments`
- `GET /me/applications`
- `GET /me/jobs`
- `GET /skills`
- `PATCH /applications/{application_id}`
- `PATCH /applications/{application_id}/mine`
- `PATCH /comments/{comment_id}`
- `PATCH /jobs/{job_id}`
- `POST /jobs`
- `POST /jobs/{job_id}/apply`
- `POST /jobs/{object_id}/comments`

Total listed: 220 routes.

# 4. Backend test (unit test)

Command: `cd backend && python -m pytest -q` (Python 3.13, PYTHONPATH covers `shared/backend` and `backend`).

Result (full run, about 11 minutes, 2026-11-24): 2396 passed, 6 failed, 3 skipped (2405 tests). The 6 failing tests: `tests/center/test_email_hardening.py`, `tests/center/test_username_case.py`, `tests/center/test_username_chars.py`, `tests/center/test_virtual_seed.py`, and two in `tests/job/test_data.py` (`test_tables_and_ops`, `test_applicant_create_withdraw_and_forbidden`). The job tests check older permission strings and an old 405 response of the generic records route; they are stale. The center tests depend on state left by other tests. None is fixed yet. The CV tests (`tests/center/test_cv.py`, 4 tests) were added after this run and pass when run alone.

# 5. Frontend

One Next.js app (`frontend/`), one folder per app under `frontend/app/<app>`. Shared UI lives in `shared/frontend`, split in four tiers:

| Tier | Folder | Rule |
|---|---|---|
| Elements | `shared/frontend/elements` | use no other kit component |
| Compounds | `shared/frontend/compounds` | built from elements only (never from another compound) |
| Complex | `shared/frontend/complex` | built from compounds (the site bar and its tools) |
| Apps | `frontend/app/<app>` | built from all three tiers; each app has its own `layout.tsx` |

Shared helpers that are not components (`crudModel`, `galleryModel`, `justifiedRows`, `useRecordList`, `appsMenuExtras`) sit next to the compounds that use them. Locale hooks, the API client and the theme live in `shared/frontend/lib`, `locales`, `api.ts`. `shared/frontend/ui.ts` is the entry point that re-exports the kit.

## 5.1 Shared components

The kit in `shared/frontend`, in four tiers (see the table above): elements, compounds, complex, and the shared helpers beside them.

### 5.1.1 Elements

Plain building blocks, no dependency on other kit components.

- `Button`: the button of every app. Variants `primary`, `secondary`, `danger`, `ghost`; sizes `sm`, `md`, `lg`; effects; `loading`; `status`.
- `TextBox`: one-line input, or textarea with `multiline`.
- `Select`: native select styled like the fields.
- `CheckBox`: checkbox with a label, supports the indeterminate state.
- `Alert`: message announced to screen readers (`role="alert"` for errors, `role="status"` otherwise).
- `Card`: bordered panel on the surface colour.
- `Icon`: named SVG icons (`ICON_NAMES`).
- `JsonView`: a json value shown in plain sight, as its keys and values (read only, scrolls inside a cell).

### 5.1.2 Compounds

Built from elements. A compound never imports another compound.

Navigation and frame:

- `CrudToolbar` (`shared/frontend/complex/CrudToolbar.tsx`): the bar over a table: search, the create button, the extra controls, and the bulk actions for the picked rows. (It is complex, not a compound: it uses `SearchBox`.)
- `DataTable`: the table of rows with a box on each row, the select-all line and an actions column; it takes its words from the shared crud translations.
- `TreeView`: navigation tree; top level in a row, children in a drop-down.
- `SplitPanel`: resizable panes, remembered per `storageKey`; also `FacetGridView`, `ExtraPane`, and `TabPanel` (tabs that are links to `#key`; panels stay mounted unless `keepMounted={false}`).
- `AuthGate`: loading, error and signed-out states; children only for a signed-in user.
- `ConfirmModal`: yes/no dialog for destructive actions; also `ConfirmHost`, `confirmDialog(message)`.
- `Dialog`, `FileCellDialog`, `pickFiles` (`Dialogs.tsx`): the shared modal frame, a file cell's dialog, and the file chooser.
- `ContextMenu`: right-click menu from `items` at `x`, `y`; closes on outside press or Escape.
- (The unread count is part of `SiteBar`, in `shared/frontend/complex/SiteBar.tsx`.)

Records and tables:

- `CrudView`: one module's table, one row per record; technical columns hidden until chosen; inline edit; row actions.
- `ColumnsMenu` and `Pager` (`TableFooter.tsx`): the Columns menu and the previous and next pager. (The table itself is `DataTable`.)
- `crudTable.css` (shared, imported by the root layout): the look of every `DataTable`, including the sticky actions column.
- `CrudRowForm`: add or edit a row, with server suggestions (`SuggestField`).
- `SchemaForm`: form generated from a field description sent by the server.
- `CellView`: formats one cell and hides technical columns; `JsonCell` for JSON.
- `GalleryView`: a table as cards with search, filter chips (`groups`), paging, add/edit/delete; also `GridView` (`justified` rows possible).
- `FacetView`: filter values with counts, as a tree.

Inputs:

- `LabelTextBox`: labelled text input or textarea; also `NumberBox`.
- `JsonEditor` (`JsonEditor.tsx`): a json value in a monospace box, with a message when it is not valid json; read-only mode shows it formatted.
- `InputBox`: search chips (`SearchBox`, `TermChips`), `PageSizeSelect`, and `TagBox`. (`SelectBar` was removed: `SelectAllBar` and a delete button do its job.)

Files and media:

- `FileTools`: `FileDropZone` (`accept` rules), `UploadDialog`, `MediaField` (replace a row's file), `MediaView`.
- `RecordFiles`: `CellFiles` (a cell's files). The card picture of the grid is local to `GridEditor.tsx`.

Settings and social:

- `LanguageSwitcher` (`SiteSettings.tsx`): a `Select` of `locales`, labelled by `names`. On change: set `<html lang>` and `<html dir>` (`rtl` for ar, he, fa, ur), call `setLocale`, then `onChange`. `SiteBar` keeps `<html lang>` in step.
- `ThemePicker` (`SiteSettings.tsx`): main colour, accent count and swatches in a "Theme" panel; saved in the browser and synced across tabs. Modes: floating (default), `inline`, `expanded`.
  - **Colour roles** (set by `buildTheme`, `shared/frontend/lib/theme.ts`):
    - `solid-color` (background, fill): the main colour and accents `--solid-0…`.
    - `line-color` (`--line`): black or white, whichever contrasts more with the solid colour.
    - `border-color`: `LINE_SOFT` (`--line` at 30%). Every border and divider uses it; a border of a selected or pressed state uses `--line` solid.
    - Components use only these roles. Semantic exceptions: none of the colour meaning is kept by a colour: an error is `--line` bold with its text, a danger action is `--line` underlined, a folder icon is yellow (a file-type icon), and the Roulette and Werewolf games keep their own colours.
    - No `box-shadow` anywhere in the source. A pressed tab is marked by a 3px bottom border, not a shadow.
    - A disabled control is faded (opacity 0.4), not dashed.
- `Comments` (`Comments.tsx`): comments and star ratings.
- `TableFooter` (`shared/frontend/compounds/TableFooter.tsx`): the footer row of every table: `SelectAllBar` (with a `label`), `PageBar` (rows per page, then the pager pushed to the right), and `CONTROL` (the one height of every control of a bar, 36px). The Database table and grid, and the chat's Rooms, Messages and Members use it; all of them are one line, with no wrapping.

### 5.1.3 Complex

Built from compounds. These are the pieces every app page shares.

- `SiteBar` (`shared/frontend/complex/SiteBar.tsx`, props `name`, `href`): the top bar of every page, in one component. It holds the app picker (a `Select` of the apps; picking one opens it), the unread count, the greeting (signed-in users only, plain text), `LanguageSwitcher` and `ThemePicker` (inline, expanded). It sets `<html lang>` from the shared locale and the page title from `href`. `href` marks the open app.
  - Tests: `frontend/tests/center/SiteBar.test.tsx` (language, theme, greeting). The app picker has no test yet.
- Tables of an app are chosen in the app's own pane, not in the picker. The picker has no test yet.

### 5.1.4 Shared between apps (kept in an app folder)

Some components are used by more than one app but live in the folder of the app that made them. They are part of the shared kit in practice; this list says where they are.

- **Frame and docks** (`chat`): `AppFrame`, `PageDock`, `ChatDock`, `libraries` (the library of each app), `appMains` (the main page of each app in the User pane of the home page).
- **Tables**: `TableControls`. (`DataTable` is in the shared compounds; `CrudToolbar` is in the shared complex tier, since it uses a compound.)
- **Rooms and members** (`chat`): `RoomView`, `RoomsPanel`, `AddVirtual` (used by Werewolf).
- **Helpers**: `useSize`, `errorMessage` and the room types (`protocol`) (`chat`); `prepareGame` (`werewolf`, used by chat).
- **Face** (`face`): `useFaceTracker`, `mediapipe`, `geometry` and `types`, used by the face page and its analysis page.
- **Account** (`center`): `useReauth`, used by the account pages.

## 5.2 Layout of an app

### Frame

Every app page is drawn by `AppFrame` (`frontend/app/chat/dock/AppFrame.tsx`), from the top down:

1. `SiteBar` (complex): the top bar, always the same height.
2. `PageDock`: the page on the left, the chat dock on the right (Rooms, Messages, Members). The addresses in its `except` list show the page alone.
3. The page itself, in `<main>`.

The root element carries the class `app-<name>`, which scopes that app's CSS. The page takes the whole space under the bar: its width is the width of the window, and its height is the height left under the bar.

### Size rules

- A box that is the main content of a page (a card, a camera box, the game box) stretches to the full width and to the full height of the page. It has no outer border or background when it is the only thing on the page (Werewolf, Face).
- A table or a list grows with the page and scrolls inside it; the page itself does not scroll in the middle of a table.
- Controls keep their own size (the same height for every control of a bar, 36px); only the boxes around them stretch.

### Where things sit, per page

- **Face**: the camera on the left, filling the height. On the right, from the top: the buttons (camera on or off, draw), the status line (camera off, starting, error), the score panel, Save result, and the history.
- **Werewolf**: the wolf and the title at the top of the box, then the game of the open room (lobby, roles, start) inside the same box. Without an open room, the steps to start are shown in the box.
- **Chat (page)**: the call of the open room fills the page: the checks for camera and microphone, the Join button, the call tiles. The header row shows the room's name, the slots and the number online (`SplitPanel` `header`). The messages toolbar holds Link, then Columns (Columns always last).
- **Chat (dock)**: the rooms, messages and members as tabs; the tab row is the header of the dock.
- **Database and tables**: the table fills the page; the footer (select all, rows per page, pager) sits at its bottom.

### How the app panes are chosen

- The User pane of the home page shows the main page of an app from the registry `frontend/app/chat/dock/appMains.tsx`: Roulette, Face, Werewolf, Chat and Users (`center`). Each entry sets the app's CSS class.
- When an app has a table API, the panes beside its page (library and extra panes) come from `appPanes` in `ChatDock.tsx`, shown in a `SplitPanel`.
- The Database home (`/`) uses the same class and bar, with `DatabaseDock` inside.

### Addresses

`/` is the Database home (rewritten internally to `/database`). The sign-in, account and profile pages are under `/user`; the old `/login`, `/account` and `/profile` addresses lead there. A signed-in person opens an app from the User pane of `/`; the old app addresses (`/chat`, `/face`, `/werewolf`, `/roulette`, `/job`, `/market`, `/file`, `/admin`) redirect to `/`. `/center` opens the Users pane as `/?app=center`.

## 5.3 Each app

The layout of each app's page, and the components that fill each part of it. Components are named as they are in `frontend/app/<app>`.

- **Face** (`FaceLibrary` → `FaceApp`)
  - Left: the camera (video and canvas that draws the face points).
  - Right, from the top: the buttons (`CheckBox` for drawing, camera on or off), the status line, `ScorePanel`, the save section, `History`.

- **Werewolf** (`WerewolfHome` → `ChatDock` → `GameOfRoom`)
  - One box: the wolf and the title, then three tabs, in order: Game (the open room's content), History (`HistoryView`, the person's finished games), Leaderboard (`Leaderboard`, the wins this month or all time, from `GET /leaderboard?season=`).
  - Before the game: `LobbyView` (`SetupMeta`, `SeatRow`, `RulesContent`, `CheckBox`).
  - In the game: `GameView` (`PhaseBanner`, `PlayerGrid` of `PlayerTile` with `Avatar`, `ActionPanel`, `PerspectivePanel`, `EventBanner`, `Countdown`).
  - At the end: `ResultView` and `RecapCard`.
  - `Toast` shows messages at the top.

- **Roulette** (`RouletteGame`)
  - The title, then three tabs, in order: Table (the ball, the chips, `BetTable`, the strip of recent, hot and cold numbers `NumberStrip`, and the spin buttons), History (the spins, with rebet and delete), Leaderboard (the top chips).
  - Components: `BetTable` (bets), `SpinResult`, `Record` (history).

- **File** (`FileLibrary` → `Explorer`)
  - Left: the folder tree (`TreeView`). Middle: the list and the grid (`GridView`), with `ContextMenu`.
  - Dialogs: `VersionsSection`, `TrashPanel`, `ShareSection`, `Dialog`.

- **Job** (`JobLibrary`)
  - A `TabPanel` with the tabs, in order: `MyPostings` (CRUD descriptions), `JobSearch` (Create application), `PendingApplications` (Update application), `ApproveList` (Approve application), `ApplicationsList` (My applications).

- **Market** (`MarketLibrary`)
  - A `TabPanel` with the tabs, in order: CRUD products (`GalleryView`), `Shop` (Create order), `CartView` (Update order), `PayList` (Pay order), `OrderList` (My orders).

- **Database** (`DatabaseDock`)
  - Table choice (`TableChooser`, `MenuTables`), the grid (`GridEditor`) or the table (`TableEditor`), the record dialogs (`RecordDialog`, `FieldDialog`), and the reference picker (`RefPickHost`).

- **Chat** (`ChatDock` → `SplitPanel`; the page is `RoomCall`)
  - Dock: `RoomsPanel`, `RoomView`, `MemberPanel`, `PastRoom`, `JoinPrompt`, `DmRequest`, `RoomForm` (make a room), `AvatarImage`.
  - Page: `RoomCall` (`Meeting`, `CallRoom`). Editing a room opens the shared `RowDialog` from `RoomsPanel`.

- **Users** (`LoginFlow` → `AuthPanel`)
  - `AuthPanel` with a `TabPanel` of sign-in methods (`AuthTabContent`), and `ModeSwitch`, `AccountMode`, `UsernameField`, `ProfileFields`, and the shared `Alert`.
  - `MfaStep` is the step after the method is chosen.

# 6. Frontend test (UI test)

Command: `cd frontend && npx vitest run` and `npx tsc --noEmit`.

Result (full run in parallel, 2026-11-24, after the latest changes): 86 test files, 1273 tests: 1164 pass, 109 fail. Most of the failures are timing problems under the parallel run: the files in `tests/center` (Liveness, AccountChanges, Email, AccountFlows, Phone, Passkey, LoginFlow, ChangeUsername, AuthPanel) and `tests/chat/chat/chat.test.tsx` pass when run alone or in smaller groups. The real remaining failures are the 2 tests in `tests/center/Liveness.test.tsx` that look for the "Đang quay" button (sign-in with the webcam); they are not fixed yet. Running the suite with fewer workers is the first thing to try.

Typecheck: `tsc --noEmit` passes.

# 7. Local setup and deploy

```bash
cp .env.example .env     # set JWT_SECRET, POSTGRES_PASSWORD, REDIS_PASSWORD, DB_PASSWORD_APP, RABBITMQ_PASSWORD, CALLEAR_SECRET, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
docker compose --env-file .env -f shared/infra/docker-compose.yml up --build      # http://localhost:8080
```
Outside Docker: `python -m venv .venv`, `pip install -r backend/requirements-dev.txt -e shared/backend`, `cd frontend && npm install && npm run dev`. Camera/mic need HTTPS (localhost excepted).

| Variable | Sets |
|---|---|
| `APP_ENV` `PUBLIC_ORIGIN` `GATEWAY_PORT` `COOKIE_SECURE` `ALLOWED_ORIGINS` | mode (`production` needs keys), site address/port, secure cookies, chat socket origins |
| `JWT_SECRET` `JWT_KEY_ID` `ACCESS_TOKEN_MINUTES` (60) `REFRESH_DAYS` (14) `DATA_KEY` | sign-in secrets, lifetimes, key sealing biometrics |
| `GOOGLE_CLIENT_ID` `WEBAUTHN_RP_ID` `WEBAUTHN_RP_NAME` `WITH_BIOMETRICS` `BIOMETRICS_ENABLED` | Google, passkeys, voice/face (`WITH_BIOMETRICS` adds slow models to the build) |
| `SMTP_*` `SMS_*` `TWILIO_*` `LIVEKIT_*` | mail (`mail-dev` profile = Mailpit), SMS, video calls (key, secret, address of LiveKit) |
| `AI_PROVIDER` (`dummy`/`gemini`) `GEMINI_*` `AI_*_LIMIT` | AI for companions in chat |
| `WEREWOLF_SECRET` `WEREWOLF_SNAPSHOT_KEY` `RABBITMQ_*` | signed module calls, saved-game key, queue |
| `ORDER_TTL_MINUTES` | tunable limits |
| `ORDER_DISCOUNT_PERCENT` | the percent off every market order, 0 to 90 (0 = none) |

Only the eight secrets above are needed to start (compose refuses to start without them).

**Access-token keys:** only `center` signs `sn_token` (JWT `EdDSA`); others verify with public keys (files). Dev: `center` makes a throwaway pair. Real pair:
```bash
docker exec -w /srv socialnetwork-api-backend-1 python -m api.center.cli gen-jwt-key    # prints private PEM, public PEM, kid

# save git-ignored as shared/infra/secrets/jwt_private.pem and shared/infra/secrets/jwt_public_keys.pem

```
Rotate without logout: add new public key beside old, recreate backends, switch private key, recreate `api-backend`, drop old public key after one token lifetime. Production: `center` needs the private key, others the public keys.

Work in slices, one app at a time (table → page).

- Pages: `bash scripts/deploy.sh web-frontend`; backend: `bash scripts/deploy.sh api-backend` (slow with `WITH_BIOMETRICS=1`; use `0` meanwhile); infra: `python shared/infra/generate_infra.py` then `bash scripts/deploy.sh`
- `deploy.sh`: builds, starts without rebuilding, restarts gateway; ends `gateway answers 200`
- Demo data: `python -m tools.seed_demo --embedder dummy` in the backend container

| Layer | Catches | How |
|---|---|---|
| Data | seeder left a field out, bad dates, table that cannot list | `bash scripts/smoke.sh` lists every table as admin and person (`backend/tools/smoke.py`), fails on server error |
| Pages | route errors, old address not redirecting | `scripts/smoke.sh` asks every page and old address |
| Requirements | feature missing | section 1 is the checklist |
| Eye | stretched button, color ignoring theme, gap | open in browser, dark + light, narrow + wide |

Before "done": (1) backend + frontend tests pass and `scripts/smoke.sh` ends `ALL GOOD` (`--quick` skips types/tests); (2) new table/seeder lists as admin and person and its page shows rows; (3) changed page looked at in User pane and own page, theme changed; (4) changed address redirects.

# 8. Building from nothing

1. First pass: leave out voice/face sign-in, SMS, video calls, Google, passkeys, RabbitMQ, Kafka; `AI_PROVIDER=dummy`
2. Conventions first: integer ids; person = `user_id`; money = cents; lists = JSON columns; deleted account = user `0`; list routes take a limit (market and most apps: default 20, max 50; chat rooms and members: default 50, max 100; chat history up to 200); errors `{"detail": "..."}`; roles `user` / `moderator` / `admin`; cookie `sn_token`
3. Order: `sn_shared` + shared kit (theme, `CrudView`, `GalleryView`, `SplitPanel`, `SiteBar`, `PageDock`) → `center` → Database home → simple apps (Face, File, Roulette) → flows (Market, Jobs) → Chat, Werewolf → demo data; each app = tables in `admin.py`, routes, Library, pages
4. Gate per step: backend test, frontend test, `scripts/smoke.sh`
5. Write any choice not covered here (exact columns, route payloads, look beyond the measures) into this file before building