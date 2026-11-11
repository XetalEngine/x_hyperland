# Fusion RDP

Open **Control Panel → RDP** (in **Network & connections**), enter the PC's
address and account, and select **Connect**. Connections are saved automatically;
**Save connection** also lets you prepare a PC without connecting. Select a saved
PC in the sidebar to reconnect or edit it. Several session windows can run at once.

This is Hyper Fusion's native Qt interface using the
[FreeRDP 3 client libraries](https://github.com/FreeRDP/FreeRDP) (3.2 or later) for the protocol.
It does not launch Remmina or an external FreeRDP window. The destination PC
needs an enabled RDP server; this page is a client, not an incoming desktop server.

## Defaults and controls

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

## Saved connections and passwords

PC settings live in `control_panel/state/rdp/connections.json` under the installed
Hyprland configuration. Writes are atomic and locked, the directory is private,
and files have mode `0600`. Invalid existing JSON is preserved rather than reset.
This state directory is already excluded from source control and preserved by
Hyper Fusion updates.

Passwords go through `secret-tool` to the desktop's Secret Service wallet
(GNOME Keyring on the default install). They are passed through standard input,
never placed in profiles, process arguments, or application error messages.
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
they do not contact a PC or alter saved credentials.

Remote verification additionally needs a real RDP server: connect/reconnect,
type and drag, exchange text/images, open the shared `Home` drive, resize and
switch full screen, test available audio/microphone/printers, and disconnect.
Local/offscreen checks do not establish server interoperability.
