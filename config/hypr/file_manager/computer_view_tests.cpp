#include "window.h"
#include "computer_views.h"
#include <KDirLister>
#include <QtTest>

class ComputerViewTests : public QObject {
  Q_OBJECT
  QTemporaryDir temporary;
  const QStringList modes{"tiles", "list", "original", "winme", "win7", "win10", "win11"};
  const QStringList buttons{"computerShelfView", "computerListView", "computerOriginalView", "computerWinMEView", "computerWin7View", "computerWin10View", "computerWin11View"};
  static QList<Volume> inventory() {
    auto volumes = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/main","type":"disk","model":"Samsung SSD 970 EVO Plus 2TB","size":2000000000000,"children":[
        {"path":"/dev/main1","type":"part","fstype":"ext4","label":"HyperFusion","size":1990000000000,"mountpoints":["/"]},
        {"path":"/dev/main2","type":"part","fstype":"vfat","label":"FUSION_EFI","size":512000000,"mountpoints":["/boot/efi"]}]},
      {"path":"/dev/backup","type":"disk","model":"SATA SSD","fstype":"ntfs","label":"Windows_10_SATA","size":1000000000000},
      {"path":"/dev/locked","type":"disk","model":"Samsung SSD 980 PRO","fstype":"BitLocker","label":"Encrypted backups","size":1000000000000},
      {"path":"/dev/usb","type":"disk","model":"USB DISK 3.0","tran":"usb","fstype":"exfat","label":"Ventoy","size":16000000000},
      {"path":"/dev/sr0","type":"rom","model":"DVDRAM_GSA-T50N","tran":"sata","rm":1,"fstype":"iso9660","label":"Beg_C++_GP","size":23288832},
      {"path":"/dev/projects","type":"disk","model":"Portable SSD","fstype":"ext4","label":"Projects","size":500000000000,"mountpoints":["/media/projects"]}
    ]})");
    for (auto &volume : volumes) if (volume.mounted()) {
      volume.total = volume.size; volume.available = volume.size * .55; volume.freeBytes = volume.available; volume.spaceKnown = true;
    }
    Volume prefix; prefix.device = prefix.mount = "/home/player/prefixes/X_Default/pfx/drive_c";
    prefix.type = "wine-prefix"; prefix.name = "X_Default (C:)"; volumes << prefix;
    return volumes;
  }
  static QWidget *visibleDrive(DriveShelf &shelf, const QString &device) {
    for (auto *widget : shelf.findChildren<QWidget *>())
      if ((widget->objectName() == "volumeCard" || widget->objectName() == "windowsComputerItem")
          && widget->property("device").toString() == device && widget->isVisible()) return widget;
    return nullptr;
  }
