"""Publish archive jobs through the existing, session-owned transfer UI."""
from PyQt6.QtCore import QObject, QMetaType, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import (QDBus, QDBusArgument, QDBusConnection, QDBusMessage,
                         QDBusPendingCallWatcher, QDBusPendingReply, QDBusServiceWatcher)


class RemoteProgress(QObject):
    lost = pyqtSignal()
    ready = pyqtSignal(bool)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job=job;self.bus=QDBusConnection.sessionBus();self.path='';self.owner='';self.finished=False;self.validated=False
        self.rows={};self.state={};self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(80)
        self.timer.timeout.connect(self.flush)
        self.job.changed.connect(lambda:self.timer.start() if not self.timer.isActive() else None)
        self.job.queue_changed.connect(self.queue)
        self.job.finished.connect(self.terminate)
        self.probing=True
        self.watch=QDBusServiceWatcher('org.kde.JobViewServer',self.bus,QDBusServiceWatcher.WatchModeFlag.WatchForUnregistration,self)
        self.watch.serviceUnregistered.connect(self.disconnected)
        if not self.bus.isConnected():QTimer.singleShot(0,lambda:self.ready.emit(False));self.probing=False;return
        interface=self.bus.interface()
        owner=interface.serviceOwner('org.kde.JobViewServer')
        if not owner.isValid():QTimer.singleShot(0,lambda:self.ready.emit(False));self.probing=False;return
        self.owner=owner.value()
        message=QDBusMessage.createMethodCall(self.owner,'/JobViewServer','org.kde.JobViewServerV2','requestView')
        message.setArguments(['xetal-archives',3,self.job.data])
        watcher=QDBusPendingCallWatcher(self.bus.asyncCall(message,2500),self)
        watcher.finished.connect(self.registered)

    def registered(self,watcher):
        reply=QDBusPendingReply(watcher).reply();watcher.deleteLater();self.probing=False
        if reply.type()==QDBusMessage.MessageType.ErrorMessage or not reply.arguments():self.ready.emit(False);return
        value=reply.arguments()[0]
        self.path=value.path() if hasattr(value,'path') else str(value)
        if not self.path.startswith('/JobViewServer/job'):
            self.path='';self.ready.emit(False);return
        message=QDBusMessage.createMethodCall(self.owner,self.path,'org.freedesktop.DBus.Introspectable','Introspect')
        watcher=QDBusPendingCallWatcher(self.bus.asyncCall(message,2500),self)
        watcher.finished.connect(self.inspected)

    def inspected(self,watcher):
        reply=QDBusPendingReply(watcher).reply();watcher.deleteLater()
        if reply.type()==QDBusMessage.MessageType.ErrorMessage or not reply.arguments() or 'org.xetal.FileTransfer1' not in str(reply.arguments()[0]):
            # A different desktop's JobView implementation cannot answer our
            # attention queue. Keep those controls in the local Fusion window.
            self.send('org.kde.JobViewV3','terminate',[QDBusArgument(0,QMetaType.Type.UInt.value),'',{}])
            self.path='';self.ready.emit(False);return
        self.validated=True
        for name,callback in [('cancelRequested',self.cancel),('suspendRequested',self.pause),('resumeRequested',self.resume)]:
            self.bus.connect(self.owner,self.path,'org.kde.JobViewV3',name,callback)
        self.bus.connect(self.owner,self.path,'org.xetal.FileTransfer1','queueDecision',self.decision)
        self.flush();self.ready.emit(True)
        if self.job.result is not None:self.terminate()

    def send(self,interface,method,arguments):
        if not self.path:return
        message=QDBusMessage.createMethodCall(self.owner,self.path,interface,method);message.setArguments(arguments)
        self.bus.call(message,QDBus.CallMode.NoBlock)

    def queue(self,rows):
        for row in rows:self.rows[row['id']]=row
        self.state.update(self.job.queue_state)
        if not self.timer.isActive():self.timer.start()

    def flush(self):
        if not self.path or not self.validated or self.finished:return
        self.send('org.kde.JobViewV3','update',[self.job.data])
        if self.rows or self.state:
            self.send('org.xetal.FileTransfer1','updateQueue',[{'rows':list(self.rows.values()),'state':self.state}])
            self.rows={};self.state={}

    def terminate(self):
        if self.finished or not self.path or not self.validated:return
        self.flush();self.finished=True
        code=0 if self.job.result=='done' else 1 if self.job.result=='canceled' else 2
        self.send('org.kde.JobViewV3','terminate',[QDBusArgument(code,QMetaType.Type.UInt.value),self.job.data.get('errorMessage',''),{}])

    @pyqtSlot()
    def cancel(self):self.job.request('cancel')
    @pyqtSlot()
    def pause(self):self.job.request('suspend')
    @pyqtSlot()
    def resume(self):self.job.request('resume')
    @pyqtSlot('QVariantMap')
    def decision(self,value):
        self.job.decide_queue(value.get('ids',[]),value.get('choice'),value.get('all',False),value.get('versions'))

    @pyqtSlot(str)
    def disconnected(self,name):
        if self.path and not self.finished:
            self.path='';self.lost.emit()
