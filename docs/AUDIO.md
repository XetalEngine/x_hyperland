# Microphone boost and hardware capture gain

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

Run the existing mixer and hardware-gain tests with offscreen Qt:

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s config/hypr/control_center -p 'test_audio*.py' -v
```

The tests use fixture devices. Check the actual microphone in a normal desktop
session as well: opening/refreshing should not change gain; lowering boost
should reduce overload; unplugging or changing input ports should not apply
a queued change to another device. A microphone without a separate control
must keep the main volume control usable and display the unsupported message.

ALSA API reference: https://www.alsa-project.org/alsa-doc/alsa-lib/group___simple_mixer.html
