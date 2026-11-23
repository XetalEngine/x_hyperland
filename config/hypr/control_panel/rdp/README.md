# Fusion Remote Desktop · RDP and VNC

Open **Control Panel → RDP** (in **Network & connections**), enter the PC's
address and account, choose **RDP** (the default) or **VNC**, and select **Connect**. Connections are saved automatically;
**Save connection** also lets you prepare a PC without connecting. Select a saved
PC in the sidebar to reconnect or edit it. Several session windows can run at once.

This is Hyper Fusion's native Qt interface using the
[FreeRDP 3 client libraries](https://github.com/FreeRDP/FreeRDP) (3.2 or later) for the protocol.
RDP sessions use the native Qt window. VNC connections open
[TigerVNC](https://tigervnc.org/doc/vncviewer.html) with the saved connection's
options. The destination PC needs the corresponding server enabled. The second
tab, **Share this desktop · RDP / VNC in**, hosts this session over RDP or VNC.
The first tab is **Connect to a PC · RDP / VNC out**; incoming sharing and
outgoing connections have separate settings.

## VNC connections

The selector changes the default port between 3389 and 5900; explicit custom
ports are preserved. RDP-only fields are hidden for VNC. VNC settings include
clipboard text, remote resizing where supported, full screen, view only,
keeping other viewers connected, and offering reconnection after errors.
View only also disables outgoing clipboard and resize requests.

Encryption is required by default. **Allow legacy unencrypted VNC** additionally
permits classic VNC authentication and servers without authentication; use that
only over a trusted network or an SSH tunnel. TLS certificate questions are
handled by TigerVNC, independently of the RDP certificate preference. A username
is optional and only used when the server requests one. VNC clipboard images,
folder/printer sharing and microphone forwarding are not exposed here.

## RDP defaults and controls

- The current user's home directory is shared read/write as `Home` on
  `HyperFusion`, accessible on Windows as `\\tsclient\Home`. Choose a different
  folder or disable sharing per PC. Paths containing spaces or commas are literal.
- Clipboard text and images, remote audio, microphone, local printers,
  automatic reconnect, and desktop resizing are enabled. Server policy and the
  installed local audio/printing backends determine what is available.
- Certificate acceptance is automatic, including unverified or changed
  certificates. Turn off **Automatically accept certificates** to require a
  certificate accepted by FreeRDP's trust checks. TLS/NLA remain enabled.
- Sessions start in a window. **Start in full screen** and **Administrative
  session** are optional. **Gateway and keyboard** contains an RD Gateway address
  using the same account and a keyboard layout selector.
- The session toolbar hides after inactivity. Move to the top edge to reveal
  **Window mode / Full screen**, **Ctrl+Alt+Del**, and **Disconnect**. The local
  shortcuts are `Ctrl+Alt+Shift+F` for full screen and `Ctrl+Alt+Shift+Home` for
  controls. Compositor shortcuts remain local.

Clipboard support covers Unicode text, PNG, and Windows bitmap images. Transfer
files through the shared folder; clipboard file copying and USB/smartcard
redirection are not implemented. Resizing changes one remote desktop; it does not
span the local monitor arrangement. Servers without display-control support use
a scaled view.

## Share this desktop · RDP / VNC in

Share one monitor from the active Hyper Fusion session using **RDP** through
hypr-rdp or **VNC** through WayVNC. Only one incoming protocol runs at a time;
outgoing connection windows remain independent. RDP uses NLA/TLS and VNC uses
authenticated TLS. Hosting defaults to **off**, **Local computer only** and no
automatic startup.

1. Select the incoming tab, protocol and monitor. **Current monitor** resolves
   to the current output when sharing starts.
2. Choose **Listen on** and the port. Select the computer's LAN address for
   another PC to connect; `127.0.0.1` is local-only and requires an SSH tunnel
   for remote access. The usual ports are 3389 for RDP and 5900 for VNC.
3. Set a sharing username and a password of 12–256 characters. A blank password
   keeps an already-saved password; the placeholder is not a password.
   **Start sharing** stays unavailable until a password is supplied or saved.
4. Choose the frame limit and available remote-control options. Select
   **Start sharing after I sign in** only if desired, then **Start sharing**.
5. Connect using Windows Remote Desktop for RDP or a TLS-capable VNC client
   such as TigerVNC. Use the displayed address and verify the certificate's
   SHA-256 fingerprint. **Stop sharing** disconnects viewers.

The status distinguishes **Starting**, **Listening · waiting for a connection**,
active connection counts and **Sharing is off**. Counts reflect the server's
TCP connections, including authentication negotiation; they are not a list of
authenticated users. Failed starts keep their error visible. Background polling
does not flash or disable the buttons, preserves unsaved edits, and queues user
actions behind reads. While sharing runs, the connection card shows its active
endpoint rather than unsaved form values.

The output pane strips terminal color/control sequences, including from logs
written by an already-running server. New server processes also request plain
text. An existing pane refreshes without requiring a sharing restart.

RDP shares keyboard/mouse input, text/image clipboard and mirrored desktop
audio; clipboard file transfer is disabled. VNC offers view-only sharing.
No firewall rules are opened automatically. Sharing ends at logout and does
not expose the greeter or provide remote login before the desktop starts.

Incoming settings, TLS material and the sharing password use private
desktop-services state, separately from the outgoing connection wallet.

## Saved outgoing connections and passwords

PC settings live in `control_panel/state/rdp/connections.json` under the installed
Hyprland configuration. Writes are atomic and locked, the directory is private,
and files have mode `0600`. Invalid existing JSON is preserved rather than reset.
This state directory is already excluded from source control and preserved by
Hyper Fusion updates.

Passwords go through `secret-tool` to the desktop's Secret Service wallet
(GNOME Keyring on the default install). They are passed through standard input,
never placed in profiles, process arguments, or application error messages.
TigerVNC receives the selected password in its child process environment using
`VNC_PASSWORD`/`VNC_USERNAME`, not a temporary password file. The wallet's RDP
namespace and existing credential keys remain unchanged; VNC has its own
namespace and keys. Switching protocols clears the displayed password.
If the wallet is locked/unavailable, the page explains that the password was not
saved; a connection can still use the password entered for this session.
Editing a PC/account clears a loaded password, and delayed wallet replies cannot
overwrite a newly typed password or populate another PC. Deletion removes the
wallet entry before the profile.

## Build and checks

The parent Control Panel build links this library. Arch needs `freerdp` and
`libsecret`, Fedora needs `freerdp-devel` and `libsecret`, and Debian needs
`freerdp3-dev` and `libsecret-tools`, alongside the existing Qt/C++ prerequisites.
The installer checks `freerdp3`, `freerdp-client3`, `winpr3`, and `secret-tool`.
It also installs TigerVNC and checks `vncviewer` (or Debian's `xtigervncviewer`).
Incoming VNC needs WayVNC. The desktop-services build supplies the pinned
hypr-rdp RDP host; see the [dependency guide](../../../../docs/DEPENDENCIES.md)
and [integration status](../../../../docs/DESKTOP-ROADMAP.md#components-and-validation)
for its source build and offline requirements.

From the repository root:

```sh
cmake -S config/hypr/control_panel/backend -B config/hypr/control_panel/.build -DBUILD_RDP_TESTS=ON
cmake --build config/hypr/control_panel/.build --target CachyOsTools rdp_tests --parallel
QT_QPA_PLATFORM=offscreen config/hypr/control_panel/.build/rdp/rdp_tests
```

The isolated checks exercise real FreeRDP settings, profiles and file modes,
wallet stdin and failures, stale credential replies, input mapping, display
coordinates, clipboard protocol callbacks, cancellation before connection, and
toolbar interaction. They use temporary profiles and a fake wallet executable;
they do not contact a PC or alter saved credentials. They also cover outgoing
VNC options and credential separation, hosting status, queued start/stop actions,
stable polling, preserved drafts, visible failures and worker cleanup.

Remote verification additionally needs a real RDP server: connect/reconnect,
type and drag, exchange text/images, open the shared `Home` drive, resize and
switch full screen, test available audio/microphone/printers, and disconnect.
Local/offscreen checks do not establish server interoperability.

`python tests/check-vnc-client.py` additionally exercises the actual Control
Panel VNC launch path, encrypted authentication, rendered pixels and clipboard
transfer in two private X servers. It does not use the active desktop or saved
connections.

`python tests/check-desktop-services.py /tmp/fusion-services-check-new` checks
incoming VNC/RDP authentication and video decoding in a private nested session.
Physical monitor capture and Windows RDP input/audio still need an interactive
check on the intended hardware; authentication alone does not establish those.
