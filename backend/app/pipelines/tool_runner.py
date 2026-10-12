"""
ToolRunner Subprocess Execution Wrapper
Safely executes external commands with streaming output, cancellation killing, and timeout enforcement.
"""

import os
import signal
import subprocess
import time
from typing import List, Callable, Optional
from app.pipelines.base import CancelToken


class ToolExecutionError(Exception):
    def __init__(self, command: List[str], exit_code: int, log_tail: List[str]):
        self.command = command
        self.exit_code = exit_code
        self.log_tail = log_tail
        tail_str = "\n".join(log_tail[-20:])
        super().__init__(f"Command '{' '.join(command)}' failed with exit code {exit_code}.\nRecent logs:\n{tail_str}")


class ToolRunner:
    @staticmethod
    def run(
        command: List[str],
        cwd: Optional[str] = None,
        timeout: int = 7200,
        log_callback: Optional[Callable[[str], None]] = None,
        cancel_token: Optional[CancelToken] = None,
        progress_parser: Optional[Callable[[str], Optional[float]]] = None
    ) -> subprocess.CompletedProcess:
        """
        Execute command list without shell interpolation.
        Streams stdout and stderr line-by-line, tracks cancel token, and kills process tree on cancel.
        """
        log_lines: List[str] = []

        def log_line(line: str):
            clean = line.rstrip()
            if clean:
                log_lines.append(clean)
                if log_callback:
                    log_callback(clean)
                if progress_parser:
                    progress_parser(clean)

        # Launch subprocess
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            start_new_session=(os.name != "nt")
        )

        if cancel_token:
            cancel_token.set_active_pid(proc.pid)

        start_time = time.time()
        try:
            while True:
                # Check cancellation
                if cancel_token and cancel_token.is_cancelled():
                    ToolRunner._kill_process(proc)
                    raise RuntimeError("Command terminated due to job cancellation.")

                # Check timeout
                if time.time() - start_time > timeout:
                    ToolRunner._kill_process(proc)
                    raise TimeoutError(f"Command timed out after {timeout} seconds.")

                # Read line
                line = proc.stdout.readline() if proc.stdout else ""
                if line:
                    log_line(line)
                elif proc.poll() is not None:
                    break
                else:
                    time.sleep(0.05)

            # Consume any remaining output
            if proc.stdout:
                for line in proc.stdout:
                    log_line(line)

            exit_code = proc.wait()
            if cancel_token and cancel_token.is_cancelled():
                raise RuntimeError("Command terminated due to job cancellation.")

            if exit_code != 0:
                raise ToolExecutionError(command, exit_code, log_lines[-50:])

            return subprocess.CompletedProcess(command, exit_code, stdout="\n".join(log_lines))

        finally:
            if cancel_token:
                cancel_token.set_active_pid(None)

    @staticmethod
    def _kill_process(proc: subprocess.Popen):
        try:
            if os.name == "nt":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)])
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
