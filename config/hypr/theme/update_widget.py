"""The update badge follows the palette without replacing personal bar CSS."""
from pathlib import Path
import runtime

IMPORT = '@import url("updates.css");\n'


def style(colors):
    return '''/* Xetal update notice: subtle breathing glow, no layout movement. */
@keyframes xetal-update-pulse {
  0% { background-color: alpha(ACCENT, 0.10); box-shadow: 0 0 0 transparent; }
  50% { background-color: alpha(ACCENT, 0.25); box-shadow: 0 0 7px alpha(ACCENT, 0.35); }
  100% { background-color: alpha(ACCENT, 0.10); box-shadow: 0 0 0 transparent; }
}
#custom-updates {
  color: ACCENT; background: alpha(ACCENT, 0.08); border: 1px solid alpha(ACCENT, 0.30);
  border-radius: 8px; margin: 1px 4px; padding: 0 9px; font-weight: 600;
  transition: background-color 180ms ease;
}
#custom-updates:hover { background: alpha(ACCENT, 0.24); }
#custom-updates.available, #custom-updates.ready, #custom-updates.preparing, #custom-updates.runtime-required {
  animation: xetal-update-pulse 2.4s ease-in-out infinite;
}
#custom-updates.attention { color: TEXT; border-color: ACCENT; }
#custom-updates.current { background: transparent; border-color: transparent; }
'''.replace('ACCENT', colors['Accent']).replace('TEXT', colors['Text'])


def attach(css): return css if IMPORT.strip() in css else IMPORT+css


def write(root=None):
    root = root or runtime.ROOT.parent
    (root/'waybar/updates.css').write_text(style(runtime.colors()))
    path = root/'waybar/style.css'; path.write_text(attach(path.read_text()))


if __name__ == '__main__': write()
