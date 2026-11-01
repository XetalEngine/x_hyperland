#include "grub_editor.h"
#include <QtTest>
#include <QtWidgets>

class GrubEditorTests final : public QObject {
  Q_OBJECT
private slots:
  void driveToBootEntry() {
    QTemporaryDir fixture;
    QFile helper(fixture.filePath("helper.py"));
    QVERIFY(helper.open(QIODevice::WriteOnly));
    helper.write(R"PY(import json,sys,time
from pathlib import Path
root=Path(__file__).parent
drive=dict(path='/dev/fixture',token='disk-token',size=1000000000000,model='Test SSD',serial='fixture-serial')
state=dict(supported=True,mode='uefi',secure_boot=False,drives=[drive],entries=[],revision='original',can_undo=False)
def emit(v): print(json.dumps(v),flush=True)
if sys.argv[1]=='status': emit(state)
else:
    for line in sys.stdin:
        request=json.loads(line)
        with (root/'calls').open('a') as log: log.write(line)
        emit(dict(progress='Inspecting test drive'))
        time.sleep(.1)
        if request['action']=='scan':
            systems=[dict(id='windows',title='Windows Boot Manager',available=True,drive='/dev/fixture',drive_token='disk-token',loader_hash='loader-verified',loader='/EFI/Microsoft/Boot/bootmgfw.efi'),
                     dict(id='linux',title='Linux test system',available=True,drive='/dev/fixture',drive_token='disk-token',loader_hash='linux-verified',loader='/EFI/Linux/grubx64.efi')]
            emit(dict(result=dict(state,candidates=systems,notes=[])))
        elif request['action']=='add':
            state.update(entries=[dict(id=request['candidate'],name=request['name'],title='Linux test system',drive='/dev/fixture')],revision='saved',can_undo=True,message='Saved. Your boot menu is ready for the next restart.')
            emit(dict(result=state))
        else: emit(dict(error='Fixture error kept your boot menu unchanged.'))
)PY");
    helper.close();
    GrubEditor page(helper.fileName()); page.resize(1000, 850); page.show();
    auto *drives = page.findChild<QComboBox *>("grubDrives");
    auto *systems = page.findChild<QListWidget *>("grubSystems");
    auto *name = page.findChild<QLineEdit *>("grubName");
    auto *add = page.findChild<QPushButton *>("grubAdd");
    auto *entries = page.findChild<QListWidget *>("grubEntries");
    auto *status = page.findChild<QLabel *>("grubStatus");
    QTRY_COMPARE(drives->count(), 2);
    QVERIFY(!QFile::exists(fixture.filePath("calls"))); // Browsing never authenticates or writes.
    QVERIFY(!add->isEnabled());
    drives->setCurrentIndex(1);
    QTRY_COMPARE(systems->count(), 2);
    QTRY_VERIFY(add->isEnabled());
    QCOMPARE(name->text(), QString("Windows Boot Manager"));
    systems->setCurrentRow(1); QCOMPARE(name->text(), QString("Linux test system"));
    name->setText("My Linux drive"); add->click();
    QVERIFY(!add->isEnabled()); QVERIFY(!drives->isEnabled());
    QTRY_COMPARE(entries->count(), 1);
    QCOMPARE(entries->item(0)->text(), QString("My Linux drive"));
    QTRY_VERIFY(drives->isEnabled());
    QVERIFY(status->text().startsWith("Saved."));
    QFile calls(fixture.filePath("calls")); QVERIFY(calls.open(QIODevice::ReadOnly));
    const auto lines = calls.readAll().trimmed().split('\n'); QCOMPARE(lines.size(), 2);
    const auto request = QJsonDocument::fromJson(lines[1]).object();
    QCOMPARE(request["action"].toString(), QString("add"));
    QCOMPARE(request["candidate"].toString(), QString("linux"));
    QCOMPARE(request["name"].toString(), QString("My Linux drive"));
    QCOMPARE(request["revision"].toString(), QString("original"));
    QVERIFY(!request.contains("partition")); QVERIFY(!request.contains("command"));
    if (qEnvironmentVariableIsSet("FUSION_GRUB_TEST_SCREENSHOT"))
      QVERIFY(page.grab().save(qEnvironmentVariable("FUSION_GRUB_TEST_SCREENSHOT")));
    auto *undo = page.findChild<QPushButton *>("grubUndo"); QVERIFY(undo->isEnabled());
    page.findChild<QPushButton *>("grubLoad")->click();
    QTRY_VERIFY(status->text().contains("Fixture error"));
    QVERIFY(drives->isEnabled()); QCOMPARE(entries->count(), 1);
  }
  void cancelledAuthentication() {
    QTemporaryDir fixture;
    QFile helper(fixture.filePath("helper.py")); QVERIFY(helper.open(QIODevice::WriteOnly));
    helper.write("import sys,json\nif sys.argv[1]=='status': print(json.dumps(dict(supported=True,drives=[dict(path='/dev/fake',model='Fixture',token='x',size=1000000000)],entries=[])))\nelse: sys.exit(126)\n");
    helper.close();
    GrubEditor page(helper.fileName()); page.show();
    auto *drives = page.findChild<QComboBox *>("grubDrives"); QTRY_COMPARE(drives->count(), 2);
    drives->setCurrentIndex(1);
    QTRY_VERIFY(page.findChild<QLabel *>("grubStatus")->text().contains("cancelled"));
    QVERIFY(!page.findChild<QPushButton *>("grubAdd")->isEnabled()); QVERIFY(drives->isEnabled());
  }
};
QTEST_MAIN(GrubEditorTests)
#include "grub_editor_tests.moc"
