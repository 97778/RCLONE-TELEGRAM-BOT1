import asyncio
import os
import re
import signal
import logging

logger = logging.getLogger(__name__)

# organize.sh prints machine-readable progress lines prefixed with PROG:
#   PROG:START;<total>
#   PROG:MOVED;<bytes>;<folder_index>;<path>
#   PROG:SKIP;<path>
#   PROG:FAIL;<path>
#   PROG:DONE;<remote>
_PROG = re.compile(r"^PROG:(\w+);?(.*)$")


async def run_organize(script: str, conf_path: str, source: str,
                       limit_gb: int, state, cancel_check=None):
    """Run organize.sh for one remote, updating `state` (JobState) live."""
    env = {
        **os.environ,
        "RCLONE_CONFIG": conf_path,
        "SOURCE": source,
        "LIMIT_GB": str(limit_gb),
    }

    proc = await asyncio.create_subprocess_exec(
        "bash", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        start_new_session=True,  # own process group so we can kill rclone too
    )

    def _kill_group():
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    assert proc.stdout is not None
    try:
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if not line:
                continue
            state.last_line = line[:200]

            m = _PROG.match(line)
            if m:
                kind, rest = m.group(1), m.group(2)
                parts = rest.split(";")
                if kind == "START":
                    try:
                        state.total = int(parts[0])
                    except (ValueError, IndexError):
                        pass
                elif kind == "MOVED" and len(parts) >= 3:
                    try:
                        state.bytes_done += int(parts[0])
                    except ValueError:
                        pass
                    try:
                        state.folder_index = int(parts[1])
                    except ValueError:
                        pass
                    # path may itself contain ';' - rejoin the remainder
                    state.current_file = ";".join(parts[2:])
                    state.files_done += 1
                elif kind == "SKIP":
                    state.skipped += 1
                elif kind == "FAIL":
                    state.failed += 1

            if cancel_check and cancel_check() and not state.cancelled:
                state.cancelled = True
                _kill_group()
                break
    finally:
        # Ensure no orphaned process group survives.
        if proc.returncode is None:
            _kill_group()
        await proc.wait()

    state.exit_code = proc.returncode
    state.finished = True
    state.running = False
    return proc.returncode
