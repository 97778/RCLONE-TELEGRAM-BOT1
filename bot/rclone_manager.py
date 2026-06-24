import asyncio
import os
import logging

logger = logging.getLogger(__name__)


class RcloneManager:
    def __init__(self, conf_path: str):
        self.conf_path = conf_path

    def conf_exists(self) -> bool:
        return os.path.isfile(self.conf_path)

    def save_conf(self, data: bytes):
        os.makedirs(os.path.dirname(self.conf_path), exist_ok=True)
        with open(self.conf_path, "wb") as f:
            f.write(data)
        logger.info("Saved rclone.conf to %s", self.conf_path)

    async def list_remotes(self) -> list[str]:
        """Return all configured remotes (e.g. ['Dropbox33:', 'gdrive:'])."""
        if not self.conf_exists():
            return []
        proc = await asyncio.create_subprocess_exec(
            "rclone", "listremotes",
            "--config", self.conf_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            logger.error("listremotes failed: %s", err.decode())
            return []
        return [line for line in out.decode().splitlines() if line.strip()]
