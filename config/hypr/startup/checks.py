"""Refresh the same read-only report used by fusion-check without blocking UI."""
from pathlib import Path
import queue
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
import plugin_health


class LiveCheck:
    def __init__(self, inspect=None):
        self.inspect = plugin_health.inspect if inspect is None else inspect
        self.report = None
        self.busy = False
        self.next_check = 0
        self.results = queue.SimpleQueue()

    def refresh(self):
        try:
            self.report = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.next_check = time.monotonic() + 5
        if not self.busy and time.monotonic() >= self.next_check:
            self.busy = True
            threading.Thread(target=self.run, daemon=True).start()
        return self.report

    def run(self):
        try:
            report = self.inspect()
        except Exception as error:
            # A broken checker/IPC connection must be visible, never a green
            # empty inventory or an indefinitely stuck "checking" panel.
            report = dict(ok=False, error=str(error) or type(error).__name__)
        self.results.put(report)
