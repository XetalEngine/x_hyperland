#include "runtime_log_guard.h"
#include <QtTest>
#include <QtWidgets>

class RuntimeLogGuardTests final : public QObject {
  Q_OBJECT
private slots:
  void controlsAndFailureRecovery() {
    QTemporaryDir directory;
    QFile helper(directory.filePath("helper.py")); QVERIFY(helper.open(QIODevice::WriteOnly));
    helper.write(R"PY(import json,sys
from pathlib import Path
root=Path(__file__).parent
setting=root/'enabled'
action=sys.argv[1]
if action=='--disable': setting.write_text('no')
if action=='--enable': setting.write_text('yes')
state=dict(enabled=not setting.exists() or setting.read_text()=='yes',active=True,running=True,used=4096,runtime_free=1024**3)
if action=='--once':
    if (root/'fail').exists(): print(json.dumps(dict(error='Fixture failure')));sys.exit(1)
    state['checked']=dict(cleared=['hyprland.log'],freed=100*1024**2,errors=[])
print(json.dumps(state))
)PY");
    helper.close();
    RuntimeLogGuard widget(helper.fileName()); widget.resize(1000, 220); widget.show();
    auto *enabled = widget.findChild<QCheckBox *>("logGuardEnabled");
    auto *check = widget.findChild<QPushButton *>("logGuardCheck");
    auto *status = widget.findChild<QLabel *>("logGuardStatus");
    auto *message = widget.findChild<QLabel *>("logGuardMessage");
    QTRY_VERIFY(enabled->isEnabled()); QVERIFY(enabled->isChecked());
    QVERIFY(status->text().contains("Protecting"));
    enabled->click(); QTRY_VERIFY(enabled->isEnabled());
    QVERIFY(!enabled->isChecked()); QVERIFY(status->text().startsWith("Paused"));
    enabled->click(); QTRY_VERIFY(enabled->isEnabled()); QVERIFY(enabled->isChecked());
    check->click(); QTRY_VERIFY(check->isEnabled());
    QVERIFY(message->text().contains("100.0 MiB"));
    QFile failure(directory.filePath("fail")); QVERIFY(failure.open(QIODevice::WriteOnly)); failure.close();
    check->click(); QTRY_VERIFY(check->isEnabled());
    QCOMPARE(message->text(), QString("Fixture failure")); QVERIFY(enabled->isChecked());
  }
};
QTEST_MAIN(RuntimeLogGuardTests)
#include "runtime_log_guard_tests.moc"
