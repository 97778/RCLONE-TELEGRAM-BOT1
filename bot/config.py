import os


class Config:
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable is required")

    # The single owner/admin Telegram user ID. Has full control.
    OWNER_ID = int(os.environ["OWNER_ID"]) if os.environ.get("OWNER_ID") else None

    # Additional users allowed to RUN/CANCEL jobs (not admin actions).
    # The owner is always implicitly allowed.
    ALLOWED_USERS = {
        int(u.strip())
        for u in os.environ.get("ALLOWED_USERS", "").split(",")
        if u.strip()
    }

    LIMIT_GB = int(os.environ.get("LIMIT_GB", "200"))
    PORT = int(os.environ.get("PORT", "8080"))
    STATUS_REFRESH_SECONDS = int(os.environ.get("STATUS_REFRESH_SECONDS", "8"))
    RCLONE_CONF_PATH = os.environ.get("RCLONE_CONF_PATH", "/data/rclone.conf")
    ORGANIZE_SCRIPT = os.environ.get("ORGANIZE_SCRIPT", "/app/scripts/organize.sh")

    @classmethod
    def is_owner(cls, user_id: int) -> bool:
        return cls.OWNER_ID is not None and user_id == cls.OWNER_ID

    @classmethod
    def is_allowed(cls, user_id: int) -> bool:
        # Owner is always allowed. Otherwise must be on the allow-list.
        # If neither OWNER_ID nor ALLOWED_USERS is set, deny everyone.
        return cls.is_owner(user_id) or user_id in cls.ALLOWED_USERS
