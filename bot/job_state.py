import time
from dataclasses import dataclass, field


@dataclass
class JobState:
    """Live progress for a single organize run, rendered on the status board.

    Rendered as PLAIN TEXT (no Markdown) so arbitrary filenames containing
    backticks, underscores, asterisks, etc. cannot break Telegram parsing.
    """
    remote: str
    limit_gb: int = 200
    total: int = 0  # total candidate files, set from PROG:START
    started_at: float = field(default_factory=time.time)
    running: bool = True
    cancelled: bool = False
    finished: bool = False
    exit_code: int | None = None

    files_done: int = 0
    bytes_done: int = 0
    skipped: int = 0
    failed: int = 0
    folder_index: int = 1
    current_file: str = ""
    last_line: str = ""

    @staticmethod
    def _human(n: int) -> str:
        f = float(n)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if f < 1024 or unit == "TB":
                return f"{f:.1f} {unit}"
            f /= 1024
        return f"{f:.1f} TB"

    def _elapsed(self) -> str:
        s = int(time.time() - self.started_at)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}h {m}m {sec}s"
        if m:
            return f"{m}m {sec}s"
        return f"{sec}s"

    def _bar(self) -> str:
        if not self.total:
            return ""
        processed = self.files_done + self.skipped + self.failed
        frac = min(processed / self.total, 1.0)
        filled = int(frac * 10)
        return f"[{'#' * filled}{'.' * (10 - filled)}] {int(frac * 100)}%"

    def render(self) -> str:
        if self.finished and self.cancelled:
            head = "\U0001f6d1 Cancelled"
        elif self.finished:
            head = "\u2705 Finished" if self.exit_code == 0 else "\u26a0\ufe0f Finished with errors"
        elif self.cancelled:
            head = "\U0001f6d1 Cancelling (stopping transfer)"
        else:
            head = "\U0001f504 Processing"

        cur = self.current_file[-60:] if self.current_file else "-"
        progress = f"{self.files_done}" + (f"/{self.total}" if self.total else "")
        lines = [
            f"{head} \u2014 {self.remote}",
            "",
            f"\U0001f4c1 Folder: {self.remote}{self.limit_gb}gb{self.folder_index}",
            f"\U0001f4e6 Files moved: {progress}",
        ]
        bar = self._bar()
        if bar:
            lines.append(f"\U0001f4ca {bar}")
        lines += [
            f"\U0001f4be Data moved: {self._human(self.bytes_done)}",
            f"\u23ed\ufe0f Skipped: {self.skipped}   \u274c Failed: {self.failed}",
            f"\u23f1\ufe0f Elapsed: {self._elapsed()}",
            f"\U0001f3ac Current: {cur}",
        ]
        return "\n".join(lines)
