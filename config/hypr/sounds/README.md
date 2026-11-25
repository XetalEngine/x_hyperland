# Fusion sounds

Fusion Settings → Audio → System Audio previews eight original sounds for each
bundled sound pack. Audio → Devices contains the output, microphone and
per-application mixer. All 33 themes use the owner's replacement sound collection,
encoded as MP3. Startup is 3.6 seconds; shutdown is 1.1 seconds. The other
six cues are Error, Exclamation, Information, Question, Success and Notification.

Fresh installs enable sounds at 35%, follow the desktop theme and respect SwayNC
Do Not Disturb. Each cue can be disabled independently. Listen previews the draft
pack and volume even if normal sounds are muted. Apply sounds saves the choices.
The same pack can be selected in Theme → Mix & match. Theme component application
changes the sound design while preserving volume, mute and individual switches.
Its detailed-settings link opens Audio → System Audio. Moving between tabs keeps
unsaved sound edits; closing Settings asks before discarding them. Preview
playback stops when System Audio is hidden. There is one shared sound editor, so
pending audio edits also protect against a theme or mix replacing the sound pack.

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

The supplied collection contains 264 original synthesized cues and 33 combined
preview tracks. Its [source notes](packs/SOURCE.txt) describe the recordings.
The desktop ships the eight individual cues per theme; combined previews remain
in the converted download collection. `information.wav` maps to `info.mp3` and
`exclamation.wav` maps to `warning.mp3`, preserving existing event preferences.

The MP3 files use LAME VBR quality 4 at 44.1 kHz stereo. Encoding preserves the
source duration and levels, with no normalization, trimming or resampling. The
catalog includes source/output hashes and waveform previews measured from the
decoded MP3. The settings page reads durations from that catalog. Playback prefers
MP3 but accepts older Ogg assets while an installation is being updated.

To convert the original collection again, choose a new output folder:

```bash
python3 tools/import_sound_packs.py /path/to/HyperFusion_Theme_Sounds /path/to/new-mp3-folder --install
python3 tools/check_sound_packs.py
```

The converter preserves the WAV masters and converts all 297 files, including
combined previews. `--install` replaces the repository's sound assets after all
conversions succeed. The checker validates decoded duration, headroom, boundary
samples, stereo format, waveform data and hashes. Both require NumPy and FFmpeg
only during authoring. Runtime uses the existing PipeWire/PulseAudio tools.

`tools/generate_sound_packs.py` retains the previous procedural scores for future
authoring; it does **not** reproduce this replacement collection. Use its
`--output` option to create drafts. It refuses to overwrite existing MP3 packs
unless `--replace` is explicitly supplied.