private slots:
  void initTestCase() { QVERIFY(temporary.isValid()); qApp->setQuitOnLastWindowClosed(false); }
  void everyViewKeepsSelectionActionsAndFiltering_data() {
    QTest::addColumn<QString>("mode");
    for (const auto &mode : modes) QTest::newRow(qPrintable(mode)) << mode;
  }
  void everyViewKeepsSelectionActionsAndFiltering() {
    QFETCH(QString, mode);
    Fusion::Preferences prefs(temporary.path() + '/' + mode + ".ini"); prefs.settings.setValue("computer/viewMode", mode);
    Drives drives(nullptr, false); drives.volumes = inventory();
    DriveShelf shelf(&prefs, &drives); shelf.resize(1200, 950); shelf.show(); shelf.activateWindow();
    auto *toggle = shelf.findChild<QCheckBox *>("showUnmountedDrives"); QVERIFY(toggle->isChecked());
    QVERIFY(shelf.findChild<QToolButton *>(buttons[modes.indexOf(mode)])->isChecked());
    QSignalSpy operations(&shelf, &DriveShelf::operationRequested), context(&shelf, &DriveShelf::volumeContextRequested), selection(&shelf, &DriveShelf::selectionChanged);
    QTRY_VERIFY(visibleDrive(shelf, "/dev/backup"));
    auto *drive = visibleDrive(shelf, "/dev/backup"); QTest::mouseClick(drive, Qt::LeftButton);
    QCOMPARE(shelf.selectedVolume().device, QString("/dev/backup")); QVERIFY(!selection.isEmpty());
    emit drive->customContextMenuRequested(drive->rect().center());
    QCOMPARE(context.size(), 1); QCOMPARE(context[0][0].value<Volume>().device, QString("/dev/backup"));
    QTest::keyClick(drive, Qt::Key_Return); QCOMPARE(operations.size(), 1); QCOMPARE(operations[0][1].toString(), QString("open"));
    toggle->click(); QTRY_VERIFY(!visibleDrive(shelf, "/dev/backup"));
    QVERIFY(shelf.selectedVolume().device.isEmpty());
    QVERIFY(visibleDrive(shelf, "/dev/main1")); QVERIFY(visibleDrive(shelf, "/dev/usb")); QVERIFY(visibleDrive(shelf, "/dev/sr0"));
    QVERIFY(visibleDrive(shelf, "/home/player/prefixes/X_Default/pfx/drive_c"));
    for (auto &volume : drives.volumes) if (volume.device == "/dev/backup") volume.mount = "/media/backups";
    shelf.refresh(); QTRY_VERIFY(visibleDrive(shelf, "/dev/backup"));
    shelf.selectDevice("/dev/backup", true); auto *same = visibleDrive(shelf, "/dev/backup");
    std::reverse(drives.volumes.begin(), drives.volumes.end()); shelf.refresh(); QCoreApplication::processEvents();
    QCOMPARE(visibleDrive(shelf, "/dev/backup"), same); QCOMPARE(shelf.selectedVolume().mount, QString("/media/backups"));
    for (auto &volume : drives.volumes) if (volume.device == "/dev/backup") volume.mount.clear();
    shelf.refresh(); QTRY_VERIFY(!visibleDrive(shelf, "/dev/backup")); QVERIFY(shelf.selectedVolume().device.isEmpty());
    shelf.selectDevice("/dev/usb", true);
    drives.volumes.erase(std::remove_if(drives.volumes.begin(), drives.volumes.end(), [](const Volume &v) { return v.device == "/dev/usb"; }), drives.volumes.end());
    shelf.refresh(); QVERIFY(shelf.selectedVolume().device.isEmpty());
    QCOMPARE(operations.size(), 1); // Selection, filtering, refresh and layout do not mount.
  }
  void preferencesAndFreshDefaults() {
    const auto path = temporary.path() + "/saved.ini";
    {
      Fusion::Preferences prefs(path); Drives drives(nullptr, false); drives.volumes = inventory(); DriveShelf shelf(&prefs, &drives); shelf.show();
      QVERIFY(shelf.findChild<QToolButton *>("computerShelfView")->isChecked());
      QVERIFY(shelf.findChild<QCheckBox *>("showUnmountedDrives")->isChecked());
      shelf.findChild<QToolButton *>("computerWin11View")->click(); shelf.findChild<QCheckBox *>("showUnmountedDrives")->click(); prefs.settings.sync();
    }
    Fusion::Preferences prefs(path); Drives drives(nullptr, false); drives.volumes = inventory(); DriveShelf shelf(&prefs, &drives); shelf.show();
    QVERIFY(shelf.findChild<QToolButton *>("computerWin11View")->isChecked());
    QVERIFY(!shelf.findChild<QCheckBox *>("showUnmountedDrives")->isChecked());
    QTRY_VERIFY(!visibleDrive(shelf, "/dev/backup"));
    for (int i = 0; i < buttons.size(); ++i) {
      shelf.findChild<QToolButton *>(buttons[i])->click();
      QCOMPARE(prefs.settings.value("computer/viewMode").toString(), modes[i]);
      QTRY_VERIFY(!visibleDrive(shelf, "/dev/backup"));
      QVERIFY(visibleDrive(shelf, "/dev/main1"));
    }
  }
  void windowsFoldersAndControlPanelHaveRealTargets() {
    Fusion::Preferences prefs(temporary.path() + "/links.ini"); prefs.settings.setValue("computer/viewMode", "win10");
    prefs.setPlaces({{{"name", "Studio share"}, {"url", "smb://studio.example/shared"}}});
    Drives drives(nullptr, false); drives.volumes = inventory(); DriveShelf shelf(&prefs, &drives); shelf.resize(1100, 950); shelf.show();
    QSignalSpy locations(&shelf, &DriveShelf::locationRequested), panel(&shelf, &DriveShelf::controlPanelRequested);
    auto *view = shelf.findChild<WindowsComputerView *>();
    for (auto *item : view->findChildren<QAbstractButton *>("windowsComputerItem")) {
      const auto location = item->property("location").toUrl();
      if (location == QUrl::fromLocalFile(QDir::homePath()) || location.scheme() == "smb") {
        QTest::mouseDClick(item, Qt::LeftButton); QCOMPARE(locations.last()[0].toUrl(), location);
        QVERIFY(shelf.selectedVolume().device.isEmpty());
      }
    }
    QCOMPARE(locations.size(), 2);
    shelf.findChild<QToolButton *>("computerWinMEView")->click();
    for (auto *item : view->findChildren<QAbstractButton *>("windowsComputerItem"))
      if (item->accessibleName() == "Control Panel") QTest::mouseDClick(item, Qt::LeftButton);
    QCOMPARE(panel.size(), 1);
  }
  void emptyFilteredViewExplainsHowToRevealDrives() {
    Fusion::Preferences prefs(temporary.path() + "/empty.ini"); prefs.settings.setValue("computer/viewMode", "win7");
    Drives drives(nullptr, false); drives.volumes = {inventory()[2]};
    DriveShelf shelf(&prefs, &drives); shelf.resize(700, 500); shelf.show();
    auto *empty = shelf.findChild<QLabel *>("explorerEmpty");
    QVERIFY(!empty->isVisible());
    shelf.findChild<QCheckBox *>("showUnmountedDrives")->click(); QTRY_VERIFY(empty->isVisible());
    shelf.findChild<QCheckBox *>("showUnmountedDrives")->click(); QTRY_VERIFY(!empty->isVisible());
    drives.volumes.clear(); shelf.refresh(); QVERIFY(empty->isVisible());
  }
  void windowsViewsKeepPreviewAndFitSmallWindows() {
    FilesWindow window(Fusion::computerUrl(), false, temporary.path() + "/window.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.resize(1600, 900); window.show();
    window.drives->volumes = inventory(); emit window.drives->changed();
    if (!window.browser()->previewVisible) window.runAction("preview");
    auto *shelf = window.browser()->findChild<DriveShelf *>();
    auto *pane = shelf->findChild<WindowsComputerView *>();
    QTest::qWait(450); const auto palette = qApp->palette();
    const auto artifacts = qEnvironmentVariable("FUSION_FILES_ARTIFACTS");
    for (int i = 3; i < modes.size(); ++i) {
      shelf->findChild<QToolButton *>(buttons[i])->click(); shelf->selectDevice("/dev/main1");
      QTRY_COMPARE(window.findChild<QLabel *>("drivePreviewName")->text(), QString("HyperFusion"));
      QCOMPARE(window.findChild<QStackedWidget *>("previewStack")->currentWidget()->objectName(), QString("drivePreview"));
      QCOMPARE(qApp->palette(), palette);
      QTest::qWait(60);
      if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/this-pc-" + modes[i] + ".png"));
      for (const auto size : {QSize(1000, 720), QSize(760, 600), QSize(1600, 900)}) {
        window.resize(size); QTest::qWait(25); QCOMPARE(window.size(), size);
        QCOMPARE(pane->horizontalScrollBar()->maximum(), 0);
        for (auto *button : shelf->findChild<QWidget *>("computerViewButtons")->findChildren<QToolButton *>())
          QVERIFY(shelf->rect().contains(QRect(button->mapTo(shelf, QPoint()), button->size())));
      }
    }
    shelf->findChild<QToolButton *>("computerShelfView")->click();
    shelf->findChild<QCheckBox *>("showUnmountedDrives")->click(); QTest::qWait(60);
    if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/this-pc-filtered.png"));
    QVERIFY(!visibleDrive(*shelf, "/dev/backup"));
    window.close();
  }
};
QTEST_MAIN(ComputerViewTests)
#include "computer_view_tests.moc"
