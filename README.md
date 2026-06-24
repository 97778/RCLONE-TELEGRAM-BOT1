# rclone Telegram Bot

Telegram bot that organizes media files across rclone remotes into capped folders,
with a **live status board that refreshes every 8 seconds**.

The owner uploads an `rclone.conf` via chat, lists remotes, and runs the organizer
per-remote or on all remotes. Runs as a Docker image with an HTTP health check for Koyeb.

## Features
- Upload `rclone.conf` directly through Telegram (owner only)
- Lists and handles all configured remotes
- Organizes video/audio files into `<LIMIT>gbN` folders
- Live status board (files moved, progress bar, data moved, current file, folder, elapsed) refreshing every 8s
- Real cancellation that stops the in-flight rclone transfer (`/cancel`)
- Owner / allowed-user permission levels
- HTTP health check at `/health` for Koyeb

## Access control

Two permission levels, configured via environment variables:

| Role | Env var | Can do |
|---|---|---|
| **Owner** | `OWNER_ID` | Everything: upload `rclone.conf`, list remotes, run/cancel jobs, `/users` |
| **Allowed user** | `ALLOWED_USERS` | Run (`/organize`) and cancel (`/cancel`) jobs only |

- The owner is **always** allowed to run jobs (no need to also list them in `ALLOWED_USERS`).
- Allowed users **cannot** upload the config or view remotes.
- If neither `OWNER_ID` nor `ALLOWED_USERS` is set, **everyone is denied**.
- Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot).

## Run locally (Docker)
1. `cp .env.example .env` and fill in `BOT_TOKEN` + `OWNER_ID`.
2. `docker compose up --build`
3. In Telegram: `/start`, send your `rclone.conf`, then `/organize`.

## Deploy on Koyeb
1. Push this repo to GitLab/GitHub.
2. Create a Koyeb **Web Service** from the repo (Dockerfile build).
3. Set environment variables (no `.env` file needed in production):
   - `BOT_TOKEN` – BotFather token (store as a **Secret**)
   - `OWNER_ID` – your Telegram user ID
   - `ALLOWED_USERS` – optional, comma-separated extra IDs (run/cancel only)
   - `LIMIT_GB` – optional (default 200)
   - `STATUS_REFRESH_SECONDS` – optional (default 8)
   - Leave `PORT` unset; Koyeb injects it automatically.
4. Health check: HTTP, path `/health`, port `8080`.
5. Add a **persistent volume** mounted at `/data` so `rclone.conf` survives restarts.

## Status board
The organizer script (`scripts/organize.sh`) emits machine-readable `PROG:` lines
(`START`, `MOVED`, `SKIP`, `FAIL`, `DONE`) that the bot parses into a `JobState`.
A background task edits the status message every `STATUS_REFRESH_SECONDS` (default 8)
so you always see current progress, including a `[####......] %` bar.

The board is sent as **plain text** so filenames containing Markdown characters
(`` ` ``, `_`, `*`, `[`) cannot break rendering.

## Commands
| Command | Role | Description |
|---|---|---|
| `/start`, `/help` | allowed | Show help |
| `/remotes` | owner | List configured remotes |
| `/organize` | allowed | Inline buttons to pick a remote (or ALL) |
| `/organize <remote:>` | allowed | Run directly on one remote |
| `/cancel` | allowed | Stop the running job (kills the transfer) |
| `/users` | owner | Show who has access |
| (send a file) | owner | Upload `rclone.conf` |

## Notes
- Bot uses long polling, so no inbound webhook needed.
- `rclone.conf` is stored at `RCLONE_CONF_PATH` (default `/data/rclone.conf`); mount a volume to persist it.
- `rclone moveto` runs with `--retries 3 --low-level-retries 10 --timeout 5m` for resilience.
- `rclone lsf` uses a TAB separator, so filenames containing `;` are handled correctly.
