# Audio devices and microphone gain

## Waybar mixer and output test

The outlined **Mixer** button immediately to the right of Waybar's volume slider opens a
theme-colored popup. **Main volume** stays fixed on the left; each playing app
gets its own volume, mute and output selector. Multiple streams from one app
stay in one column, and apps appear/disappear as they start/stop using audio.

The popup fits Main volume and the actual app columns, growing and shrinking as
apps start or stop. One app gets a compact two-column popup without unused space.
Larger, high-contrast labels make the app names, levels and controls easier to read.
Up to ten apps fit without scrolling on a 1920-pixel-wide work area at 100% scale;
columns use extra width on larger displays. Smaller work areas and additional apps use horizontal
scrolling; the main volume remains reachable. Resizing waits while a fader is held
or a device menu is open, and keeps the popup's right edge anchored without taking
focus. Scrolling over the mixer scrolls
the columns without changing a fader. Drag a fader or use its arrow keys to set
volume. Click the speaker again, click outside, or press Escape to dismiss it.
**Settings** opens the full Devices/System Audio page. Right-clicking the
Waybar Mixer button also opens Settings. The volume percentage keeps its direct
shortcut to the full Audio settings page.

**Test** inside Settings' Output box, and beside the popup's Main volume mute
button, plays the current desktop theme's **success** sound through that output.
It uses a short preview at 35% clip gain, respects the device's existing volume
and mute, and works even if automatic system sounds or notifications are off.
Press **Stop** to cancel; closing the popup/page or changing output also stops
the preview. No default device, volume, mute or system-sound preference is changed
by a test. The button waits until a newly selected monitor output is ready.

Mixer reads run in the background, refresh on audio-server events, and stop
polling/subscribing when hidden. The popup shares Settings' device identity
checks and serialized writes; it does not probe microphone hardware gain.

## System Default and individual app outputs

Each app's device list starts with **System Default** in both Settings and the
Waybar mixer. New apps follow the main **Output** selection. The tooltip names
the current device. Choosing a specific output overrides that app only; changing
the main output afterward moves following apps and keeps individual overrides.
Choosing **System Default** again clears the override and resumes following.
The Recording tab uses the same choice for the main **Microphone** selection.

An explicit device choice stays explicit even when it happens to equal the
current main output. Mixed stream choices within one app are shown as **Mixed
routing** until a selection is applied to the whole app. Existing routes chosen
outside Fusion are respected. Refreshing the UI never changes a route.

`control_center/audio_routing.py` reads PipeWire target metadata to distinguish
default following from a pinned device. Explicit choices use WirePlumber's
target metadata, which [WirePlumber remembers for later streams](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/settings.html).
Returning to System Default uses the audio server's default-device move, which
clears that saved target. Routing continues with both mixers closed. Native audio
state is already covered by **Default Settings → Audio** save/load/reset.

## Monitor audio outputs

**Fusion Settings → Audio → Devices → Output** lists connected HDMI/DisplayPort
monitors by their reported name and connection. A graphics card can expose only
one monitor through its active audio profile even while several monitors are
connected. The output picker also reads the card's other available monitor
connections, so they remain selectable without already having an active sink.

Selecting a monitor activates its matching profile/port, waits for the output
to become ready, then makes it the default for apps using **System Default**.
Existing USB, Bluetooth, analog and virtual outputs remain in the list. Per-app
pickers in Settings and the popup show the same monitor names and connections.
Selecting one there activates it and moves only that app's current streams;
it does not explicitly change the system default. On cards exposing one HDMI
output at a time, choosing another monitor also switches that card's active
audio output. Other streams using the previous card profile follow the audio
server's policy when that output is replaced.
Opening or refreshing the page only reads the inventory; it does not switch
profiles, change volume/mute, or restart the audio services.

Card/port events refresh the list after hotplug and external profile changes.
Selection rechecks the card identity, connection and monitor name before
changing anything. Per-app selections also recheck stream identities before
activation and routing. Activation or routing failures restore the previous profile when it is
still the same card and no other controller has selected a different profile.
Unavailable connections are omitted, and errors stay visible in the mixer.
Compatible existing surround profiles and microphone inputs are preserved when
choosing a profile for a monitor.

