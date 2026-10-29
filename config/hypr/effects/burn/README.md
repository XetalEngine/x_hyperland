# Compiz Burn for Xetal

Open **Fusion Settings → Theme → Window effects → Burn**. Enable **Burn closing
windows**, adjust the controls and choose **Apply Burn**. **Preview Burn** opens
a disposable window; close it with its button or X. **Compiz defaults** restores
the original settings while preserving your enable switch. The master Animations
switch in **Window appearance** and individual `no_anim` window rules still apply.

This is a port of Burn from the supplied `XetalCompiz_old` source, not a flame
shader approximation. Only Burn, its particle equations, texture and option
metadata are included. No Compiz compositor or unrelated effects are installed.

| Setting | Compiz default | Range |
| --- | --- | --- |
| Fire particles | 1000 | 100–10000 |
| Particle size | 5 | 0.1–20 |
| Particle slowdown | 0.5 | 0.1–10 |
| Particle life | 0.7 | 0.1–1 |
| RGBA color | `FFFF 3333 0555 FFFF` | Four 16-bit channels, including opacity |
| Direction | Down | Down, Up, Left, Right, Random, Automatic |
| Constant speed | Off | Duration scales by window height / 500 |
| Smoke | Off | Smoke uses one tenth of the particle count |
| Randomly colored fire | Off | Original Mystical Fire colors |
| Close duration | 200 ms | 50–4000 ms; the first Animation close-duration default |
| Intense animation time step | 30 ms | 1–400 ms |

Particles finish fading after the window has burned away. At the maximum life
setting they can linger for roughly 25 seconds. Automatic direction uses the
pointer location at close time, as Compiz's close-animation path does. Particle
coordinates use logical pixels so the effect has the same visual size on scaled
displays. Color is converted to the compositor's working color space.

## Integration and compatibility

The native adapter is tested with **Hyprland 0.56.2**, commit
`efb50993780079460b0cbed1363e2166a2de1d9f`, on x86-64 with its OpenGL renderer.
It needs matching Hyprland development headers (`pkg-config hyprland`), a C++23
compiler, pkg-config and GLESv2 development files. The profile installer tries
the optional build. Session startup loads it asynchronously, and the control
desk can build it on first enable. Binaries are built locally, never shipped.

Both the builder's tested-commit check and Hyprland's full runtime plugin ABI
check must pass. A compositor upgrade to a different commit leaves the ordinary
closing animation in place until the adapter is updated. It never fetches or
loads an unverified replacement plugin. The rest of the desktop still starts.
Initialization errors go to the active session's `burn.log`.

The adapter hooks the **window** snapshot overload and the compositor's existing
fadeout rendering planes. Opening, moving, minimizing and layer-shell surfaces
retain their normal behavior. Once the app exits, the effect owns only its
snapshot, not the process or live window. Animation records stay on their original
monitor/workspace and are discarded if the output mode or scale changes.
Up to eight burns run simultaneously; additional closes use the normal animation.
Direct scanout is suspended while particles are visible, then its prior block
state is restored. Disabling Burn removes active snapshots immediately.

`settings.conf` is the single saved configuration. The UI validates all options,
checks for outside edits, writes atomically, reloads the plugin and rolls back
on activation errors. Active burns retain the settings they started with.
No global environment, KDE/Plasma configuration or system service is changed.
The small startup loader and any compiler it starts are owned by the session.

Compiz's original Burn subtracts a configured step per paint. This port schedules
those steps using a monotonic clock, avoiding speed changes between 60/144 Hz
monitors. Catch-up work is bounded after stalls. The undefined original case
`duration <= time_step_intense` completes immediately without dividing by zero.
The random generator is private to the effect, with the same 8-bit distribution.

## Source and license

`native/engine.hpp`, `native/plugin.cpp`, `native/fire_texture.hpp`, the native
test and the extracted `compiz-options.xml` are **GPL-2.0-or-later**, with the
license in [COPYING](COPYING). The separate Python controls/build helpers retain
the surrounding repository's MIT license. Compiz authors: **Erkin Bahceci**
(animation) and **Dennis Kasprzyk** (particle system and texture). Integration:
XetalEngine, 2026. The original texture's copyright header is preserved.

The 32×32 RGBA sprite is unchanged. Its C array declaration is unsized to allow
the string's trailing NUL in C++; only the original 4096 image bytes are uploaded.
Reference input SHA-256 hashes from the supplied source:

```
aa3a5d3a3a8f57ba06f27b4c6b8cc8c6179e2162490815be405bb6a2630045b3  burn.c
337423d1aa73398907dd09ddd8fd36f2892ea7597482f97eb4a6ef81474ee67f  particle.c
bfa82a7b4e6244ffaa6d24067a44052bbe872dcde378e0095fdd1c9d08ea5557  animation_tex.h
```

Run `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s
config/hypr/effects/burn -v` from the repository for the option, UI, transaction
and compiled particle-engine checks. Native renderer changes must also be
tested in a disposable nested Hyprland before loading them in a working session.
`hyprctl xetal-burn` reports enable state, active records and lifecycle counters.
