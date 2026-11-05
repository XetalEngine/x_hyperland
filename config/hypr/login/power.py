"""Non-blocking logind power controls for the dedicated sign-in session."""
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher, QDBusPendingReply


ACTIONS = {'reboot': ('Reboot', 'Restart'), 'poweroff': ('PowerOff', 'Shut down')}


class Power(QObject):
    changed = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, parent=None, *, preview=False, bus=None):
        super().__init__(parent)
        self.preview, self.bus = preview, bus
        self.available = {name: 'unknown' for name in ACTIONS}
        self.busy = False
        self.refreshing = False
        self.pending = set()

    def call(self, method, arguments, callback):
        if self.bus is None:
            self.bus = QDBusConnection.systemBus()
        message = QDBusMessage.createMethodCall('org.freedesktop.login1',
            '/org/freedesktop/login1', 'org.freedesktop.login1.Manager', method)
        message.setArguments(arguments)
        watcher = QDBusPendingCallWatcher(self.bus.asyncCall(message, 5000), self)
        self.pending.add(watcher)

        def finished():
            if watcher not in self.pending:
                return
            reply = QDBusPendingReply(watcher).reply()
            self.pending.remove(watcher)
            watcher.deleteLater()
            callback(reply)

        watcher.finished.connect(finished)
        # A disconnected bus can return an already-completed error.
        if watcher.isFinished():
            QTimer.singleShot(0, finished)

    def refresh(self):
        if self.preview:
            self.available = {name: 'yes' for name in ACTIONS}
            self.changed.emit()
            return
        if self.refreshing or self.busy:
            return
        self.refreshing = True
        remaining = set(ACTIONS)

        def completed(action, reply):
            values = reply.arguments()
            self.available[action] = values[0] if reply.type() == QDBusMessage.MessageType.ReplyMessage and values and values[0] in ('yes', 'no', 'challenge', 'na') else 'unavailable'
            remaining.remove(action)
            self.refreshing = bool(remaining)
            self.changed.emit()

        for action, (method, _) in ACTIONS.items():
            self.call('Can'+method, [], lambda reply, action=action: completed(action, reply))

    def reason(self, action):
        return {'yes': '', 'unknown': 'Checking availability…',
                'challenge': 'Sign in to use this power action.',
                'no': 'This action is not allowed at the sign-in screen.',
                'na': 'This action is not supported on this computer.',
                'unavailable': 'The computer’s power service is unavailable.'}.get(self.available.get(action), '')

    def request(self, action):
        if action not in ACTIONS or self.busy:
            return
        if self.preview:
            self.message.emit('Preview only. The computer will not restart or shut down.')
            return
        if self.available[action] != 'yes':
            self.message.emit(self.reason(action))
            return
        self.busy = True
        self.changed.emit()
        self.message.emit('Restarting…' if action == 'reboot' else 'Shutting down…')

        def completed(reply):
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                self.busy = False
                self.changed.emit()
                self.message.emit('Could not '+ACTIONS[action][1].lower()+'. Another session or application may be preventing it. You can sign in and try again.')
                self.refresh()
            # logind owns the transition. Do not exit the greeter or kill sessions.

        # Non-interactive: no password prompt on an unauthenticated greeter, no
        # force flags and no bypass of other sessions or shutdown inhibitors.
        self.call(ACTIONS[action][0], [False], completed)
