#!/usr/bin/env python3
"""Real TLS VNC viewer, pixels and clipboard in private X servers only."""
import ctypes
import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import tempfile
import time

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]


def main():
    build = ROOT/'config/hypr/control_panel/.build'
    cached = build/'tigervnc/usr/bin'
    server = shutil.which('Xvnc') or str(cached/'Xvnc')
    passwd = shutil.which('vncpasswd') or str(cached/'vncpasswd')
    children = []
    with tempfile.TemporaryDirectory(prefix='fusion-vnc-check-') as temporary:
        folder = Path(temporary)
        env = dict(os.environ, HOME=temporary, XDG_CONFIG_HOME=str(folder/'config'),
                   XDG_RUNTIME_DIR=temporary, XDG_STATE_HOME=str(folder/'state'),
                   DBUS_SESSION_BUS_ADDRESS='unix:path='+str(folder/'no-bus'),
                   WAYLAND_DISPLAY='no-compositor', HYPRLAND_INSTANCE_SIGNATURE='',
                   QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='', QT_PLUGIN_PATH='',
                   LD_LIBRARY_PATH=str(build/'tigervnc/usr/lib'))
        def spawn(argv, **kwargs):
            child = subprocess.Popen(argv, env=env, **kwargs)
            children.append(child)
            return child
        def xserver(command):
            read, write = os.pipe()
            try:
                child = spawn([*command, '-displayfd', str(write), '-nolisten', 'tcp'],
                              pass_fds=(write,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                os.close(write); write = -1
                assert select.select([read], [], [], 10)[0], 'Private X server did not start'
                number = os.read(read, 32).decode().strip()
                assert number.isdigit() and child.poll() is None, 'Private X server failed'
                return ':'+number
            finally:
                os.close(read)
                if write >= 0: os.close(write)
        try:
            client_display = xserver(['Xvfb', '-screen', '0', '1024x768x24'])
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
            password = folder/'password'
            result = subprocess.run([passwd, '-f'], input=b'fixture8\n', capture_output=True, env=env, check=True)
            password.touch(mode=0o600); password.write_bytes(result.stdout)
            server_display = xserver([server, '-geometry', '640x400', '-depth', '24', '-localhost',
                                      '-rfbport', str(port), '-SecurityTypes', 'TLSVnc', '-PasswordFile', str(password)])
            xlib = ctypes.CDLL('libX11.so.6')
            xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]; xlib.XOpenDisplay.restype = ctypes.c_void_p
            xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]; xlib.XDefaultRootWindow.restype = ctypes.c_ulong
            xlib.XSetWindowBackground.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
            xlib.XClearWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            xlib.XFlush.argtypes = [ctypes.c_void_p]; xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
            display = xlib.XOpenDisplay(server_display.encode()); assert display
            try:
                window = xlib.XDefaultRootWindow(display)
                xlib.XSetWindowBackground(display, window, 0x2169c9); xlib.XClearWindow(display, window); xlib.XFlush(display)
                env.update(DISPLAY=client_display, FUSION_VNC_TEST_PORT=str(port),
                           FUSION_VNC_TEST_ROOT=str(ROOT/'config/hypr'), FUSION_VNC_TEST_SYNC=temporary)
                test = spawn([str(build/'rdp/rdp_tests'), 'vncLaunchUsesLiteralArgumentsAndPrivateEnvironment',
                              '-o', str(folder/'result.txt')+',txt'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic()+12
                pixels = False
                while time.monotonic() < deadline and test.poll() is None:
                    shot = ImageGrab.grab(xdisplay=client_display).convert('RGB')
                    colors = dict((color, count) for count, color in shot.getcolors(1024*768) or [])
                    if colors.get((33, 105, 201), 0) > 50000: pixels = True; break
                    time.sleep(.1)
                assert pixels, 'Encrypted VNC did not display the test desktop'
                # Xvfb has no window manager to focus newly mapped windows.
                # TigerVNC only publishes the local clipboard while focused.
                xlib.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)), ctypes.POINTER(ctypes.c_uint)]
                xlib.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
                xlib.XFree.argtypes = [ctypes.c_void_p]
                local = xlib.XOpenDisplay(client_display.encode()); assert local
                try:
                    local_root = xlib.XDefaultRootWindow(local)
                    tree_root, parent, count = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_uint()
                    windows = ctypes.POINTER(ctypes.c_ulong)()
                    assert xlib.XQueryTree(local, local_root, ctypes.byref(tree_root), ctypes.byref(parent), ctypes.byref(windows), ctypes.byref(count))
                    assert count.value
                    xlib.XSetInputFocus(local, windows[count.value-1], 2, 0); xlib.XFlush(local); xlib.XFree(windows)
                finally: xlib.XCloseDisplay(local)
                time.sleep(.2)
                payload = b'Fusion VNC clipboard fixture'
                clip = spawn(['xclip', '-display', client_display, '-selection', 'clipboard', '-silent'], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                clip.stdin.write(payload); clip.stdin.close()
                deadline = time.monotonic()+3
                while time.monotonic() < deadline:
                    received = subprocess.run(['xclip', '-display', server_display, '-selection', 'clipboard', '-o'],
                                              capture_output=True, env=env, timeout=2)
                    if received.stdout == payload: break
                    time.sleep(.1)
                else: raise AssertionError('VNC clipboard did not reach the private server')
                (folder/'verified').touch(); test.wait(timeout=5)
                assert test.returncode == 0, (folder/'result.txt').read_text()
                print('PASS: Control Panel launches TigerVNC; TLS authentication, real pixels, clipboard, and clean viewer shutdown.')
            finally: xlib.XCloseDisplay(display)
        finally:
            for child in reversed(children):
                if child.poll() is None: child.terminate()
            for child in children:
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired: child.kill(); child.wait()


if __name__ == '__main__': main()
