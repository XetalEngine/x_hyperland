#include "ram_cleaner.h"
#include <QtTest>
#include <QtWidgets>

class RamCleanerTests final : public QObject {
  Q_OBJECT
private slots:
  void manualCleanup_data() {
    QTest::addColumn<QString>("mode");
    QTest::addColumn<int>("exitCode");
    QTest::newRow("normal") << QString("normal") << 0;
    QTest::newRow("aggressive") << QString("aggressive") << 0;
    QTest::newRow("cancelled") << QString("normal") << 126;
    QTest::newRow("failed") << QString("aggressive") << 1;
  }
  void manualCleanup() {
    QFETCH(QString, mode);
    QFETCH(int, exitCode);
    QTemporaryDir fixture;
    QFile helper(fixture.filePath("helper.py"));
    QVERIFY(helper.open(QIODevice::WriteOnly));
    helper.write(R"PY(import json, sys, time
from pathlib import Path
root = Path(__file__).parent
data = dict(total=16*1024**3, available=8*1024**3, free=1024**3,
            file_cache=4*1024**3, metadata_cache=1024**3, swap_total=0, swap_used=0)
if sys.argv[1] == 'status':
    print(json.dumps(data))
else:
    with (root/'calls').open('a') as log: log.write(sys.argv[2]+'\n')
    print(json.dumps(dict(stage='sync')), flush=True)
    time.sleep(.15)
    code = int((root/'exit-code').read_text())
    if code == 0:
        after = dict(data, available=7*1024**3, file_cache=1024**3)
        print(json.dumps(dict(ok=True, mode=sys.argv[2], before=data, after=after)), flush=True)
    elif code == 1:
        print(json.dumps(dict(error='Fixture denied cleanup')), flush=True)
    sys.exit(code)
)PY");
    helper.close();
    QFile code(fixture.filePath("exit-code"));
    QVERIFY(code.open(QIODevice::WriteOnly));
    code.write(QByteArray::number(exitCode));
    code.close();
    RamCleaner page(helper.fileName());
    page.resize(900, 760);
    page.show();
    auto *normal = page.findChild<QRadioButton *>("ramNormal");
    auto *aggressive = page.findChild<QRadioButton *>("ramAggressive");
    auto *button = page.findChild<QPushButton *>("ramCleanButton");
    auto *status = page.findChild<QLabel *>("ramStatus");
    auto *result = page.findChild<QLabel *>("ramResult");
    QVERIFY(normal && aggressive && button && status && result);
    QVERIFY(normal->isChecked());
    QTRY_COMPARE(page.findChild<QLabel *>("ramAvailable")->text(), QString("8.0 GiB"));
    QVERIFY(!QFile::exists(fixture.filePath("calls")));
    aggressive->setChecked(mode == "aggressive");
    QVERIFY(!QFile::exists(fixture.filePath("calls")));
    button->click();
    QVERIFY(!button->isEnabled());
    QVERIFY(!normal->isEnabled());
    QTRY_VERIFY_WITH_TIMEOUT(button->isEnabled(), 5000);
    QFile calls(fixture.filePath("calls"));
    QVERIFY(calls.open(QIODevice::ReadOnly));
    QCOMPARE(calls.readAll(), mode.toUtf8() + '\n');
    if (!exitCode) {
      QVERIFY(result->isVisible());
      QVERIFY(result->text().contains("−1.0 GiB"));
      QVERIFY(status->text().contains("complete"));
    } else {
      QVERIFY(!result->isVisible());
      QVERIFY(status->text().contains(exitCode == 126 ? "cancelled" : "Fixture denied cleanup"));
    }
    // A completed operation does not turn periodic statistics into auto-clean.
    QTest::qWait(2700);
    calls.seek(0);
    QCOMPARE(calls.readAll(), mode.toUtf8() + '\n');
  }
};
QTEST_MAIN(RamCleanerTests)
#include "ram_cleaner_tests.moc"
