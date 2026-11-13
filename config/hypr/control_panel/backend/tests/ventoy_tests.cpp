#include "ventoy_page.h"
#include <QtTest>
#include <QtWidgets>
#include <QJsonArray>
#include <QJsonDocument>

class VentoyTests : public QObject {
  Q_OBJECT
  QTemporaryDir fixture;
  QJsonObject usb(bool existing = false, const QString &identity = "usb-one") {
    return {{"path", "/dev/sdz"}, {"model", "Disposable test USB"}, {"size", 32. * 1024 * 1024 * 1024},
            {"serial", "TEST-ONLY"}, {"identity", identity}, {"layout", "layout-one"}, {"blocked", ""}, {"ventoy", existing}};
  }
  void inventory(const QJsonArray &disks, const QString &error = "") {
    QFile file(fixture.filePath("inventory.json")); QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(QJsonObject{{"ok", true}, {"version", "1.1.18"}, {"bundle_error", error}, {"disks", disks}}).toJson());
  }
  void select(VentoyPage &page) {
    auto *disks = page.findChild<QComboBox *>("ventoyDisks");
    QTRY_COMPARE(disks->count(), 2);
    disks->setCurrentIndex(1);
    QTRY_VERIFY(page.findChild<QPushButton *>("ventoyRefresh")->isEnabled());
  }
