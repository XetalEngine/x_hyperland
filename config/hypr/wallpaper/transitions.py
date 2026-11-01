"""Temporary background layer; hyprpaper remains the persistent renderer."""
import os
from pathlib import Path
import random
import select
import subprocess
import time
from wallpaper import build, library


class Transition:
    def __init__(self, child): self.child = child

    def wait(self, token, timeout):
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            if select.select([self.child.stdout], [], [], max(0, until-time.monotonic()))[0]:
                line = self.child.stdout.readline()
                if line.strip() == token: return
                if not line: break
        raise RuntimeError('The wallpaper transition did not become ready.')

    def play(self):
        self.child.stdin.write(b'GO\n'); self.child.stdin.flush(); self.wait(b'DONE', 3)
        # Allow the final frame to reach the compositor before removing the cover.
        time.sleep(.08)

    def close(self):
        try: self.child.stdin.close()
        except (OSError, ValueError): pass
        try: self.child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.child.terminate()
            try: self.child.wait(timeout=1)
            except subprocess.TimeoutExpired: self.child.kill(); self.child.wait()
        self.child.stdout.close()


def prepare(monitor, before, after, style):
    if style == 'none': return None
    if style == 'random': style = random.choice(library.ANIMATED_TRANSITIONS)
    transition = None
    try:
        binary = build.build()
        w, h = monitor['width'], monitor['height']
        if monitor.get('transform', 0)%2: w, h = h, w
        scale = monitor.get('scale', 1) or 1
        command = [str(binary), str(monitor['x']), str(monitor['y']), str(round(w/scale)), str(round(h/scale)),
                   before.get('path', ''), before.get('fit', 'cover'), after['path'], after['fit'], style]
        env = dict(os.environ, GDK_BACKEND='wayland', GSETTINGS_BACKEND='memory')
        # This helper has no settings, portals or interaction; no shared GTK config is written.
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        transition = Transition(child); transition.wait(b'READY', 5); return transition
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        if transition: transition.close()
        return None  # Unsupported GPU/output: a normal saved wallpaper change still works.


def commit(transition, save):
    try:
        result = save()
        if transition:
            try: transition.play()
            except (OSError, RuntimeError): pass
        return result
    finally:
        if transition: transition.close()
