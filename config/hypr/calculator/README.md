# Calculator

Hyper Fusion's bundled programmer calculator comes from the owner's
`WindowsCalculatorClone` project. It is an independent implementation inspired
by programmer mode in Windows Calculator, with its own arithmetic engine, Qt
interface and SVG artwork.

The bundled copy uses PyQt6, already required by the desktop. It has no dependency
on the original project, shell aliases, a virtual environment or PySide6. Run
`python3 ~/.config/hypr/calculator/app.py`, or open **Calculator** in Apps.

DEC and HEX input, signed 8/16/32/64-bit arithmetic, parentheses, repeated equals,
AND/OR/XOR/NOT, shifts, a bit view, clipboard and session history are included.
Auto calculate shows live results as you type. Arithmetic overflow wraps to the
selected word size; division truncates toward zero. This is an integer calculator.

Keyboard and numpad input only apply while this window is focused. Ctrl+D and
Ctrl+H select DEC and HEX, Enter calculates, Delete clears the current entry,
Escape clears the calculation, and F1 opens the shortcut reference.

DEC/HEX and Auto calculate preferences are stored only in
`calculator/state/preferences.ini`. Setup excludes that state, and updates leave
the recipient's copy alone. The application ID is `xetal-calculator`; its desktop
entry and floating-window rule belong to the Hyprland profile.

From this directory, run the included arithmetic and UI regression suite with:

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```
