# Fusion sounds

Fusion Settings → Theme → Sounds previews eight original sounds for each of the
11 desktop themes. Startup is 4.15 seconds; shutdown is 3.05 seconds. The other
six cues are Error, Exclamation, Information, Question, Success and Notification.

Fresh installs enable sounds at 35%, follow the desktop theme and respect SwayNC
Do Not Disturb. Each cue can be disabled independently. Listen previews the draft
pack and volume even if normal sounds are muted. Apply sounds saves the choices.
The same pack can be selected in Theme → Mix & match. Theme component application
changes the sound design while preserving volume, mute and individual switches.

The profile owns all assets and preferences. No shared mixer, KDE setting, user
service, login manager or system sound theme is changed. `settings.json` is a
personal preference during desktop updates. The player reads it for every sound,
so no audio service restart is needed.

- `session.sh` requests startup music once per compositor instance.
- Fusion's confirmed logout/restart/power-off actions play shutdown music before
  issuing the original command. Lock and suspend do not play it. Shutdown from a
  terminal, another desktop or the hardware power switch is not intercepted.
- SwayNC's receive hook handles notification sounds. It honors `suppress-sound`,
  skips replacement/progress updates, and rate-limits bursts. Sound names such as
  `dialog-warning` and `dialog-information`, urgency Critical, and category
  `transfer.complete` select the appropriate cue. Other notifications use the
  Notification chime. No notification content is executed or stored.
- Fusion's Python Qt runtime and private Qt 5/6 platform theme add sounds to
  QMessageBox error, warning, information and question dialogs. A shared app
  property prevents duplicate hooks. Already-open applications pick up new hook
  code when reopened; their saved pack choices are read live.

Only bundled filenames are playable. PipeWire `pw-play` is preferred, with
`paplay` as fallback. Playback has a short deadline, watches the compositor's
socket, and terminates only its own audio process. Missing audio never prevents
normal notifications or a confirmed session action.

The Ogg files are original compositions and synthesis, under the repository's
MIT license; they contain no third-party samples or songs. From the repository,
`python3 tools/generate_sound_packs.py` regenerates them with NumPy and FFmpeg.
`python3 tools/check_sound_packs.py` checks decoded duration, headroom, quiet edges,
stereo format, unique assets and catalog hashes. These are authoring tools, not
runtime dependencies. The catalog also contains the actual waveform previews.
