# Screen recording

**Alt+F9** starts recording the monitor under the pointer. Press it again, or click the **REC** timer in the bar, to stop and save. Moving the pointer or changing workspaces does not change the recorded monitor. Disconnecting that monitor ends and saves the recording.

The **Recording saved** notification includes **📂 Show in folder**. Click it to open Fusion Files with that exact MP4 selected. Clicking the notification body does the same. The action remains available in notification history for the current desktop session, until the notification is dismissed. It is offered only after the MP4 has been checked and saved successfully.

The defaults are **64 FPS**, **desktop audio**, **high quality**, and **MP4** in your XDG Videos folder (`~/Videos` when no folder is configured). Fusion Settings → Capture offers frame rate, quality, automatic/software encoding, desktop/microphone/no audio and a custom save folder. Changes apply to the next recording. The shortcut is editable in Hotkeys.

Automatic encoding probes available NVIDIA NVENC and VA-API encoders before using the CPU. Actual capture throughput depends on the GPU, display refresh rate, resolution and load; 64 FPS is the encoded output rate, and frames may repeat when the display updates more slowly. Audio uses the default output's monitor source, or the default microphone, selected at recording start. It does not change audio routing or mix the microphone into desktop audio.

The recorder uses `wf-recorder` and FFmpeg, installed by the Arch, Fedora and Debian setup recipes. Video is captured into a private `.fusion-recording-*` directory inside the destination folder, then copied into an MP4 container without re-encoding. Only a successfully checked MP4 is published under its final name. If capture or saving fails, the temporary capture and `capture.log` remain in the recovery directory shown in the notification and settings. They can be removed after recovering the video. Saving temporarily needs space for both copies.

The controller starts on demand and follows the current Hyprland IPC connection. It finalizes an active recording when that session ends, and owns only its own child processes. There is no persistent user service or shared portal/audio configuration change.

Implementation references: [wf-recorder](https://github.com/ammen99/wf-recorder), [FFmpeg MP4 muxer](https://ffmpeg.org/ffmpeg-formats.html#mov_002c-mp4_002c-ismv).
