"""Console sizing uses synthetic windows/state and never touches the desktop."""

import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import console_window as cw


@pytest.mark.parametrize("data", ["{", "null", "[]", '{"width": true, "height": 800}',
                                 '{"width": 0, "height": 800}', '{"width": 900000, "height": 800}'])
def test_invalid_saved_size_is_ignored(tmp_path, data):
    path = tmp_path / "size.json"
    path.write_text(data)
    assert cw.load_size(path) is None


@pytest.fixture
def observer(tmp_path, monkeypatch):
    path = tmp_path / "size.json"
    cw.save_size(path, dict(width=1024, height=768))
    monkeypatch.setattr(cw, "process_start", lambda _: "100")
    state = dict(now=0, size=(640, 480), flags="", owner=123, transient="", kind="NORMAL", windows="40\n")
    calls = []

    def command(*args):
        calls.append(args)
        if args[:2] == ("xdotool", "search"):
            assert args[2:] == ("--onlyvisible", "--pid", "123")
            return state["windows"]
        if args[0] == "xprop":
            return (f"_NET_WM_PID(CARDINAL) = {state['owner']}\n"
                    f"_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_{state['kind']}\n"
                    f"{state['transient']}\n_NET_WM_STATE(ATOM) = {state['flags']}")
        if args[:2] == ("xdotool", "getdisplaygeometry"):
            return "1920 1080"
        if args[:2] == ("xdotool", "windowsize"):
            state["size"] = tuple(int(n) for n in args[-2:])
            return ""
        if args[:2] == ("xdotool", "getwindowgeometry"):
            return f"WIDTH={state['size'][0]}\nHEIGHT={state['size'][1]}\n"
        raise AssertionError(args)

    monkeypatch.setattr(cw, "command", command)
    monkeypatch.setattr(cw.time, "monotonic", lambda: state["now"])
    return cw.SizeObserver(123, "100", path), state, calls


def test_restores_once_then_persists_manual_resize_for_next_observer(observer):
    monitor, state, calls = observer
    assert monitor.poll()
    assert state["size"] == (640, 480)  # Allow the viewer's first framebuffer to arrive.
    state["now"] = 3
    monitor.poll()
    assert state["size"] == (1024, 768)
    state["size"] = (1200, 820)
    monitor.poll()
    monitor.poll()
    assert cw.load_size(monitor.path) == dict(width=1200, height=820)
    assert len([c for c in calls if c[:2] == ("xdotool", "windowsize")]) == 1
    assert json.loads(monitor.path.read_text()) == dict(width=1200, height=820)
    assert not list(monitor.path.parent.glob("*.tmp"))
    reopened = cw.SizeObserver(123, "100", monitor.path)
    state["size"] = (640, 480)
    reopened.poll()
    state["now"] = 6
    reopened.poll()
    assert state["size"] == (1200, 820)


@pytest.mark.parametrize("changes", [
    {"flags": "_NET_WM_STATE_FULLSCREEN"},
    {"flags": "_NET_WM_STATE_MAXIMIZED_VERT, _NET_WM_STATE_MAXIMIZED_HORZ"},
    {"flags": "_NET_WM_STATE_HIDDEN"},
    {"kind": "DIALOG"},
    {"owner": 456},
    {"transient": "WM_TRANSIENT_FOR(WINDOW): window id # 0x2000"},
    {"windows": ""},
])
def test_other_windows_and_non_windowed_sizes_are_never_changed_or_saved(observer, changes):
    monitor, state, calls = observer
    monitor.poll()
    state.update(changes, now=3, size=(1800, 1000))
    monitor.poll()
    monitor.poll()
    assert cw.load_size(monitor.path) == dict(width=1024, height=768)
    assert not any(c[:2] == ("xdotool", "windowsize") for c in calls)


def test_oversized_saved_window_is_clamped_to_current_screen(observer):
    monitor, state, _ = observer
    monitor.saved = dict(width=3840, height=2160)
    monitor.poll()
    state["now"] = 3
    monitor.poll()
    assert state["size"] == (1880, 1000)


def test_pid_reuse_ends_observation_without_accessing_windows(observer, monkeypatch):
    monitor, _, calls = observer
    monkeypatch.setattr(cw, "process_start", lambda _: "101")
    assert not monitor.poll()
    assert not calls


def test_read_only_state_directory_does_not_stop_observing(observer, monkeypatch):
    monitor, state, _ = observer
    monitor.poll()
    state["now"] = 3
    monitor.poll()
    state["size"] = (1200, 820)
    save = Mock(side_effect=PermissionError("read-only"))
    monkeypatch.setattr(cw, "save_size", save)
    assert monitor.poll()
    assert monitor.poll()
    save.assert_called_once()


def test_observer_is_detached_and_scoped_to_viewer_process(monkeypatch, tmp_path):
    monkeypatch.setattr(cw, "unavailable_reason", lambda: "")
    spawn = Mock()
    monkeypatch.setattr(cw.subprocess, "Popen", spawn)
    pid = os.getpid()
    path = tmp_path / "size.json"
    cw.observe(pid, path)
    assert spawn.call_args.args[0] == [sys.executable, str(Path(cw.__file__).resolve()),
                                     str(pid), cw.process_start(pid), str(path)]
    assert spawn.call_args.kwargs["start_new_session"] is True


@pytest.mark.parametrize("title,accepted", [("QEMU - TigerVNC", True), ("VNC connection error", False)])
def test_tigervnc_console_without_ewmh_type_is_recognized_but_dialog_is_not(monkeypatch, tmp_path, title, accepted):
    properties = ('_NET_WM_PID(CARDINAL) = 123\n'
                  '_NET_WM_WINDOW_TYPE: not found.\n'
                  'WM_CLASS(STRING) = "vncviewer", "Vncviewer"\n'
                  f'WM_NAME(STRING) = "{title}"\n')
    monkeypatch.setattr(cw, "command", lambda *_: properties)
    monitor = cw.SizeObserver(123, "100", tmp_path / "size.json")
    assert bool(monitor.properties("40")) == accepted


def test_wayland_and_missing_tools_have_an_explanation(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert "X11" in cw.unavailable_reason()
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":123")
    monkeypatch.setattr(cw.shutil, "which", lambda _: None)
    assert "xdotool and xprop" in cw.unavailable_reason()
    monkeypatch.setattr(cw.shutil, "which", lambda name: "/usr/bin/" + name)
    assert cw.unavailable_reason() == ""


@pytest.mark.parametrize('floating,rule', [(True,'float on; center on'),(False,'float off')])
def test_hyprland_console_uses_a_scoped_launch_rule_and_quotes_arguments(monkeypatch, floating, rule):
    import shlex
    import subprocess
    monkeypatch.setenv('HYPRLAND_INSTANCE_SIGNATURE','fixture-session')
    monkeypatch.setenv('XCURSOR_THEME','Xetal-Cursor-cyan')
    command=['/fixture/path with spaces/viewer', 'spice://127.0.0.1:5930', '$(must not run)']
    dispatch=Mock(return_value=subprocess.CompletedProcess([],0,'ok\n',''))
    monkeypatch.setattr(cw.subprocess,'run',dispatch)
    assert cw.launch(command,floating=floating) is None
    args=dispatch.call_args.args[0]
    assert args[:3]==['hyprctl','dispatch','exec']
    assert args[3].startswith('['+rule+'] ')
    assert shlex.join(command) in args[3]
    assert 'XCURSOR_THEME=Xetal-Cursor-cyan' in args[3]
