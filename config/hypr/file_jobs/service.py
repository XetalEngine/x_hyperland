"""KDE JobView protocols used by Dolphin, Ark and other KIO clients.

Protocol references: KDE/kjobwidgets kuiserver[v2]jobtracker.cpp and the
installed kf6_org.kde.JobView[Server,V2].xml interfaces. No KDE service is replaced.
"""
from PyQt6.QtCore import QObject, QTimer, pyqtClassInfo, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection, QDBusMessage, QDBusObjectPath, QDBusVariant
try:
    from .model import Job
except ImportError:
    from model import Job

NAMES = ('org.kde.JobViewServer', 'org.kde.kuiserver')
ROOT = '/JobViewServer'


class Guarded(QDBusAbstractAdaptor):
    def accepted(self, message):
        if message.service() == self.parent().owner:
            return True
        message.setDelayedReply(True)
        self.parent().service.bus.send(message.createErrorReply(
            'org.freedesktop.DBus.Error.AccessDenied', 'This job belongs to another application.'))
        return False


@pyqtClassInfo('D-Bus Interface', 'org.kde.JobViewV3')
class ViewV3(Guarded):
    cancelRequested = pyqtSignal()
    suspendRequested = pyqtSignal()
    resumeRequested = pyqtSignal()

    @pyqtSlot('QVariantMap', QDBusMessage)
    def update(self, properties, message):
        if self.accepted(message): self.parent().update(properties)

    @pyqtSlot('uint', str, 'QVariantMap', QDBusMessage)
    def terminate(self, code, text, hints, message):
        if self.accepted(message): self.parent().terminate(code, text)


@pyqtClassInfo('D-Bus Interface', 'org.kde.JobViewV2')
class ViewV2(Guarded):
    cancelRequested = pyqtSignal()
    suspendRequested = pyqtSignal()
    resumeRequested = pyqtSignal()

    def change(self, message, values):
        if self.accepted(message): self.parent().update(values)

    @pyqtSlot(str, QDBusMessage)
    def terminate(self, text, message):
        if self.accepted(message):
            self.parent().terminate(self.parent().data.get('errorCode', 2 if text else 0), text)

    @pyqtSlot(bool, QDBusMessage)
    def setSuspended(self, value, message): self.change(message, {'suspended': value})

    @pyqtSlot('qulonglong', str, QDBusMessage)
    def setTotalAmount(self, value, unit, message):
        if unit in ('bytes', 'files', 'directories', 'items'): self.change(message, {'total' + unit.title(): value})

    @pyqtSlot('qulonglong', str, QDBusMessage)
    def setProcessedAmount(self, value, unit, message):
        if unit in ('bytes', 'files', 'directories', 'items'): self.change(message, {'processed' + unit.title(): value})

    @pyqtSlot('uint', QDBusMessage)
    def setPercent(self, value, message): self.change(message, {'percent': value})

    @pyqtSlot('qulonglong', QDBusMessage)
    def setSpeed(self, value, message): self.change(message, {'speed': value})

    @pyqtSlot('qulonglong', QDBusMessage)
    def setElapsedTime(self, value, message): self.change(message, {'elapsedTime': value})

    @pyqtSlot(str, QDBusMessage)
    def setInfoMessage(self, value, message): self.change(message, {'title': value})

    @pyqtSlot('uint', str, str, QDBusMessage, result=bool)
    def setDescriptionField(self, number, name, value, message):
        if not self.accepted(message) or number > 1: return False
        self.parent().update({f'descriptionLabel{number+1}': name, f'descriptionValue{number+1}': value})
        return True

    @pyqtSlot('uint', QDBusMessage)
    def clearDescriptionField(self, number, message):
        if number < 2: self.change(message, {f'descriptionLabel{number+1}': '', f'descriptionValue{number+1}': ''})

    @pyqtSlot(QDBusVariant, QDBusMessage)
    def setDestUrl(self, value, message): self.change(message, {'destUrl': str(value.variant())})

    @pyqtSlot('uint', QDBusMessage)
    def setError(self, value, message): self.change(message, {'errorCode': value})


