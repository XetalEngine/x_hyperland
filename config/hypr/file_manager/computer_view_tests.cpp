#include "window.h"
#include "computer_views.h"
#include <KDirLister>
#include <QtTest>

class ComputerViewTests : public QObject {
  Q_OBJECT
  QTemporaryDir temporary;
  const QStringList modes{"tiles", "list", "original", "winme", "win7", "win10", "win11", "winme-themed", "win7-themed", "win10-themed", "win11-themed"};
  const QStringList buttons{"computerShelfView", "computerListView", "computerOriginalView", "computerWinMEView", "computerWin7View", "computerWin10View", "computerWin11View", "computerWinMEThemedView", "computerWin7ThemedView", "computerWin10ThemedView", "computerWin11ThemedView"};
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
      QVERIFY(shelf.findChild<QToolButton *>("computerWin7ThemedView")->isChecked());
      QVERIFY(shelf.findChild<QCheckBox *>("showUnmountedDrives")->isChecked());
      QVERIFY(shelf.findChild<QWidget *>("computerViewButtons")->isVisible());
      for (const auto &name : buttons) QVERIFY(shelf.findChild<QToolButton *>(name)->isVisible());
      shelf.findChild<QToolButton *>("computerWin11ThemedView")->click(); shelf.findChild<QCheckBox *>("showUnmountedDrives")->click(); prefs.settings.sync();
    }
    Fusion::Preferences prefs(path); Drives drives(nullptr, false); drives.volumes = inventory(); DriveShelf shelf(&prefs, &drives); shelf.show();
    QVERIFY(shelf.findChild<QToolButton *>("computerWin11ThemedView")->isChecked());
    QVERIFY(!shelf.findChild<QCheckBox *>("showUnmountedDrives")->isChecked());
    QTRY_VERIFY(!visibleDrive(shelf, "/dev/backup"));
    for (int i = 0; i < buttons.size(); ++i) {
      shelf.findChild<QToolButton *>(buttons[i])->click();
      QCOMPARE(prefs.settings.value("computer/viewMode").toString(), modes[i]);
      QTRY_VERIFY(!visibleDrive(shelf, "/dev/backup"));
      QVERIFY(visibleDrive(shelf, "/dev/main1"));
    }
    for (const bool list : {false, true}) {
      Fusion::Preferences legacy(temporary.path() + (list ? "/legacy-list.ini" : "/legacy-cards.ini"));
      legacy.settings.setValue("computer/listView", list);
      DriveShelf restored(&legacy, &drives);
      QVERIFY(restored.findChild<QToolButton *>(list ? "computerListView" : "computerShelfView")->isChecked());
    }
  }
  void windowsFoldersAndControlPanelHaveRealTargets_data() {
    QTest::addColumn<bool>("themed");
    QTest::newRow("classic") << false; QTest::newRow("themed") << true;
  }
  void windowsFoldersAndControlPanelHaveRealTargets() {
    QFETCH(bool, themed);
    Fusion::Preferences prefs(temporary.path() + "/links.ini"); prefs.settings.setValue("computer/viewMode", themed ? "win10-themed" : "win10");
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
    shelf.findChild<QToolButton *>(themed ? "computerWinMEThemedView" : "computerWinMEView")->click();
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
        if (i >= 7 && size == QSize(760, 600) && !artifacts.isEmpty())
          QVERIFY(window.grab().save(artifacts + "/this-pc-" + modes[i] + "-small.png"));
      }
    }
    shelf->findChild<QToolButton *>("computerShelfView")->click();
    shelf->findChild<QCheckBox *>("showUnmountedDrives")->click(); QTest::qWait(60);
    if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/this-pc-filtered.png"));
    QVERIFY(!visibleDrive(*shelf, "/dev/backup"));
    window.close();
  }
  void viewButtonSettingSavesCancelsAndKeepsLayout() {
    const auto path = temporary.path() + "/view-buttons.ini";
    FilesWindow window(Fusion::computerUrl(), false, path);
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    QTRY_VERIFY_WITH_TIMEOUT(!window.property("fusionTheme").toString().isEmpty(), 10000);
    auto *shelf = window.browser()->findChild<DriveShelf *>();
    auto *controls = shelf->findChild<QWidget *>("computerViewButtons");
    QVERIFY(controls->isVisible());
    shelf->findChild<QToolButton *>("computerWin10ThemedView")->click();
    window.openLocation(Fusion::computerUrl(), true);
    auto configure = [&](bool visible, bool save) {
      bool found = false;
      QTimer::singleShot(0, &window, [&] {
        auto *dialog = window.findChild<QDialog *>("filesConfiguration");
        if (!dialog) return;
        dialog->findChild<QTabWidget *>("filesSettingsTabs")->setCurrentWidget(dialog->findChild<QScrollArea *>("computerSettingsScroll"));
        if (auto *toggle = dialog->findChild<QCheckBox *>("configureComputerViewButtons")) {
          found = true; toggle->setChecked(visible);
        }
        const auto artifacts = qEnvironmentVariable("FUSION_FILES_ARTIFACTS");
        if (found && !artifacts.isEmpty()) dialog->grab().save(artifacts + "/view-buttons-settings.png");
        if (found && save) dialog->accept(); else dialog->reject();
      });
      window.findChild<QAction *>("configureFiles")->trigger();
      return found;
    };
    QVERIFY(configure(false, false));
    QVERIFY(!controls->isHidden());
    QVERIFY(window.preferences.settings.value("computer/showViewButtons", true).toBool());
    QVERIFY(configure(false, true));
    QCoreApplication::processEvents();
    const auto artifacts = qEnvironmentVariable("FUSION_FILES_ARTIFACTS");
    if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/view-buttons-hidden.png"));
    for (auto *other : window.findChildren<DriveShelf *>()) {
      QVERIFY(other->findChild<QWidget *>("computerViewButtons")->isHidden());
      QVERIFY(other->findChild<QToolButton *>("computerWin10ThemedView")->isChecked());
      QVERIFY(!other->findChild<QCheckBox *>("showUnmountedDrives")->isHidden());
    }
    FilesWindow reopened(Fusion::computerUrl(), false, path);
    reopened.setAttribute(Qt::WA_DeleteOnClose, false); reopened.show();
    QVERIFY(reopened.findChild<QWidget *>("computerViewButtons")->isHidden());
    QVERIFY(reopened.findChild<QToolButton *>("computerWin10ThemedView")->isChecked());
    reopened.close();
    QVERIFY(configure(true, true));
    for (auto *other : window.findChildren<DriveShelf *>())
      QVERIFY(!other->findChild<QWidget *>("computerViewButtons")->isHidden());
    QCOMPARE(window.preferences.settings.value("computer/viewMode").toString(), QString("win10-themed"));
    window.close();
  }
  void settingsFitAndIndividualControlsKeepTheViewAndFilter() {
    const auto path = temporary.path() + "/individual-controls.ini";
    FilesWindow window(Fusion::computerUrl(), false, path);
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.resize(1400, 900); window.show();
    QTRY_VERIFY_WITH_TIMEOUT(!window.property("fusionTheme").toString().isEmpty(), 10000);
    window.drives->volumes = inventory(); emit window.drives->changed();
    auto *shelf = window.browser()->findChild<DriveShelf *>();
    auto *filter = shelf->findChild<QCheckBox *>("showUnmountedDrives"); filter->click();
    auto configure = [&](const QStringList &visible, bool save) {
      bool found = false, fit = true;
      QTimer::singleShot(0, &window, [&] {
        auto *dialog = window.findChild<QDialog *>("filesConfiguration");
        if (!dialog) return;
        auto *tabs = dialog->findChild<QTabWidget *>("filesSettingsTabs");
        const auto artifacts = qEnvironmentVariable("FUSION_FILES_ARTIFACTS");
        for (const auto &name : {"browsingSettingsScroll", "computerSettingsScroll"}) {
          auto *page = dialog->findChild<QScrollArea *>(name);
          if (!page) { fit = false; continue; }
          tabs->setCurrentWidget(page); QCoreApplication::processEvents();
          fit &= page->verticalScrollBar()->maximum() == 0 && page->horizontalScrollBar()->maximum() == 0;
          if (!artifacts.isEmpty()) dialog->grab().save(artifacts + "/" + name + ".png");
        }
        int count = 0;
        for (const auto &[key, label] : DriveShelf::viewOptions())
          if (auto *toggle = dialog->findChild<QCheckBox *>("configureComputerView_" + key)) {
            toggle->setChecked(visible.contains(key)); ++count;
          }
        auto *switchControl = dialog->findChild<QCheckBox *>("configureUnmountedControl");
        found = count == modes.size() && switchControl;
        if (switchControl) switchControl->setChecked(false);
        if (found && save) dialog->accept(); else dialog->reject();
      });
      window.findChild<QAction *>("configureFiles")->trigger();
      QCoreApplication::processEvents();
      return found && fit;
    };
    QVERIFY(configure({"win7-themed"}, false));
    QVERIFY(filter->isVisible());
    for (const auto &name : buttons) QVERIFY(shelf->findChild<QToolButton *>(name)->isVisible());
    QVERIFY(configure({"win7-themed"}, true));
    for (int i = 0; i < modes.size(); ++i)
      QCOMPARE(shelf->findChild<QToolButton *>(buttons[i])->isVisible(), modes[i] == "win7-themed");
    QVERIFY(!filter->isVisible()); QVERIFY(!filter->isChecked());
    QVERIFY(!visibleDrive(*shelf, "/dev/backup"));
    QVERIFY(shelf->findChild<QToolButton *>("computerWin7ThemedView")->isChecked());
    QVERIFY(shelf->findChild<WindowsComputerView *>()->isVisible());
    FilesWindow reopened(Fusion::computerUrl(), false, path);
    reopened.setAttribute(Qt::WA_DeleteOnClose, false); reopened.show();
    QVERIFY(reopened.findChild<QToolButton *>("computerWin7ThemedView")->isChecked());
    QVERIFY(reopened.findChild<QToolButton *>("computerWin7ThemedView")->isVisible());
    QVERIFY(!reopened.findChild<QToolButton *>("computerWin7View")->isVisible());
    QVERIFY(!reopened.findChild<QCheckBox *>("showUnmountedDrives")->isVisible());
    reopened.close();
    // All buttons may be hidden without switching away from the selected view.
    QVERIFY(configure({}, true));
    QVERIFY(shelf->findChild<QWidget *>("computerViewButtons")->isHidden());
    QVERIFY(shelf->findChild<QToolButton *>("computerWin7ThemedView")->isChecked());
    QVERIFY(shelf->findChild<WindowsComputerView *>()->isVisible());
    QVERIFY(configure(modes, true));
    for (const auto &name : buttons) QVERIFY(shelf->findChild<QToolButton *>(name)->isVisible());
    window.close();
  }
  void themedViewsFollowPinnedPaletteAndKeepClassicColors() {
    if (qEnvironmentVariable("FUSION_FILES_ISOLATED") != "1")
      QSKIP("Requires an isolated profile for theme changes.");
    const auto statePath = Fusion::root() + "/theme/state.json";
    QFile stateFile(statePath); QVERIFY(stateFile.open(QIODevice::ReadOnly));
    const auto original = stateFile.readAll(); stateFile.close();
    auto writeState = [&](const QByteArray &data) {
      QSaveFile file(statePath);
      return file.open(QIODevice::WriteOnly) && file.write(data) == data.size() && file.commit();
    };
    const auto restore = qScopeGuard([&] { writeState(original); });
    auto state = QJsonDocument::fromJson(original).object();
    state["design"] = "killerinstinct"; state["mode"] = "dark";
    QVERIFY(writeState(QJsonDocument(state).toJson()));
    const auto path = temporary.path() + "/pinned-palette.ini";
    { QSettings settings(path, QSettings::IniFormat); settings.setValue("appearance/theme", "kitemple"); }
    QFile palettesFile(Fusion::root() + "/theme/palettes.json"); QVERIFY(palettesFile.open(QIODevice::ReadOnly));
    const auto palettes = QJsonDocument::fromJson(palettesFile.readAll()).object()["kitemple"].toObject();
    FilesWindow window(Fusion::computerUrl(), false, path);
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.resize(1600, 900); window.show();
    window.drives->volumes = inventory(); emit window.drives->changed();
    auto *shelf = window.browser()->findChild<DriveShelf *>();
    auto *pane = shelf->findChild<WindowsComputerView *>();
    QMap<QString, QImage> classicImages;
    auto hasColor = [](const QImage &image, const QColor &color) {
      int matches = 0;
      for (int y = 0; y < image.height(); ++y) for (int x = 0; x < image.width(); ++x) {
        const auto pixel = image.pixelColor(x, y);
        // Small text has antialiased edges, even at the center of a stroke.
        if (qAbs(pixel.red() - color.red()) <= 10 && qAbs(pixel.green() - color.green()) <= 10
            && qAbs(pixel.blue() - color.blue()) <= 10 && ++matches > 8) return true;
      }
      return false;
    };
    for (const QString &paletteMode : {"dark", "light", "contrast"}) {
      // Change the desktop while Files remains pinned to a different theme.
      state["mode"] = paletteMode; state["design"] = paletteMode == "dark" ? "killerinstinct" : "kifireice";
      QVERIFY(writeState(QJsonDocument(state).toJson()));
      const auto colors = palettes[paletteMode].toObject();
      QTRY_COMPARE_WITH_TIMEOUT(qApp->palette().color(QPalette::Window), QColor(colors["Window"].toString()), 10000);
      QCOMPARE(window.property("fusionTheme").toString(), QString("kitemple"));
      for (int i = 3; i < modes.size(); ++i) {
        auto *button = shelf->findChild<QToolButton *>(buttons[i]); button->click(); button->setFocus();
        shelf->selectDevice("/dev/main1"); QCoreApplication::processEvents();
        auto *item = visibleDrive(*shelf, "/dev/main1"); QVERIFY(item);
        const auto tile = item->grab().toImage();
        const auto frame = shelf->grab().toImage();
        QPixmap background(shelf->size()); background.fill(Qt::transparent);
        shelf->render(&background, QPoint(), QRegion(), QWidget::DrawWindowBackground);
        const auto expected = background.toImage();
        for (int y : {20, pane->viewport()->height() / 2, pane->viewport()->height() - 12}) {
          const auto point = pane->viewport()->mapTo(shelf, QPoint(pane->viewport()->width() - 3, y));
          QCOMPARE(frame.pixelColor(point), i < 7 ? QColor(Qt::white) : expected.pixelColor(point));
        }
        if (i < 7) {
          if (paletteMode == "dark") classicImages[modes[i]] = tile;
          else QCOMPARE(tile, classicImages[modes[i]]);
        } else {
          const auto artifacts = qEnvironmentVariable("FUSION_FILES_ARTIFACTS");
          if (!artifacts.isEmpty()) QVERIFY(tile.save(artifacts + "/selected-" + modes[i] + "-" + paletteMode + ".png"));
          const auto caption = i == 7 ? QRect(3, 42, tile.width() - 6, 48) : QRect(68, 8, tile.width() - 78, 22);
          QVERIFY2(hasColor(tile, QColor(colors["Highlight"].toString())), qPrintable(modes[i] + ' ' + paletteMode));
          QVERIFY2(hasColor(tile.copy(caption), QColor(colors["HighlightedText"].toString())), qPrintable(modes[i] + ' ' + paletteMode));
          shelf->selectDevice({});
          QVERIFY2(hasColor(item->grab().toImage().copy(caption), QColor(colors["Text"].toString())), qPrintable(modes[i] + ' ' + paletteMode));
          if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/" + modes[i] + "-jade-" + paletteMode + ".png"));
        }
      }
    }
    window.close();
  }
};
QTEST_MAIN(ComputerViewTests)
#include "computer_view_tests.moc"