`control_center/audio_outputs.py` owns monitor discovery and activation through
the existing PulseAudio-compatible backend. Device operations run in the same
background queue as the other mixer controls. Pending volume changes are
canceled when selecting another output.

## Microphone boost and hardware capture gain

Fusion Settings → Audio keeps microphone volume and hardware gain separate.
The additional **Mic boost** fader uses the gain control exposed by the selected
microphone's ALSA card. It displays the driver's actual dB values, including
negative gain where supported. **Minimum** selects that control's lowest step;
it does not change gain merely by opening the page.

If speech is excessively loud or distorted, lower boost first and then adjust
microphone volume for a comfortable recording level. Reducing digital volume
cannot repair a signal already clipped upstream. When no dedicated boost is
available but the device provides hardware capture gain, that control is shown
as **Hardware capture gain**; it may also change the main microphone volume.
Devices without either control show an explanation instead of a pretend boost
slider. Hardware controls and their ranges depend on the device and driver.

Changes apply immediately. Existing audio-server/ALSA policy determines whether
hardware values survive a reboot; this page does not rewrite system mixer
configuration or save machine-specific gain values into the repository.

## Device selection and implementation

- `control_center/audio_gain.py` uses the ALSA simple-mixer API through Python's
  standard `ctypes` module. It needs `libasound.so.2`, not the `amixer` program.
  Setup declares `alsa-lib` on Arch/Fedora and `libasound2t64` on Debian 13.
- Hardware is selected from the source's ALSA card property, not its PulseAudio
  source/card index. Monitor and virtual sources are excluded.
- Recognized input boost/preamp controls are preferred. A playback-channel
  control named **Mic Boost** is supported, but ordinary playback **Mic**,
  speaker, headphone, loopback, sidetone and output controls are excluded.
- Jack-specific controls must match the source's active input port. Unknown
  jack mappings are not guessed. The source serial, input port, opened card
  identity, control identity and range are checked again before changing gain.
- Gain operations use the existing background operation queue. Refreshing is
  read-only; switching microphones/controls or hiding the page cancels a
  pending slider commit. Multiple hardware steps are displayed using the
  driver's dB conversion, not a fabricated linear dB scale.
- Channel step offsets are retained where the hardware range permits. Changes
  do not unmute the microphone, alter playback, or restart PipeWire/WirePlumber.

## Verification

Run the mixer, monitor-routing and hardware-gain tests with offscreen Qt:

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/control_center -p 'test_audio*.py' -v
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/quick_panel -p 'test_*.py' -v
python3 -m unittest discover -s config/hypr/sounds -p 'test_sounds.py' -v
python3 tests/check_audio_routing.py
```

The monitor tests cover inactive profiles, delayed output creation, port changes,
unplugging, reused card identities, activation rollback and concurrent changes
from another controller. They do not change the host's audio routing.

Popup tests exercise tight fitting for zero through ten apps, overflow, constrained
displays, fixed main volume, live resizing and deferral during slider/menu use,
mute/volume/routing actions, wheel scrolling and dismissal.
The native routing check starts private PipeWire/Pulse/WirePlumber instances
with no hardware monitors and two null outputs. It verifies default following,
independent overrides, pinning the current default, clearing overrides and app
restarts without changing the desktop's audio devices, volume or saved routes.
Preview tests use a stub player to check the selected target, current theme,
error feedback, cancellation and disabled controls while an output is switching.

The tests use fixture devices. Check the actual microphone in a normal desktop
session as well: opening/refreshing should not change gain; lowering boost
should reduce overload; unplugging or changing input ports should not apply
a queued change to another device. A microphone without a separate control
must keep the main volume control usable and display the unsupported message.

ALSA API reference: https://www.alsa-project.org/alsa-doc/alsa-lib/group___simple_mixer.html