@pyqtClassInfo('D-Bus Interface', 'org.kde.JobViewServerV2')
class ServerV2(QDBusAbstractAdaptor):
    @pyqtSlot(str, int, 'QVariantMap', QDBusMessage, result=QDBusObjectPath)
    def requestView(self, application, capabilities, hints, message):
        return self.parent().create(message.service(), application, capabilities, hints, 'org.kde.JobViewV3')


@pyqtClassInfo('D-Bus Interface', 'org.kde.JobViewServer')
class ServerV1(QDBusAbstractAdaptor):
    @pyqtSlot(str, str, int, QDBusMessage, result=QDBusObjectPath)
    def requestView(self, application, icon, capabilities, message):
        return self.parent().create(message.service(), application, capabilities, {}, 'org.kde.JobViewV2')


@pyqtClassInfo('D-Bus Interface', 'org.kde.kuiserver')
class Tracker(QDBusAbstractAdaptor):
    requiresJobTrackerChanged = pyqtSignal(bool)

    @pyqtSlot(result=bool)
    def requiresJobTracker(self): return False


class Service(QObject):
    created = pyqtSignal(object)

    def __init__(self, bus=None, parent=None):
        super().__init__(parent)
        self.bus = bus or QDBusConnection.sessionBus()
        self.jobs = {}
        self.serial = 0
        self.names = []
        self.adaptors = [ServerV2(self), ServerV1(self), Tracker(self)]

    def start(self):
        if not self.bus.isConnected(): raise RuntimeError('The session bus is not available.')
        for name in NAMES:
            if self.bus.interface().isServiceRegistered(name).value():
                raise RuntimeError('An existing file-job service is already running; leaving it in charge.')
        if not self.bus.registerObject(ROOT, self, QDBusConnection.RegisterOption.ExportAdaptors):
            raise RuntimeError(self.bus.lastError().message())
        for name in NAMES:
            if not self.bus.registerService(name):
                self.stop()
                raise RuntimeError('Another file-job service started first; leaving it in charge.')
            self.names.append(name)
        self.bus.connect('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                         'NameOwnerChanged', self.owner_changed)

    def create(self, owner, application, capabilities, hints, interface):
        self.serial += 1
        path = ROOT + '/job' + str(self.serial)
        job = Job(path, owner, application, capabilities, hints, self)
        job.service, job.interface = self, interface
        job.adaptors = [ViewV3(job), ViewV2(job)]
        if not self.bus.registerObject(path, job, QDBusConnection.RegisterOption.ExportAdaptors):
            job.deleteLater()
            return QDBusObjectPath('/')
        self.jobs[path] = job
        job.requested.connect(lambda action: self.request(job, action))
        # Return the DBus object before a very fast operation can finish its UI.
        QTimer.singleShot(0, lambda: self.created.emit(job) if path in self.jobs else None)
        return QDBusObjectPath(path)

    def request(self, job, action):
        signal = QDBusMessage.createTargetedSignal(job.owner, job.path, job.interface, action + 'Requested')
        self.bus.send(signal)

    @pyqtSlot(str, str, str)
    def owner_changed(self, name, previous, current):
        if previous and not current:
            for job in list(self.jobs.values()):
                if job.owner == name and job.result is None: job.disconnected()

    def release(self, job):
        if self.jobs.pop(job.path, None) is not None:
            self.bus.unregisterObject(job.path)
            job.deleteLater()

    def stop(self):
        # Ending the desktop releases the UI. It never sends Cancel to jobs.
        for name in self.names: self.bus.unregisterService(name)
        self.names.clear()
        self.bus.unregisterObject(ROOT, QDBusConnection.UnregisterMode.UnregisterTree)