private slots:
  void initTestCase() {
    QVERIFY(fixture.isValid());
    QVERIFY(QDir().mkpath(fixture.filePath("control_panel")));
    QFile helper(fixture.filePath("control_panel/ventoy.py"));
    QVERIFY(helper.open(QIODevice::WriteOnly));
    helper.write(R"PY(import json, pathlib, sys, time
root = pathlib.Path(__file__).resolve().parents[1]
if sys.argv[1:] == ['status']:
    print((root / 'inventory.json').read_text())
else:
    request = json.loads(sys.stdin.readline())
    (root / 'request.json').write_text(json.dumps({'args': sys.argv[1:], 'request': request}))
    mode = (root / 'mode').read_text() if (root / 'mode').exists() else 'success'
    if mode == 'cancel': sys.exit(126)
    print(json.dumps({'stage': 'Writing fixture only…'}), flush=True)
    time.sleep(0.2)
    print(json.dumps({'ok': mode == 'success', 'message': 'Ventoy USB is ready.', 'error': 'Fixture: disk changed.' if mode != 'success' else ''}), flush=True)
)PY");
  }
  void init() {
    QFile::remove(fixture.filePath("request.json"));
    QFile::remove(fixture.filePath("mode"));
  }
  void discoveryDoesNotWriteAndInternalDisksAreAbsent() {
    inventory({});
    VentoyPage page(fixture.path()); page.show();
    auto *create = page.findChild<QPushButton *>("ventoyCreate");
    QTRY_VERIFY(page.findChild<QLabel *>("ventoyDetails")->text().contains("No USB"));
    QVERIFY(!create->isEnabled());
    QVERIFY(!page.findChild<QPushButton *>("ventoyUpdate")->isEnabled());
    QVERIFY(!QFile::exists(fixture.filePath("request.json")));
    inventory({usb()}); page.findChild<QPushButton *>("ventoyRefresh")->click();
    select(page);
    QVERIFY(create->isEnabled());
    QVERIFY(!QFile::exists(fixture.filePath("request.json")));
  }
  void replacingSelectedUsbRequiresNewSelection() {
    inventory({usb()});
    VentoyPage page(fixture.path()); page.show(); select(page);
    inventory({usb(false, "usb-replacement")});
    page.findChild<QPushButton *>("ventoyRefresh")->click();
    QTRY_COMPARE(page.findChild<QComboBox *>("ventoyDisks")->currentIndex(), 0);
    QVERIFY(!page.findChild<QPushButton *>("ventoyCreate")->isEnabled());
  }
  void protectedAndMissingBundleDisableWrites() {
    auto protectedUsb = usb(); protectedUsb["blocked"] = "Protected system disk";
    inventory({protectedUsb});
    VentoyPage page(fixture.path()); page.show(); select(page);
    QVERIFY(!page.findChild<QPushButton *>("ventoyCreate")->isEnabled());
    QVERIFY(page.findChild<QLabel *>("ventoyDetails")->text().contains("Protected system"));
    inventory({usb()}, "Archive failed verification");
    page.findChild<QPushButton *>("ventoyRefresh")->click();
    QTRY_VERIFY(page.findChild<QLabel *>("ventoyBundle")->text().contains("failed verification"));
    QVERIFY(!page.findChild<QPushButton *>("ventoyCreate")->isEnabled());
  }
  void cancelledConfirmationDoesNotStartHelper() {
    inventory({usb()});
    VentoyPage page(fixture.path()); page.show(); select(page);
    QTimer::singleShot(20, &page, [&] {
      auto *dialog = page.findChild<QDialog *>("ventoyConfirmation"); QVERIFY(dialog);
      auto *accept = dialog->findChild<QPushButton *>("ventoyConfirmAccept");
      QVERIFY(!accept->isEnabled());
      dialog->findChild<QLineEdit *>("ventoyConfirmPath")->setText("/dev/sda");
      dialog->findChild<QCheckBox *>("ventoyConfirmErase")->setChecked(true);
      QVERIFY(!accept->isEnabled());
      dialog->reject();
    });
    page.findChild<QPushButton *>("ventoyCreate")->click();
    QVERIFY(!QFile::exists(fixture.filePath("request.json")));
  }
  void confirmationAndResults_data() {
    QTest::addColumn<QString>("mode"); QTest::addColumn<bool>("existing"); QTest::addColumn<QString>("expected");
    QTest::newRow("install") << "success" << false << "USB is ready";
    QTest::newRow("update") << "success" << true << "USB is ready";
    QTest::newRow("auth-cancelled") << "cancel" << false << "cancelled";
    QTest::newRow("changed-disk") << "failure" << false << "disk changed";
  }
  void confirmationAndResults() {
    QFETCH(QString, mode); QFETCH(bool, existing); QFETCH(QString, expected);
    QFile modeFile(fixture.filePath("mode")); QVERIFY(modeFile.open(QIODevice::WriteOnly)); modeFile.write(mode.toUtf8()); modeFile.close();
    inventory({usb(existing)});
    VentoyPage page(fixture.path()); page.show(); select(page);
    QVERIFY(page.findChild<QPushButton *>("ventoyUpdate")->isEnabled() == existing);
    QVERIFY(page.findChild<QPushButton *>("ventoyCreate")->isEnabled() != existing);
    QTimer::singleShot(20, &page, [&] {
      auto *dialog = page.findChild<QDialog *>("ventoyConfirmation"); QVERIFY(dialog);
      if (!existing) {
        dialog->findChild<QLineEdit *>("ventoyConfirmPath")->setText("/dev/sdz");
        QVERIFY(!dialog->findChild<QPushButton *>("ventoyConfirmAccept")->isEnabled());
        dialog->findChild<QCheckBox *>("ventoyConfirmErase")->setChecked(true);
      }
      dialog->findChild<QPushButton *>("ventoyConfirmAccept")->click();
    });
    page.findChild<QPushButton *>(existing ? "ventoyUpdate" : "ventoyCreate")->click();
    QVERIFY(!page.findChild<QComboBox *>("ventoyDisks")->isEnabled());
    QTRY_VERIFY_WITH_TIMEOUT(page.findChild<QLabel *>("ventoyStatus")->text().contains(expected), 5000);
    QTRY_VERIFY(page.findChild<QComboBox *>("ventoyDisks")->isEnabled());
    QFile saved(fixture.filePath("request.json")); QVERIFY(saved.open(QIODevice::ReadOnly));
    auto sent = QJsonDocument::fromJson(saved.readAll()).object();
    QCOMPARE(sent["args"].toArray().last().toString(), existing ? "update" : "install");
    QCOMPARE(sent["request"].toObject()["identity"].toString(), QString("usb-one"));
    if (!existing) QCOMPARE(sent["request"].toObject()["erase_confirmed"].toString(), QString("/dev/sdz"));
    QVERIFY(!page.findChild<QPlainTextEdit *>("ventoyLog")->toPlainText().isEmpty());
  }
};
QTEST_MAIN(VentoyTests)
#include "ventoy_tests.moc"
