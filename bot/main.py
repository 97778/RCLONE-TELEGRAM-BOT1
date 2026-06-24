import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode

from .config import Config
from .health import start_health_server
from .rclone_manager import RcloneManager
from .organizer import run_organize
from .job_state import JobState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

rclone = RcloneManager(Config.RCLONE_CONF_PATH)
_jobs: dict[int, JobState] = {}      # chat_id -> JobState
_cancel: dict[int, bool] = {}        # chat_id -> cancel flag


def _deny(checker):
    """Build a decorator that gates a handler by `checker(user_id) -> bool`."""
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if not user or not checker(user.id):
                uid = user.id if user else "unknown"
                msg = f"\u26d4 Not authorized. Your ID: {uid}"
                if update.message:
                    await update.message.reply_text(msg)
                elif update.callback_query:
                    await update.callback_query.answer("Not authorized", show_alert=True)
                return
            return await func(update, context)
        return wrapper
    return decorator


# Allowed users (owner + allow-list) can run/cancel jobs.
guard = _deny(Config.is_allowed)
# Only the owner can manage config and admin actions.
owner_only = _deny(Config.is_owner)


@guard
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Markdown is safe here: static text only.
    await update.message.reply_text(
        "\U0001f916 *rclone organizer bot*\n\n"
        "1. Send me your `rclone.conf` as a file.\n"
        "2. /remotes \u2013 list configured remotes\n"
        "3. /organize \u2013 pick a remote (live status board)\n"
        "4. /organize Dropbox33: \u2013 run directly on one remote\n"
        "5. /cancel \u2013 stop a running job\n"
        "6. /users \u2013 (owner) show who has access\n",
        parse_mode=ParseMode.MARKDOWN,
    )


@owner_only
async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    name = (doc.file_name or "").lower()
    if "rclone" not in name and not name.endswith(".conf"):
        await update.message.reply_text(
            "Please send a file named rclone.conf (or *.conf)."
        )
        return
    if doc.file_size and doc.file_size > 1_000_000:
        await update.message.reply_text("File too large to be an rclone.conf.")
        return

    tg_file = await doc.get_file()
    data = bytes(await tg_file.download_as_bytearray())
    rclone.save_conf(data)
    remotes = await rclone.list_remotes()
    # Plain text: remote names are dynamic.
    await update.message.reply_text(
        "\u2705 Saved rclone.conf.\nFound remotes:\n" +
        ("\n".join(f"\u2022 {r}" for r in remotes) or "(none)")
    )


@owner_only
async def cmd_remotes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not rclone.conf_exists():
        await update.message.reply_text("No rclone.conf yet. Send it as a file first.")
        return
    remotes = await rclone.list_remotes()
    if not remotes:
        await update.message.reply_text("No remotes found in the config.")
        return
    await update.message.reply_text(
        "Configured remotes:\n" + "\n".join(f"\u2022 {r}" for r in remotes)
    )


@guard
async def cmd_organize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not rclone.conf_exists():
        await update.message.reply_text("No rclone.conf yet. Send it as a file first.")
        return

    remotes = await rclone.list_remotes()
    if not remotes:
        await update.message.reply_text("No remotes found.")
        return

    if context.args:
        remote = context.args[0]
        if remote not in remotes:
            await update.message.reply_text(
                f"Unknown remote: {remote}\nUse /remotes to see valid ones."
            )
            return
        await _start_job(update.effective_chat.id, remote, context)
        return

    # Telegram caps callback_data at 64 bytes; skip remotes that won't fit.
    buttons = [
        [InlineKeyboardButton(r, callback_data=f"org:{r}")]
        for r in remotes
        if len(f"org:{r}".encode()) <= 64
    ]
    buttons.append([InlineKeyboardButton("\U0001f30d ALL remotes", callback_data="org:__all__")])
    await update.message.reply_text(
        "Pick a remote to organize:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@guard
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not q.data.startswith("org:"):
        return
    target = q.data[len("org:"):]
    chat_id = q.message.chat_id

    remotes = await rclone.list_remotes()

    if target == "__all__":
        await q.edit_message_text(f"Queuing {len(remotes)} remotes...")
        for r in remotes:
            if _cancel.get(chat_id):
                break
            await _start_job(chat_id, r, context)
    else:
        if target not in remotes:
            await q.edit_message_text(f"Unknown remote: {target}")
            return
        await q.edit_message_text(f"Starting organize for {target}")
        await _start_job(chat_id, target, context)


async def _start_job(chat_id: int, remote: str, context):
    if chat_id in _jobs and _jobs[chat_id].running:
        await context.bot.send_message(chat_id, "\u23f3 A job is already running. /cancel first.")
        return

    state = JobState(remote=remote, limit_gb=Config.LIMIT_GB)
    _jobs[chat_id] = state
    _cancel[chat_id] = False

    # Status board is PLAIN TEXT (no parse_mode) so filenames can't break it.
    board = await context.bot.send_message(chat_id, state.render())

    async def refresher():
        last = ""
        while state.running:
            await asyncio.sleep(Config.STATUS_REFRESH_SECONDS)
            text = state.render()
            if text != last:
                last = text
                try:
                    await context.bot.edit_message_text(
                        text, chat_id=chat_id, message_id=board.message_id
                    )
                except Exception as e:
                    logger.debug("board edit skipped: %s", e)
        # final render after job ends
        try:
            await context.bot.edit_message_text(
                state.render(), chat_id=chat_id, message_id=board.message_id
            )
        except Exception:
            pass

    refresh_task = asyncio.create_task(refresher())

    try:
        await run_organize(
            Config.ORGANIZE_SCRIPT, Config.RCLONE_CONF_PATH,
            remote, Config.LIMIT_GB, state,
            cancel_check=lambda: _cancel.get(chat_id, False),
        )
    except Exception as e:
        logger.exception("job failed")
        state.running = False
        state.finished = True
        await context.bot.send_message(chat_id, f"\u274c Error on {remote}: {e}")
    finally:
        await refresh_task
        # Clean up so the chat can start a new job.
        _jobs.pop(chat_id, None)
        _cancel.pop(chat_id, None)


@guard
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in _jobs and _jobs[chat_id].running:
        _cancel[chat_id] = True
        await update.message.reply_text("Cancelling job (stopping current transfer)...")
    else:
        await update.message.reply_text("No job running.")


@owner_only
async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: show who can use the bot."""
    owner = Config.OWNER_ID or "(unset!)"
    extra = sorted(u for u in Config.ALLOWED_USERS if u != Config.OWNER_ID)
    extra_txt = ", ".join(str(u) for u in extra) or "(none)"
    await update.message.reply_text(
        f"\U0001f451 Owner: {owner}\n"
        f"\U0001f465 Allowed users: {extra_txt}\n\n"
        "Manage access via the OWNER_ID and ALLOWED_USERS env vars."
    )


async def _post_init(app: Application):
    await start_health_server(Config.PORT)


def main():
    app = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("remotes", cmd_remotes))
    app.add_handler(CommandHandler("organize", cmd_organize))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(CallbackQueryHandler(on_callback))

    if Config.OWNER_ID is None:
        logger.warning(
            "OWNER_ID is not set - owner-only actions (config upload, /remotes, /users) "
            "are disabled. Set OWNER_ID to your Telegram user ID."
        )

    logger.info("Bot starting (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
