#include "../control_panel/backend/volume_commands.h"
#include "drive_properties.h"
#include "window.h"
#include "applications.h"
#include "removal.h"
#include "context_actions.h"
#include "transfers.h"
#include "transfer_issues.h"
#include "native_transfer.h"
#include <QLabel>
#include <QWindow>
#include <QTableView>
#include <QCheckBox>
#include <QPushButton>
#include <QPlainTextEdit>
#include <QLocalServer>
#include <QFileDialog>
#include <KIO/FileUndoManager>
#include <KApplicationTrader>
#include <KDirLister>
#include <KProtocolInfo>
#include <KIO/RenameDialog>
#include <KIO/Paste>
#include <KIO/RenameFileDialog>
#include <KIO/StatJob>
#include <KUrlComboBox>
#include <QDBusConnection>
#include <QScopeGuard>
#include <QStorageInfo>
#include <QtTest>
#include <sys/stat.h>
#include <unistd.h>

class TestFileManager : public QObject {
  Q_OBJECT
  Q_CLASSINFO("D-Bus Interface", "org.freedesktop.FileManager1")
public slots:
  void ShowItems(const QStringList &, const QString &) {}
  void ShowFolders(const QStringList &, const QString &) {}
};

class TestArkExtract : public QObject {
  Q_OBJECT
  Q_CLASSINFO("D-Bus Interface", "org.kde.ark.DndExtract")
public:
  QString destination;
public slots:
  void extractSelectedFilesTo(const QString &path) { destination=path; }
};

class FileTests : public QObject {
  Q_OBJECT
  QTemporaryDir temporary;
  QString folder;
  TestFileManager fileManager;
  static void write(const QString &path,
                    const QByteArray &bytes = "fixture data\n") {
    QFile file(path);
    QVERIFY(file.open(QIODevice::WriteOnly));
    QCOMPARE(file.write(bytes), bytes.size());
  }
  static Fusion::TransferIssues *queueFor(const QString &base) {
    for (auto *widget : QApplication::topLevelWidgets()) {
      auto *queue = qobject_cast<Fusion::TransferIssues *>(widget);
      if (!queue) continue;
      auto *table = queue->findChild<QTableView *>("transferIssuesTable");
      for (int n=0; n<table->model()->rowCount(); ++n)
        if (table->model()->index(n,3).data().toString().startsWith(base+"/")) return queue;
    }
    return nullptr;
  }
  static bool answerQueue(const QString &base, const QString &choice, bool all=true) {
    auto *queue = queueFor(base); if (!queue) return false;
    auto *table = queue->findChild<QTableView *>("transferIssuesTable");
    table->clearSelection();
    for (int n=0; n<table->model()->rowCount(); ++n)
      if (table->model()->index(n,2).data().toString()=="Needs a choice")
        table->selectionModel()->select(table->model()->index(n,0), QItemSelectionModel::Select|QItemSelectionModel::Rows);
    if (table->selectionModel()->selectedRows().isEmpty()) return false;
    if (choice=="cancel") { queue->findChild<QPushButton *>("cancelQueuedTransfer")->click(); return true; }
    queue->findChild<QCheckBox *>("similarTransferIssues")->setChecked(all);
    if (choice=="replace") QTimer::singleShot(0, queue, [queue] {
      for (auto *dialog : queue->findChildren<QMessageBox *>()) dialog->button(QMessageBox::Yes)->click();
    });
    queue->findChild<QPushButton *>("transferIssue_"+choice)->click();
    return true;
  }
  static void focus(Browser *tab) {
    tab->window()->activateWindow();
    tab->view()->setFocus();
    QTest::qWait(40);
  }
  static QPoint filePoint(Browser *tab, const QModelIndex &index) {
    const auto rect = tab->view()->visualRect(index);
    if (tab->view() != tab->icons) return rect.center();
    const auto icon = tab->icons->iconSize();
    return tab->icons->viewMode() == QListView::IconMode
        ? QPoint(rect.center().x(), rect.top() + icon.height() / 2 + 3)
        : QPoint(rect.left() + icon.width() / 2 + 3, rect.center().y());
  }
  static void clickFile(Browser *tab, const QUrl &url,
                        Qt::KeyboardModifiers modifiers = Qt::NoModifier) {
    const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(url));
    QVERIFY(index.isValid());
    tab->view()->scrollTo(index);
    QTRY_VERIFY(tab->view()->visualRect(index).isValid());
    QTest::mouseClick(tab->view()->viewport(), Qt::LeftButton, modifiers,
                      filePoint(tab, index));
  }
  static QListWidget *driveRow(Browser *tab, const QString &key) {
    for (auto *row : tab->findChildren<QListWidget *>("driveCards"))
      if (row->property("driveKey").toString() == key)
        return row;
    return nullptr;
  }
  static QList<QGroupBox *> driveGroups(Browser *tab, const QString &section) {
    return tab->findChild<QScrollArea *>(section)->findChildren<QGroupBox *>("physicalDriveGroup");
  }
  static QList<Volume> computerVolumes() {
    auto volumes = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/fusion-a","name":"fusion-a","type":"disk","model":"Fusion NVMe","tran":"nvme","size":1000000000000,"children":[
        {"path":"/dev/fusion-a1","type":"part","fstype":"vfat","label":"EFI","size":512000000,"mountpoints":["/boot/efi"]},
        {"path":"/dev/fusion-a2","type":"part","fstype":"ext4","label":"Linux system","size":512000000000,"mountpoints":["/"]},
        {"path":"/dev/fusion-a3","type":"part","fstype":"ntfs","label":"Windows","size":480000000000,"mountpoints":[null]}]},
      {"path":"/dev/fusion-b","name":"fusion-b","type":"disk","model":"Project SSD","tran":"sata","size":2000000000000,"children":[
        {"path":"/dev/fusion-b1","type":"part","fstype":"ext4","label":"Projects","size":2000000000000,"mountpoints":["/media/Projects"]}]},
      {"path":"/dev/fusion-c","name":"fusion-c","type":"disk","model":"Portable SSD","tran":"usb","rm":false,"size":64000000000,"children":[
        {"path":"/dev/fusion-c1","type":"part","fstype":"exfat","label":"USB files","size":32000000000,"mountpoints":["/media/USB"]},
        {"path":"/dev/fusion-c2","type":"part","fstype":"exfat","label":"USB backup","size":32000000000,"mountpoints":[null]}]}
    ]})");
    for (auto &volume : volumes)
      if (volume.mounted()) {
        volume.total = volume.size;
        volume.available = volume.total * 63 / 100;
        volume.freeBytes = volume.available;
        volume.spaceKnown = true;
      }
    return volumes;
  }
private slots:
  void cleanup() {
    // Completed queue reports intentionally stay open for review. They belong
    // to the preceding test, not to a subsequent no-dialog assertion.
    for (auto *widget : QApplication::topLevelWidgets())
      if (auto *queue=qobject_cast<Fusion::TransferIssues *>(widget)) queue->close();
    QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);
  }
  void initTestCase() {
    QVERIFY(temporary.isValid());
    folder = temporary.path() + "/files";
    QVERIFY(QDir().mkpath(folder));
    qApp->setQuitOnLastWindowClosed(false);
    qApp->setDesktopFileName("xetal-files");
    auto bus = QDBusConnection::sessionBus();
    QVERIFY(bus.registerService("org.freedesktop.FileManager1"));
    QVERIFY(bus.registerObject("/org/freedesktop/FileManager1", &fileManager,
                               QDBusConnection::ExportAllSlots));
  }
  void pathsPreserveLiteralCharacters() {
    const QString path = folder + "/deep path/# 100% café %u.txt";
    QCOMPARE(Fusion::displayPath(Fusion::userUrl(path)), path);
    QCOMPARE(Fusion::userUrl("../next", QUrl::fromLocalFile(folder + "/child"))
                 .adjusted(QUrl::NormalizePathSegments),
             QUrl::fromLocalFile(folder + "/next"));
    QCOMPARE(Fusion::userUrl("~/Documents").toLocalFile(),
             QDir::homePath() + "/Documents");
    QVERIFY(Fusion::isComputer(Fusion::userUrl("This PC")));
    QCOMPARE(Fusion::userUrl("smb://server/share/deep%20folder").path(),
             QString("/share/deep folder"));
    QVERIFY(!Fusion::validName("../outside"));
    QVERIFY(!Fusion::validName(".."));
    QVERIFY(Fusion::validName("100% # résumé.txt"));
  }
  void hiddenOnlyFolderExplainsAndRevealsItsContents() {
    const auto path = folder + "/hidden-only";
    QVERIFY(QDir().mkpath(path + "/.config"));
    write(path + "/.profile");
    FilesWindow window(QUrl::fromLocalFile(path), false, temporary.path() + "/hidden-only.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    auto *action = tab->findChild<QPushButton *>("folderMessageAction");
    auto *heading = tab->findChild<QLabel *>("folderMessageHeading");
    QTRY_VERIFY(action->isVisible());
    QCOMPARE(heading->text(), QString("This folder contains hidden files"));
    QCOMPARE(action->text(), QString("Show hidden files"));
    QVERIFY(!window.statusBar()->currentMessage().contains("0 items"));
    auto *explanation = tab->findChild<QLabel *>("folderMessageExplanation");
    QTRY_VERIFY(explanation->height() >= explanation->heightForWidth(explanation->width()));
    const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) { QTest::qWait(100); window.grab().save(capture + "-hidden-folder.png"); }
    tab->setView(4);
    QVERIFY(action->isVisible()); // View changes must not hide the explanation.
    QTest::mouseClick(action, Qt::LeftButton);
    QTRY_COMPARE(tab->proxy->rowCount(), 2);
    QVERIFY(!action->isVisible());
    QVERIFY(window.findChild<QAction *>("hiddenFilesAction")->isChecked());
    QVERIFY(window.preferences.settings.value("hidden").toBool());
    QVERIFY(tab->details->isVisible());
    QVERIFY(tab->model->indexForUrl(QUrl::fromLocalFile(path + "/.profile")).isValid());
  }
  void emptyAndFilteredFoldersAreNotReportedAsPrivate() {
    const auto path = folder + "/empty-readable";
    QVERIFY(QDir().mkpath(path));
    Fusion::Preferences preferences(temporary.path() + "/empty-readable.ini");
    Drives drives;
    Browser tab(&preferences, &drives);
    QSignalSpy loaded(tab.model->dirLister(), &KDirLister::completed);
    tab.navigate(QUrl::fromLocalFile(path));
    tab.show();
    QTRY_VERIFY(!loaded.isEmpty());
    QVERIFY(!tab.findChild<QPushButton *>("folderMessageAction")->isVisible());
    write(path + "/visible.txt");
    write(path + "/.hidden");
    tab.refresh();
    QTRY_COMPARE(tab.proxy->rowCount(), 1);
    tab.filter->setText("no such name");
    QCOMPARE(tab.proxy->rowCount(), 0);
    QVERIFY(!tab.findChild<QPushButton *>("folderMessageAction")->isVisible());
    tab.filter->clear();
    QTRY_COMPARE(tab.proxy->rowCount(), 1);
  }
  void privateFolderShowsUnlockAndRecoversWithoutChangingPermissions() {
    if (geteuid() == 0) QSKIP("Permission denial requires an ordinary desktop user.");
    const auto path = folder + "/private # café";
    QVERIFY(QDir().mkpath(path));
    write(path + "/keep.txt");
    const auto encoded = QFile::encodeName(path);
    const auto restore = qScopeGuard([&] { ::chmod(encoded, 0700); });
    QCOMPARE(::chmod(encoded, 0000), 0);
    FilesWindow window(QUrl::fromLocalFile(path), false, temporary.path() + "/private.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    auto *action = tab->findChild<QPushButton *>("folderMessageAction");
    QTRY_VERIFY(action->isVisible());
    QTRY_COMPARE(action->text(), QString("Unlock folder…"));
    QCOMPARE(tab->findChild<QLabel *>("folderMessageHeading")->text(), QString("This folder is private"));
    QVERIFY(tab->findChild<QLabel *>("folderMessageExplanation")->text().contains("running system"));
    QCOMPARE(window.statusBar()->currentMessage(), QString("This folder is private"));
    const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) { QTest::qWait(100); window.grab().save(capture + "-private-folder.png"); }
    QCOMPARE(tab->location(), QUrl::fromLocalFile(path)); // No automatic elevation or prompt loop.
    struct stat info;
    QCOMPARE(::stat(encoded, &info), 0);
    QCOMPARE(info.st_mode & 0777, mode_t(0000));
    tab->setView(4);
    QVERIFY(action->isVisible());
    tab->refresh();
    QTRY_VERIFY(action->isVisible());
    QTRY_COMPARE(action->text(), QString("Unlock folder…"));
    // Permissions can also be corrected externally; Refresh retries a failed
    // listing instead of trying to update a directory absent from the cache.
    QCOMPARE(::chmod(encoded, 0700), 0);
    tab->refresh();
    QTRY_COMPARE(tab->proxy->rowCount(), 1);
    QVERIFY(!action->isVisible());
    QVERIFY(tab->details->isVisible());
    QVERIFY(QFileInfo::exists(path + "/keep.txt"));
  }
  void missingFolderOffersRetryInsteadOfCredentials() {
    const auto path = folder + "/missing-folder";
    Fusion::Preferences preferences(temporary.path() + "/missing-folder.ini");
    Drives drives;
    Browser tab(&preferences, &drives);
    tab.navigate(QUrl::fromLocalFile(path));
    tab.show();
    auto *action = tab.findChild<QPushButton *>("folderMessageAction");
    QTRY_VERIFY(action->isVisible());
    QCOMPARE(action->text(), QString("Try again"));
    QVERIFY(QDir().mkpath(path));
    write(path + "/now-here.txt");
    QTest::mouseClick(action, Qt::LeftButton);
    QTRY_COMPARE(tab.proxy->rowCount(), 1);
    QVERIFY(!action->isVisible());
    tab.navigate(Fusion::computerUrl());
    QVERIFY(!action->isVisible());
  }
  void unlockFailureCanReturnToNormalAccess() {
    if (geteuid() == 0 || !KProtocolInfo::isKnownProtocol("admin")) QSKIP("Needs kio-admin and an ordinary user.");
    if (!qEnvironmentVariable("DBUS_SYSTEM_BUS_ADDRESS").endsWith("/no-system-bus"))
      QSKIP("Run through test.py: authentication tests must not contact the real system bus.");
    const auto path = folder + "/unlock # 100% café";
    QVERIFY(QDir().mkpath(path));
    write(path + "/kept.txt");
    const auto encoded = QFile::encodeName(path);
    const auto restore = qScopeGuard([&] { ::chmod(encoded, 0700); });
    QCOMPARE(::chmod(encoded, 0000), 0);
    Fusion::Preferences preferences(temporary.path() + "/unlock.ini");
    Drives drives;
    Browser tab(&preferences, &drives);
    tab.navigate(QUrl::fromLocalFile(path));
    tab.show();
    auto *action = tab.findChild<QPushButton *>("folderMessageAction");
    QTRY_VERIFY(action->isVisible());
    QTRY_COMPARE(action->text(), QString("Unlock folder…"));
    QSignalSpy attempts(tab.model->dirLister(), &KDirLister::started);
    QTest::mouseClick(action, Qt::LeftButton);
    QCOMPARE(tab.location().scheme(), QString("admin"));
    QCOMPARE(tab.location().path(), path);
    auto *normal = tab.findChild<QPushButton *>("normalFolderAccess");
    QVERIFY(normal->isVisible());
    QTRY_VERIFY_WITH_TIMEOUT(action->isVisible(), 15000);
    QCOMPARE(action->text(), QString("Try again"));
    const auto count = attempts.size();
    QTest::qWait(100);
    QCOMPARE(attempts.size(), count); // Authentication failure never loops.
    QTest::mouseClick(normal, Qt::LeftButton);
    QCOMPARE(tab.location(), QUrl::fromLocalFile(path));
    QTRY_VERIFY(action->isVisible());
    QTRY_COMPARE(action->text(), QString("Unlock folder…"));
    QVERIFY(!normal->isVisible());
    struct stat info;
    QCOMPARE(::stat(encoded, &info), 0);
    QCOMPARE(info.st_mode & 0777, mode_t(0000));
    QCOMPARE(::chmod(encoded, 0700), 0);
    tab.refresh();
    QTRY_COMPARE(tab.proxy->rowCount(), 1);
  }
  void iconSetChangesKeepTheOpenFolderAndSelection() {
    const auto oldPaths=QIcon::themeSearchPaths();const auto oldName=QIcon::themeName();
    const auto reset=qScopeGuard([&]{QIcon::setThemeSearchPaths(oldPaths);QIcon::setThemeName(oldName);});
    const QString iconRoot=temporary.path()+"/icon-sets";
    for (const auto &name:QStringList{"Fusion-Test-Red","Fusion-Test-Green"}) {
      const QString path=iconRoot+"/"+name;
      QVERIFY(QDir().mkpath(path+"/scalable"));
      QFile index(path+"/index.theme");QVERIFY(index.open(QIODevice::WriteOnly));
      index.write("[Icon Theme]\nName=Test Icons\nDirectories=scalable\n\n[scalable]\nSize=64\nType=Scalable\nMinSize=16\nMaxSize=512\n");index.close();
      QImage image(64,64,QImage::Format_ARGB32);image.fill(name.endsWith("Red") ? QColor("#d12244") : QColor("#22bb55"));
      QVERIFY(image.save(path+"/scalable/folder.png"));
      QVERIFY(image.save(path+"/scalable/inode-directory.png"));
    }
    const QString parent=folder+"/icon-reload";const auto child=QUrl::fromLocalFile(parent+"/example");
    QVERIFY(QDir().mkpath(child.toLocalFile()));
    Fusion::Preferences preferences(temporary.path()+"/icon-reload.ini");Drives drives;
    QIcon::setThemeSearchPaths({iconRoot});QIcon::setThemeName("Fusion-Test-Red");
    Browser browser(&preferences,&drives);browser.setThumbnails(false);browser.navigate(QUrl::fromLocalFile(parent));browser.show();
    QTRY_VERIFY_WITH_TIMEOUT(browser.model->indexForUrl(child).isValid(),5000);
    browser.selectUrl(child);
    auto color=[&]{const auto image=qvariant_cast<QIcon>(browser.model->indexForUrl(child).data(Qt::DecorationRole)).pixmap(64,64).toImage();return image.isNull() ? QString("null") : image.pixelColor(image.width()/2,image.height()/2).name();};
    QTRY_COMPARE_WITH_TIMEOUT(color(),QString("#d12244"),5000);
    QIcon::setThemeName("Fusion-Test-Green");browser.refreshIcons();
    QTRY_COMPARE_WITH_TIMEOUT(color(),QString("#22bb55"),5000);
    QCOMPARE(browser.location(),QUrl::fromLocalFile(parent));QCOMPARE(browser.selectedUrls(),QList<QUrl>{child});
  }
  void builtinWindowControlsUseNativeActions() {
    FilesWindow window(Fusion::computerUrl(),false,temporary.path()+"/window-controls.ini");
    window.setAttribute(Qt::WA_DeleteOnClose,false);window.show();
    auto *minimize=window.findChild<QToolButton *>("windowMinimize");
    auto *maximize=window.findChild<QToolButton *>("windowMaximize");
    auto *close=window.findChild<QToolButton *>("windowClose");
    QVERIFY(minimize&&maximize&&close);
    window.resize(760,450);QTRY_VERIFY(close->isVisibleTo(&window));
    for(int i=0;i<3;++i){
      maximize->click();QTRY_VERIFY(window.isMaximized());QCOMPARE(maximize->accessibleName(),QString("Restore"));
      maximize->click();QTRY_VERIFY(!window.isMaximized());QCOMPARE(maximize->accessibleName(),QString("Maximize"));
    }
    minimize->click();QTRY_VERIFY(window.isMinimized());
    window.showNormal();QTRY_VERIFY(!window.isMinimized());QVERIFY(window.isVisible());
    close->click();QTRY_VERIFY(!window.isVisible());
  }
  void trashButtonFollowsLocationAndCancelKeepsFiles() {
    FilesWindow window(QUrl::fromLocalFile(folder), false, temporary.path()+"/trash-button.ini");
    window.show();
    auto *button=window.findChild<QToolButton *>("emptyTrashButton");QVERIFY(button);
    QVERIFY(!button->isVisible());
    window.openLocation(QUrl("trash:/"));QTRY_VERIFY(button->isVisible());
    QTest::mouseClick(button,Qt::LeftButton);
    QTRY_VERIFY(window.findChild<QMessageBox *>("emptyTrashConfirmation"));
    auto *dialog=window.findChild<QMessageBox *>("emptyTrashConfirmation");
    QCOMPARE(dialog->defaultButton(),dialog->button(QMessageBox::Cancel));
    dialog->reject();QCoreApplication::processEvents();
    window.openLocation(QUrl::fromLocalFile(folder));QTRY_VERIFY(!button->isVisible());
  }
  void desktopMenuPreferencesAreIndependent() {
    Fusion::Preferences preferences(temporary.path()+"/desktop-menu.ini");
    const auto files=preferences.menu();auto desktop=files;
    desktop[0]["enabled"]=false;preferences.setMenu(desktop,"desktopMenu");
    QCOMPARE(preferences.menu(),files);QCOMPARE(preferences.menu("desktopMenu"),desktop);
  }
  void sidebarSelectionKeepsIndentationClear() {
    // Render the real PlacesTree with every shipped palette and marker. A
    // second selected background in the branch gutter must not reappear.
    QProcess styles;
    styles.start("python3", {"-c", R"(
import json,sys
from unittest.mock import patch
sys.path.insert(0,sys.argv[1]+'/file_manager')
import appearance
runtime=appearance.runtime
rows=[]
for design in runtime.DESIGNS:
 for mode in runtime.MODES:
  for marker in ('none','line','curve'):
   with patch.object(runtime,'state',return_value=dict(design=design,mode=mode,selection_marker=marker)):
    rows.append(dict(design=design,mode=mode,marker=marker,style=appearance.appearance()['stylesheet']))
print(json.dumps(rows))
)", Fusion::root()});
    QVERIFY(styles.waitForFinished(15000));
    QCOMPARE(styles.exitCode(), 0);
    const auto variants = QJsonDocument::fromJson(styles.readAllStandardOutput()).array();
    QVERIFY(variants.size() >= 72);
    FilesWindow window(Fusion::computerUrl(), false, temporary.path()+"/sidebar.ini");
    window.show();
    // Other window tests leave the application's stylesheet populated. Wait
    // for this window's own asynchronous theme load before inserting fixture
    // rows, otherwise its completion rebuilds the tree beneath the test.
    QTRY_VERIFY(!window.property("fusionIconTheme").toString().isEmpty());
    auto *tree = window.findChild<QTreeWidget *>("places");
    QVERIFY(tree);
    tree->clear();
    auto *group = new QTreeWidgetItem(tree, {"Quick access"});
    auto *child = new QTreeWidgetItem(group, {"Pictures"});
    group->setExpanded(true);
    for (const auto variant : variants) {
      const auto row = variant.toObject();
      tree->setStyleSheet(row["style"].toString());
      for (auto direction : {Qt::LeftToRight, Qt::RightToLeft}) {
        tree->setLayoutDirection(direction);
        tree->clearSelection();
        qApp->processEvents();
        const auto bounds = tree->visualItemRect(child);
        auto gutter = bounds;
        if (direction == Qt::LeftToRight) gutter.setCoords(0,bounds.top(),bounds.left()-1,bounds.bottom());
        else gutter.setCoords(bounds.right()+1,bounds.top(),tree->viewport()->width()-1,bounds.bottom());
        QVERIFY(gutter.width() >= tree->indentation());
        const auto plain = tree->viewport()->grab().toImage();
        tree->setCurrentItem(child);
        child->setSelected(true);
        const auto selected = tree->viewport()->grab().toImage();
        const auto name = row["design"].toString()+" / "+row["mode"].toString()+" / "+row["marker"].toString();
        QVERIFY2(plain.copy(gutter) == selected.copy(gutter), qPrintable(name));
        QVERIFY2(plain.copy(bounds) != selected.copy(bounds), qPrintable(name));
        const auto capture = qEnvironmentVariable("FUSION_SIDEBAR_CAPTURE");
        if (!capture.isEmpty() && direction == Qt::LeftToRight && row["mode"] == "dark")
          tree->grab().save(capture+"/"+row["design"].toString()+"-"+row["marker"].toString()+".png");
      }
    }
    tree->setLayoutDirection(Qt::LeftToRight);
    tree->setCurrentItem(group);
    const auto bounds = tree->visualItemRect(group);
    const QPoint arrow(bounds.left()-tree->indentation()/2,bounds.center().y());
    QTest::mouseClick(tree->viewport(),Qt::LeftButton,Qt::NoModifier,arrow);
    QVERIFY(!group->isExpanded());
    QTest::mouseClick(tree->viewport(),Qt::LeftButton,Qt::NoModifier,arrow);
    QVERIFY(group->isExpanded());
  }
  void navigationTreeIsAvailableInEveryWindow_data() {
    QTest::addColumn<bool>("external");
    QTest::addColumn<bool>("computer");
    QTest::addColumn<bool>("collapsed");
    for (bool external : {false, true})
      for (bool computer : {false, true})
        for (bool collapsed : {false, true})
          QTest::newRow(qPrintable(QString(external ? "external" : "normal") +
              (computer ? " computer" : " folder") + (collapsed ? " collapsed" : " fresh")))
              << external << computer << collapsed;
  }
  void navigationTreeIsAvailableInEveryWindow() {
    QFETCH(bool, external); QFETCH(bool, computer); QFETCH(bool, collapsed);
    const auto restoreRole = qScopeGuard([] { qApp->setDesktopFileName("xetal-files"); });
    qApp->setDesktopFileName(external ? "xetal-files-external" : "xetal-files");
    const auto path = temporary.path()+"/navigation-"+QTest::currentDataTag()+".ini";
    Fusion::Preferences saved(path);
    auto bookmarks = saved.places();
    bookmarks.append({{"name", "Navigation test folder"},
        {"url", QUrl::fromLocalFile(folder).toString()}, {"icon", "folder"}});
    saved.setPlaces(bookmarks);
    // Exercise both preview states while repairing only the navigation pane.
    saved.settings.setValue("preview", !computer);
    if (collapsed) {
      QSplitter legacy;
      for (int i = 0; i < 3; ++i) legacy.addWidget(new QWidget);
      legacy.resize(1100, 600);
      legacy.setSizes({0, 900, 270});
      QCOMPARE(legacy.sizes().first(), 0);
      saved.settings.setValue("splitter", legacy.saveState());
    }
    saved.settings.sync();
    const auto initial = computer ? Fusion::computerUrl() : QUrl::fromLocalFile(folder);
    int width = 0;
    {
      FilesWindow window(initial, false, path);
      window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
      auto *tree = window.findChild<QTreeWidget *>("places"); QVERIFY(tree);
      auto *split = qobject_cast<QSplitter *>(tree->parentWidget()); QVERIFY(split);
      QTRY_VERIFY(tree->isVisible() && tree->width() >= 165);
      QVERIFY(!split->isCollapsible(0));
      QCOMPARE(split->widget(2)->isVisible(), !computer);
      QCOMPARE(window.browser()->location(), initial);
      // Neither a divider drag nor opening another tab can lose navigation.
      auto sizes = split->sizes(); sizes[0] = 0; split->setSizes(sizes);
      QTRY_VERIFY(tree->width() >= 165);
      window.openLocation(Fusion::computerUrl(), true);
      QTRY_VERIFY(tree->isVisible() && tree->width() >= 165);
      QTreeWidgetItem *destination = nullptr;
      for (QTreeWidgetItemIterator it(tree); *it; ++it)
        if ((*it)->text(0) == "Navigation test folder") destination = *it;
      QVERIFY(destination); tree->scrollToItem(destination);
      QTest::mouseClick(tree->viewport(), Qt::LeftButton, Qt::NoModifier,
          tree->visualItemRect(destination).center());
      QTRY_COMPARE(window.browser()->location(), QUrl::fromLocalFile(folder));
      sizes = split->sizes(); sizes[0] = 275; split->setSizes(sizes);
      QTest::qWait(100); width = tree->width(); QVERIFY(width >= 165);
      window.close();
    }
    saved.settings.sync();
    QCOMPARE(saved.settings.value("preview").toBool(), !computer);
    QCOMPARE(saved.places(), bookmarks);
    FilesWindow reopened(initial, false, path);
    reopened.setAttribute(Qt::WA_DeleteOnClose, false); reopened.show();
    auto *tree = reopened.findChild<QTreeWidget *>("places"); QVERIFY(tree);
    QTRY_VERIFY(tree->isVisible() && tree->width() >= 165);
    QTRY_VERIFY(qAbs(tree->width()-width) <= 3);
    const auto artifacts = qEnvironmentVariable("FUSION_FILES_ARTIFACTS");
    if (!artifacts.isEmpty()) {
      QDir().mkpath(artifacts);
      QVERIFY(reopened.grab().save(artifacts+"/"+QTest::currentDataTag()+".png"));
    }
    reopened.close();
  }
  void previewPaneRecoversSavedWidth_data() {
    QTest::addColumn<bool>("external"); QTest::addColumn<bool>("computer");
    QTest::addColumn<bool>("enabled"); QTest::addColumn<int>("savedWidth");
    for (bool external : {false,true})
      for (bool computer : {false,true})
        for (bool enabled : {false,true})
          for (int width : {-1,0,2,330})
            QTest::newRow(qPrintable(QString("%1-%2-%3-%4")
                .arg(external ? "external" : "normal").arg(computer ? "computer" : "folder")
                .arg(enabled ? "shown" : "hidden").arg(width)))
                << external << computer << enabled << width;
  }
  void previewPaneRecoversSavedWidth() {
    QFETCH(bool,external); QFETCH(bool,computer); QFETCH(bool,enabled); QFETCH(int,savedWidth);
    const auto restoreRole=qScopeGuard([] { qApp->setDesktopFileName("xetal-files"); });
    qApp->setDesktopFileName(external ? "xetal-files-external" : "xetal-files");
    const auto path=temporary.path()+"/preview-width-"+QTest::currentDataTag()+".ini";
    Fusion::Preferences saved(path);
    // Leave the fresh default unset: it should offer Preview immediately.
    if (!enabled) saved.settings.setValue("preview",false);
    if (savedWidth>=0) {
      QSplitter legacy; for (int i=0;i<3;++i) legacy.addWidget(new QWidget);
      legacy.resize(1200,650); legacy.setHandleWidth(1);
      legacy.setSizes({210,720,savedWidth});
      saved.settings.setValue("splitter",legacy.saveState());
    }
    saved.settings.sync();
    const auto initial=computer ? Fusion::computerUrl() : QUrl::fromLocalFile(folder);
    int customWidth=0;
    {
      FilesWindow window(initial,false,path);window.setAttribute(Qt::WA_DeleteOnClose,false);window.show();
      auto *pane=window.findChild<QStackedWidget *>("previewStack");QVERIFY(pane);
      auto *split=qobject_cast<QSplitter *>(pane->parentWidget());QVERIFY(split);
      auto *action=window.findChild<QAction *>("previewPaneAction");QVERIFY(action);
      QCOMPARE(action->isChecked(),enabled);QCOMPARE(pane->isVisible(),enabled);
      QVERIFY(!split->isCollapsible(2));QVERIFY(split->handleWidth()>=6);
      if (!enabled) window.runAction("preview");
      QTRY_VERIFY(pane->isVisible() && pane->width()>=240);
      // A programmatic zero models dragging the divider all the way closed.
      auto sizes=split->sizes();sizes[2]=0;split->setSizes(sizes);
      QTRY_VERIFY(pane->width()>=240);
      sizes=split->sizes();sizes[2]=335;split->setSizes(sizes);QTest::qWait(25);
      customWidth=pane->width();QVERIFY(customWidth>270);
      window.runAction("preview");QVERIFY(!pane->isVisible());
      window.runAction("preview");QTRY_VERIFY(pane->width()>=240);
      QTRY_VERIFY(qAbs(pane->width()-customWidth)<=3);
      window.close();
    }
    FilesWindow reopened(initial,false,path);reopened.setAttribute(Qt::WA_DeleteOnClose,false);reopened.show();
    auto *pane=reopened.findChild<QStackedWidget *>("previewStack");QVERIFY(pane);
    QTRY_VERIFY(pane->isVisible() && pane->width()>=240);
    QTRY_VERIFY(qAbs(pane->width()-customWidth)<=3);
    const auto artifacts=qEnvironmentVariable("FUSION_FILES_ARTIFACTS");
    if (!artifacts.isEmpty() && savedWidth==0 && enabled) {
      QDir().mkpath(artifacts);QVERIFY(reopened.grab().save(artifacts+"/preview-"+QTest::currentDataTag()+".png"));
    }
    reopened.runAction("preview");reopened.close();saved.settings.sync();
    QVERIFY(!saved.settings.value("preview").toBool());
  }
  void launchGeometrySeparatesNormalAndExternalWindows() {
    const auto path = temporary.path() + "/launch-geometry.ini";
    const auto restore = qScopeGuard([] { qApp->setDesktopFileName("xetal-files"); });
    QWidget previous;
    previous.resize(1600, 1000);
    previous.setWindowState(Qt::WindowMaximized);
    Fusion::Preferences settings(path);
    settings.settings.setValue("geometry", previous.saveGeometry());
    settings.settings.setValue("external/size", QSize(940, 610));
    settings.settings.sync();
    {
      FilesWindow normal(Fusion::computerUrl(), false, path);
      QCOMPARE(normal.windowState(), Qt::WindowNoState);
      QCOMPARE(normal.size(), QSize(1180, 760));
    }
    qApp->setDesktopFileName("xetal-files-external");
    {
      FilesWindow external(Fusion::computerUrl(), false, path);
      external.setAttribute(Qt::WA_DeleteOnClose, false);
      QCOMPARE(external.windowState(), Qt::WindowNoState);
      QCOMPARE(external.size(), QSize(940, 610));
      external.resize(1020, 680); external.close();
    }
    {
      FilesWindow external(Fusion::computerUrl(), false, path);
      QCOMPARE(external.size(), QSize(1020, 680));
      QCOMPARE(external.windowState(), Qt::WindowNoState);
    }
    qApp->setDesktopFileName("xetal-files");
    FilesWindow normal(Fusion::computerUrl(), false, path);
    QCOMPARE(normal.size(), QSize(1180, 760));
    QCOMPARE(normal.windowState(), Qt::WindowNoState);
  }
  void transferAccessUsesOnlyNecessaryPrivileges() {
    if (geteuid() == 0) QSKIP("Permission routing is checked as the desktop user.");
    const auto base = folder + "/access";
    QDir().mkpath(base + "/source/nested");
    QDir().mkpath(base + "/destination");
    const auto file = base + "/source/nested/protected # 100%.txt";
    write(file);
    const auto source = QUrl::fromLocalFile(base + "/source");
    const auto destination = QUrl::fromLocalFile(base + "/destination");
    const auto cancelled = std::make_shared<std::atomic_bool>(false);
    auto plan = [&](QList<QUrl> items, Fusion::TransferOperation operation) {
      return Fusion::transferAccess(items, destination, operation, cancelled);
    };
    const auto restore = qScopeGuard([&] {
      ::chmod(QFile::encodeName(file), 0600);
      ::chmod(QFile::encodeName(base + "/source"), 0700);
      ::chmod(QFile::encodeName(base + "/destination"), 0700);
    });
    QVERIFY(!plan({source}, Fusion::TransferOperation::Copy).administrator);
    QCOMPARE(::chmod(QFile::encodeName(file), 0000), 0);
    auto copy = plan({source}, Fusion::TransferOperation::Copy);
    QVERIFY(copy.administrator);
    QCOMPARE(copy.sources.first().scheme(), "admin");
    QCOMPARE(copy.destination, destination); // Normal destination stays user-owned.
    QVERIFY(!plan({source}, Fusion::TransferOperation::Move).administrator); // Atomic rename.
    const auto link = base + "/link";
    QVERIFY(QFile::link(file, link));
    QVERIFY(!plan({QUrl::fromLocalFile(link)}, Fusion::TransferOperation::Copy).administrator);
    QCOMPARE(::chmod(QFile::encodeName(base + "/source"), 0500), 0);
    const auto moved = plan({QUrl::fromLocalFile(base + "/source/nested")}, Fusion::TransferOperation::Move);
    QVERIFY(moved.administrator);
    QCOMPARE(moved.destination.scheme(), "admin");
    QCOMPARE(::chmod(QFile::encodeName(base + "/destination"), 0500), 0);
    copy = plan({QUrl::fromLocalFile(link)}, Fusion::TransferOperation::Copy);
    QVERIFY(copy.administrator);
    QCOMPARE(copy.destination.scheme(), "admin");
    QCOMPARE(copy.sources.first().scheme(), "file");
  }
  void dropsMoveByDefaultAndCopyWithControl() {
    const auto base=folder+"/direct-drop";
    QDir().mkpath(base+"/copy");QDir().mkpath(base+"/move");QDir().mkpath(base+"/source/Folder");
    write(base+"/source/Folder/child.txt","keep contents");
    QMimeData mime;mime.setUrls({QUrl::fromLocalFile(base+"/source/Folder")});
    QWidget owner;
    for (auto modifier : {Qt::ControlModifier,Qt::NoModifier}) {
      QDropEvent event(QPointF(1,1),Qt::MoveAction|Qt::CopyAction,&mime,Qt::LeftButton,modifier);
      QCOMPARE(Fusion::fileDropAction(&mime,modifier,event.possibleActions()),modifier==Qt::ControlModifier?Qt::CopyAction:Qt::MoveAction);
      const auto target=base+(modifier==Qt::ControlModifier?"/copy":"/move");
      auto *job=Fusion::dropFiles(&event,QUrl::fromLocalFile(target),&owner,{});
      QVERIFY(job);int error=-1;connect(job,&KJob::result,&owner,[&](KJob *j){error=j->error();});
      QTRY_COMPARE_WITH_TIMEOUT(error,0,10000);
      QCOMPARE(QFileInfo::exists(base+"/source/Folder/child.txt"),modifier==Qt::ControlModifier);
      QVERIFY(QFileInfo::exists(target+"/Folder/child.txt"));
      QVERIFY(!owner.findChild<QMessageBox *>("transferConflictQuestion"));
    }
    QCOMPARE(Fusion::fileDropAction(&mime,Qt::NoModifier,Qt::CopyAction),Qt::CopyAction);
    QCOMPARE(Fusion::fileDropAction(&mime,Qt::ControlModifier,Qt::MoveAction),Qt::IgnoreAction);
  }
  void dragModifiersAndShortcuts() {
    const auto base=folder+"/drag-shortcuts";
    QDir().mkpath(base+"/source/Folder");QDir().mkpath(base+"/target");
    write(base+"/source/Folder/child.txt","folder contents");write(base+"/source/notes # café.txt","file contents");
    QMimeData mime;mime.setUrls({QUrl::fromLocalFile(base+"/source/Folder"),QUrl::fromLocalFile(base+"/source/notes # café.txt")});
    const auto linkKeys=Qt::ControlModifier|Qt::ShiftModifier;
    const auto wireActions=Qt::CopyAction|Qt::MoveAction;
    QCOMPARE(Fusion::fileDropOperation(&mime,linkKeys,wireActions),Qt::LinkAction);
    QCOMPARE(Fusion::fileDropAction(&mime,linkKeys,wireActions),Qt::CopyAction);
    QCOMPARE(Fusion::fileDropAction(&mime,linkKeys,wireActions|Qt::LinkAction),Qt::LinkAction);
    QCOMPARE(Fusion::fileDropAction(&mime,Qt::ShiftModifier,wireActions),Qt::MoveAction);
    QCOMPARE(Fusion::fileDropAction(&mime,Qt::ShiftModifier,Qt::CopyAction),Qt::IgnoreAction);
    QCOMPARE(Fusion::fileDropAction(&mime,linkKeys,Qt::MoveAction),Qt::IgnoreAction);
    QWidget owner;
    for (const auto &target : {base+"/target",base+"/source"}) {
      QDropEvent event(QPointF(1,1),wireActions,&mime,Qt::LeftButton,linkKeys);
      auto *job=Fusion::dropFiles(&event,QUrl::fromLocalFile(target),&owner,{});QVERIFY(job);
      int error=-1;connect(job,&KJob::result,&owner,[&](KJob *j){error=j->error();});
      QTRY_COMPARE_WITH_TIMEOUT(error,0,10000);
      const auto suffix=target.endsWith("/source")?"_copy1":"";
      const QFileInfo linkedFolder(target+"/Folder"+suffix),linkedFile(target+"/notes # café"+suffix+".txt");
      QVERIFY(linkedFolder.isSymbolicLink());QVERIFY(linkedFile.isSymbolicLink());
      QCOMPARE(linkedFolder.symLinkTarget(),base+"/source/Folder");
      QCOMPARE(linkedFile.symLinkTarget(),base+"/source/notes # café.txt");
      QVERIFY(!owner.findChild<QMessageBox *>("duplicateDropQuestion"));
    }
    QVERIFY(!QFileInfo(base+"/source/Folder").isSymbolicLink());
    QVERIFY(!QFileInfo(base+"/source/notes # café.txt").isSymbolicLink());
    for (const auto &target : {QUrl("computer:/"),QUrl("network:/"),QUrl::fromLocalFile(base+"/source/notes # café.txt")}) {
      QVERIFY(!Fusion::fileDropDestination(target));
      QDropEvent event(QPointF(1,1),wireActions,&mime,Qt::LeftButton,Qt::ControlModifier);
      QVERIFY(!Fusion::dropFiles(&event,target,&owner,{}));
    }
  }
  void crossFolderConflictsAskBeforeOverwriting() {
    for (const auto answer : {QMessageBox::Cancel,QMessageBox::No,QMessageBox::Yes}) {
      const auto base=folder+"/conflict-"+QString::number(answer);
      QDir().mkpath(base+"/source");QDir().mkpath(base+"/target");
      write(base+"/source/item.txt","source");write(base+"/target/item.txt","destination");
      QWidget owner;QMimeData mime;mime.setUrls({QUrl::fromLocalFile(base+"/source/item.txt")});
      QDropEvent event(QPointF(1,1),Qt::MoveAction|Qt::CopyAction,&mime,Qt::LeftButton,Qt::NoModifier);
      auto *job=Fusion::dropFiles(&event,QUrl::fromLocalFile(base+"/target"),&owner,{});
      int error=-1;connect(job,&KJob::result,&owner,[&](KJob *j){error=j->error();});
      QTRY_VERIFY(queueFor(base));
      auto *queue=queueFor(base); QVERIFY(!queue->isModal());
      QTRY_VERIFY(queue->isVisible());
      QFile existing(base+"/target/item.txt");QVERIFY(existing.open(QIODevice::ReadOnly));
      QCOMPARE(existing.readAll(),QByteArray("destination"));existing.close();
      QVERIFY(QFileInfo::exists(base+"/source/item.txt"));
      queue->hide(); QTest::qWait(30); QCOMPARE(error,-1); queue->reveal();
      QVERIFY(answerQueue(base, answer==QMessageBox::Cancel?"cancel":answer==QMessageBox::Yes?"replace":"skip"));
      QTRY_COMPARE_WITH_TIMEOUT(error,answer==QMessageBox::Cancel?KIO::ERR_USER_CANCELED:0,10000);
      QVERIFY(existing.open(QIODevice::ReadOnly));
      QCOMPARE(existing.readAll(),answer==QMessageBox::Yes?QByteArray("source"):QByteArray("destination"));
      QCOMPARE(QFileInfo::exists(base+"/source/item.txt"),answer!=QMessageBox::Yes);
      QVERIFY(!QFileInfo::exists(base+"/target/item_copy1.txt"));
    }
  }
  void overwriteAllMergesRecursivelyForCopyAndMove() {
    for (const auto operation : {Fusion::TransferOperation::Copy,Fusion::TransferOperation::Move}) {
      const auto base=folder+"/overwrite-all-"+QString::number(int(operation));
      for (const auto side : {"source","target"}) {
        QDir().mkpath(base+"/"+side+"/Folder/nested/deeper");
        for (const auto file : {"first.txt","Folder/a.txt","Folder/nested/deeper/b.txt"})
          write(base+"/"+side+"/"+file,QByteArray(side));
      }
      write(base+"/target/Folder/keep.txt","keep destination only");
      write(base+"/source/Folder/new.txt","new source only");
      QWidget owner;int prompts=0;
      QTimer answer;connect(&answer,&QTimer::timeout,&owner,[&]{
        if (!QFileInfo::exists(base+"/target/Folder/new.txt")) return;
        if (answerQueue(base,"replace")) ++prompts;
      });answer.start(10);
      auto *job=Fusion::transferFiles({QUrl::fromLocalFile(base+"/source/first.txt"),QUrl::fromLocalFile(base+"/source/Folder")},
          QUrl::fromLocalFile(base+"/target"),operation,&owner);
      int error=-1;connect(job,&KJob::result,&owner,[&](KJob *j){error=j->error();});
      QTRY_COMPARE_WITH_TIMEOUT(error,0,15000);QVERIFY(prompts>=1);
      for (const auto file : {"first.txt","Folder/a.txt","Folder/nested/deeper/b.txt"}) {
        QFile copied(base+"/target/"+file);QVERIFY(copied.open(QIODevice::ReadOnly));QCOMPARE(copied.readAll(),QByteArray("source"));
        QCOMPARE(QFileInfo::exists(base+"/source/"+file),operation==Fusion::TransferOperation::Copy);
      }
      QVERIFY(QFileInfo::exists(base+"/target/Folder/keep.txt"));
      QVERIFY(QFileInfo::exists(base+"/target/Folder/new.txt"));
      QVERIFY(!QFileInfo::exists(base+"/target/Folder_copy1"));
      QVERIFY(!QFileInfo::exists(base+"/target/first_copy1.txt"));
    }
  }
  void socketOmissionsDoNotOpenQueueOrDiscardOrdinaryFiles() {
    QTemporaryDir temporarySocket("/tmp/fusion-socket-XXXXXX"); QVERIFY(temporarySocket.isValid());
    const auto base=temporarySocket.path();
    QDir().mkpath(base+"/source"); QDir().mkpath(base+"/target");
    QLocalServer endpoint; QVERIFY(endpoint.listen(base+"/source/bus_100"));
    write(base+"/source/ordinary.sock","real data with a socket-like name");
    QVERIFY(QFile::link(base+"/source/bus_100",base+"/source/socket-link"));
    QWidget owner;
    auto *job=Fusion::transferFiles({QUrl::fromLocalFile(base+"/source")},QUrl::fromLocalFile(base+"/target"),Fusion::TransferOperation::Copy,&owner);
    int error=-1; connect(job,&KJob::result,&owner,[&](KJob *result){error=result->error();});
    QTRY_COMPARE_WITH_TIMEOUT(error,0,10000);
    QVERIFY(!queueFor(base));
    QVERIFY(QFileInfo::exists(base+"/source/bus_100"));
    QVERIFY(!QFileInfo::exists(base+"/target/source/bus_100"));
    QFile copied(base+"/target/source/ordinary.sock"); QVERIFY(copied.open(QIODevice::ReadOnly));
    QCOMPARE(copied.readAll(),QByteArray("real data with a socket-like name"));
    QVERIFY(QFileInfo(base+"/target/source/socket-link").isSymbolicLink());
    QCOMPARE(QFileInfo(base+"/target/source/socket-link").symLinkTarget(),base+"/source/bus_100");
  }
  void specialFilesQueueWithoutBlockingNormalCopies() {
    const auto base=folder+"/queued-special-files";
    QDir().mkpath(base+"/source"); QDir().mkpath(base+"/target");
    QCOMPARE(::mkfifo(QFile::encodeName(base+"/source/control-a.pipe"),0600),0);
    QCOMPARE(::mkfifo(QFile::encodeName(base+"/source/control-b.pipe"),0600),0);
    write(base+"/source/normal.txt","ordinary files keep copying");
    QWidget owner;
    auto *job=Fusion::transferFiles({QUrl::fromLocalFile(base+"/source")},QUrl::fromLocalFile(base+"/target"),Fusion::TransferOperation::Copy,&owner);
    int error=-1; connect(job,&KJob::result,&owner,[&](KJob *result){error=result->error();});
    QTRY_VERIFY(queueFor(base)); auto *queue=queueFor(base);
    QCOMPARE(queue->windowHandle()->transientParent(), owner.windowHandle());
    QVERIFY(!queue->parentWidget()); // The transfer must outlive its browser.
    QVERIFY(queue->width() <= 980); QVERIFY(queue->height() <= 540);
    QTRY_VERIFY(QFileInfo::exists(base+"/target/source/normal.txt"));
    auto *table=queue->findChild<QTableView *>("transferIssuesTable");
    QTRY_COMPARE(table->model()->rowCount(),2); QCOMPARE(error,-1);
    QVERIFY(!queue->isModal()); queue->hide(); QTest::qWait(50); QCOMPARE(error,-1);
    queue->reveal();
    if(qEnvironmentVariableIsSet("FUSION_FILES_CAPTURE")) queue->grab().save(qEnvironmentVariable("FUSION_FILES_CAPTURE")+"-queue.png");
    table->selectRow(0); queue->findChild<QCheckBox *>("similarTransferIssues")->setChecked(true);
    QVERIFY(!queue->findChild<QPushButton *>("transferIssue_retry")->isEnabled());
    QVERIFY(!queue->findChild<QPushButton *>("transferIssue_authorize")->isEnabled());
    QVERIFY(queue->findChild<QLabel *>("transferIssueHint")->text().contains("cannot be copied"));
    QCOMPARE(queue->findChild<QPushButton *>("transferIssue_skip")->text(),QString("Skip similar"));
    queue->findChild<QPushButton *>("transferIssue_skip")->click();
    QTRY_COMPARE_WITH_TIMEOUT(error,0,10000);
    QVERIFY(QFileInfo::exists(base+"/source/control-a.pipe"));
    QVERIFY(!QFileInfo::exists(base+"/target/source/control-a.pipe"));
    for(int n=0;n<2;++n) QCOMPARE(table->model()->index(n,2).data().toString(),QString("Skipped / original kept"));
    QCOMPARE(queue->findChild<QLabel *>("transferQueueHeading")->text(),QString("Completed with skipped items"));
    QVERIFY(queue->findChild<QLabel *>("transferQueueSummary")->text().contains("1 file copied"));
    QVERIFY(queue->findChild<QLabel *>("transferQueueSummary")->text().contains("2 items skipped"));
    const auto report=base+"/queue-report.txt";
    QTimer::singleShot(0,queue,[queue,report]{
      for(auto *dialog:queue->findChildren<QFileDialog *>()) {
        dialog->selectFile(report); QMetaObject::invokeMethod(dialog,"accept",Qt::QueuedConnection);
      }
    });
    queue->findChild<QPushButton *>("saveTransferReport")->click();
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(report),10000);
    QFile saved(report); QVERIFY(saved.open(QIODevice::ReadOnly));
    const auto contents=saved.readAll(); QVERIFY(contents.contains("control-a.pipe")); QVERIFY(contents.contains("control-b.pipe"));
    queue->close();
  }
  void transferQueueShowsAuthenticationStateAndRecoversAfterRefusal() {
    Fusion::NativeTransfer operation({});
    QWidget owner;
    Fusion::TransferIssues queue(&operation, &owner);
    QVariantMap issue{{"id",1},{"source",folder+"/private"},{"destination",folder+"/target/private"},
        {"stage","item"},{"category","item:permission"},{"detail","Permission denied"},{"version",1},
        {"status","authorizing"}};
    emit operation.issue(issue);
    emit operation.progress({{"administratorAccess","authorizing"},{"pendingIssues",1},{"phase","Copying"}});
    auto *status=queue.findChild<QLabel *>("transferAdministratorStatus");
    auto *button=queue.findChild<QPushButton *>("transferIssue_authorize");
    auto *table=queue.findChild<QTableView *>("transferIssuesTable");
    QVERIFY(!queue.isModal()); QVERIFY(status->isVisible()); QVERIFY(!button->isEnabled());
    QCOMPARE(table->model()->index(0,2).data().toString(),QString("Awaiting authorization"));
    issue["status"]="pending"; issue["version"]=2;
    emit operation.issue(issue);
    emit operation.progress({{"administratorAccess","failed"},{"administratorError","Authentication cancelled"}});
    QVERIFY(button->isEnabled()); QVERIFY(status->text().contains("Authentication cancelled"));
    emit operation.progress({{"administratorAccess","authorized"},{"administratorError",""}});
    QVERIFY(status->text().contains("access is active"));
  }
  void transferQueueShowsSuccessWhileOtherItemsAwaitChoices() {
    struct CompletedTransfer : Fusion::NativeTransfer {
      CompletedTransfer() : NativeTransfer({}) { setAutoDelete(false); }
      void complete() { emitResult(); }
    } operation;
    Fusion::TransferIssues queue(&operation);
    QVariantMap copied{{"id",1},{"source",folder+"/win10.xml"},{"destination",folder+"/target/win10.xml"},
        {"stage","item"},{"category","item:permission"},{"detail","Permission denied"},{"version",1},
        {"status","retry"}};
    emit operation.issue(copied);
    QVariantMap endpoint{{"id",2},{"source",folder+"/vm.sock"},{"destination",folder+"/target/vm.sock"},
        {"stage","item"},{"category","item:socket"},{"detail","This socket has no ordinary file contents to copy."},
        {"version",1},{"status","pending"},{"retry_allowed",false}};
    emit operation.issue(endpoint);
    copied["status"]="resolved"; copied["resolution"]="Copied successfully";
    emit operation.issue(copied);
    emit operation.progress({{"processedFiles",1},{"pendingIssues",1},{"phase","Waiting for queued items"}});
    auto *table=queue.findChild<QTableView *>("transferIssuesTable");
    QCOMPARE(table->model()->index(0,2).data().toString(),QString("Copied successfully"));
    QVERIFY(!table->model()->index(0,1).data().toString().contains("Permission denied"));
    QVERIFY(table->model()->index(0,2).data(Qt::DecorationRole).isValid());
    QVERIFY(queue.findChild<QLabel *>("transferQueueSummary")->text().contains("1 item needs a choice"));
    QVERIFY(queue.findChild<QPlainTextEdit *>("transferIssueDetails")->toPlainText().contains("Original issue: Permission denied"));
    table->selectAll();
    QVERIFY(!queue.findChild<QPushButton *>("transferIssue_retry")->isEnabled());
    QVERIFY(!queue.findChild<QPushButton *>("transferIssue_authorize")->isEnabled());
    auto *skip=queue.findChild<QPushButton *>("transferIssue_skip");
    QVERIFY(skip->isEnabled()); QCOMPARE(skip->text(),QString("Skip item")); // The successful copy is excluded.
    endpoint["status"]="skipped"; emit operation.issue(endpoint);
    emit operation.progress({{"processedFiles",1},{"skippedFiles",1},{"pendingIssues",0},{"phase","Finishing"}});
    operation.complete();
    QCOMPARE(table->model()->index(0,2).data().toString(),QString("Copied successfully"));
    QCOMPARE(table->model()->index(1,2).data().toString(),QString("Skipped / original kept"));
    QCOMPARE(queue.findChild<QLabel *>("transferQueueHeading")->text(),QString("Completed with skipped items"));
    QVERIFY(queue.findChild<QLabel *>("transferQueueSummary")->text().contains("1 file copied"));
    QVERIFY(queue.findChild<QLabel *>("transferQueueSummary")->text().contains("1 item skipped"));
    QVERIFY(!skip->isEnabled());
    auto *summary=queue.findChild<QLabel *>("transferQueueSummary");
    QTRY_VERIFY(summary->height() >= 2*summary->fontMetrics().height());
    if(qEnvironmentVariableIsSet("FUSION_FILES_CAPTURE")) queue.grab().save(qEnvironmentVariable("FUSION_FILES_CAPTURE")+"-completed-queue.png");
  }
  void skipConflictsStillTransfersNewFilesInsideMatchingFolders() {
    for (const auto operation : {Fusion::TransferOperation::Copy,Fusion::TransferOperation::Move}) {
      const auto base=folder+"/skip-conflicts-"+QString::number(int(operation));
      for (const auto side : {"source","target"}) {
        QDir().mkpath(base+"/"+side+"/Folder/nested/deeper");
        for (const auto file : {"first.txt","Folder/a.txt","Folder/nested/deeper/b.txt"})
          write(base+"/"+side+"/"+file,QByteArray(side));
      }
      write(base+"/source/Folder/new.txt","new source only");
      write(base+"/source/Folder/nested/deeper/new.txt","new source only");
      QWidget owner;int prompts=0;
      QTimer answer;connect(&answer,&QTimer::timeout,&owner,[&]{
        if (!QFileInfo::exists(base+"/target/Folder/nested/deeper/new.txt")) return;
        if (answerQueue(base,"skip")) ++prompts;
      });answer.start(10);
      auto *job=Fusion::transferFiles({QUrl::fromLocalFile(base+"/source/Folder"),QUrl::fromLocalFile(base+"/source/first.txt")},
          QUrl::fromLocalFile(base+"/target"),operation,&owner);
      int error=-1;connect(job,&KJob::result,&owner,[&](KJob *j){error=j->error();});
      QTRY_COMPARE_WITH_TIMEOUT(error,0,15000);QVERIFY(prompts>=1);
      for (const auto file : {"first.txt","Folder/a.txt","Folder/nested/deeper/b.txt"}) {
        QFile existing(base+"/target/"+file);QVERIFY(existing.open(QIODevice::ReadOnly));QCOMPARE(existing.readAll(),QByteArray("target"));
        QVERIFY(QFileInfo::exists(base+"/source/"+file));
      }
      for (const auto file : {"Folder/new.txt","Folder/nested/deeper/new.txt"}) {
        QFile copied(base+"/target/"+file);QVERIFY(copied.open(QIODevice::ReadOnly));QCOMPARE(copied.readAll(),QByteArray("new source only"));
        QCOMPARE(QFileInfo::exists(base+"/source/"+file),operation==Fusion::TransferOperation::Copy);
      }
      QVERIFY(!QFileInfo::exists(base+"/target/Folder_copy1"));
    }
  }
  void sameFolderDropAsksAndKeepsNumberedCopies() {
    const auto base=folder+"/duplicate-drop";QDir().mkpath(base+"/Folder");
    write(base+"/Folder/inside.txt","inside");write(base+"/bundle.tar.gz","archive");
    QMimeData mime;mime.setUrls({QUrl::fromLocalFile(base+"/Folder"),QUrl::fromLocalFile(base+"/bundle.tar.gz")});
    QWidget owner;
    for (int attempt=0;attempt<3;++attempt) {
      QDropEvent event(QPointF(1,1),Qt::MoveAction|Qt::CopyAction,&mime,Qt::LeftButton,Qt::NoModifier);
      auto *job=Fusion::dropFiles(&event,QUrl::fromLocalFile(base),&owner,{});
      int error=-1;connect(job,&KJob::result,&owner,[&](KJob *j){error=j->error();});
      QTRY_VERIFY(owner.findChild<QMessageBox *>("duplicateDropQuestion"));
      auto *question=owner.findChild<QMessageBox *>("duplicateDropQuestion");
      QTRY_VERIFY(question->isVisible());
      question->done(attempt==0?QMessageBox::Cancel:QMessageBox::Yes);
      QTRY_COMPARE_WITH_TIMEOUT(error,attempt==0?KIO::ERR_USER_CANCELED:0,10000);
      QVERIFY(QFileInfo::exists(base+"/Folder/inside.txt"));QVERIFY(QFileInfo::exists(base+"/bundle.tar.gz"));
      if (!attempt) QVERIFY(!QFileInfo::exists(base+"/Folder_copy1"));
      else {
        QVERIFY(QFileInfo::exists(base+"/Folder_copy"+QString::number(attempt)+"/inside.txt"));
        QVERIFY(QFileInfo::exists(base+"/bundle_copy"+QString::number(attempt)+".tar.gz"));
      }
      QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);
    }
  }
  void arkServiceDropsReachFoldersWithoutUriLists() {
    const auto base=folder+"/ark-drop";QDir().mkpath(base+"/Extract here");
    TestArkExtract ark;auto bus=QDBusConnection::sessionBus();
    QVERIFY(bus.registerObject("/FusionTestArk",&ark,QDBusConnection::ExportAllSlots));
    auto cleanup=qScopeGuard([&]{bus.unregisterObject("/FusionTestArk");});
    QMimeData mime;mime.setData("application/x-kde-ark-dndextract-service",bus.baseService().toUtf8());
    mime.setData("application/x-kde-ark-dndextract-path","/FusionTestArk");QVERIFY(!mime.hasUrls());
    FilesWindow window(QUrl::fromLocalFile(base),false,temporary.path()+"/ark-drop.ini");
    window.setAttribute(Qt::WA_DeleteOnClose,false);window.show();auto *tab=window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(),1);
    for (int mode : {2,3,4}) {
      tab->setView(mode);ark.destination.clear();
      auto index=tab->proxy->index(0,0);const auto point=filePoint(tab,index);
      QDragEnterEvent enter(point,Qt::CopyAction,&mime,Qt::LeftButton,Qt::NoModifier);
      QApplication::sendEvent(tab->view()->viewport(),&enter);QVERIFY(enter.isAccepted());QCOMPARE(enter.dropAction(),Qt::CopyAction);
      QDropEvent drop(point,Qt::CopyAction,&mime,Qt::LeftButton,Qt::NoModifier);
      QApplication::sendEvent(tab->view()->viewport(),&drop);QVERIFY(drop.isAccepted());
      QTRY_COMPARE(ark.destination,base+"/Extract here");
    }
  }
  void folderViewMenuTracksTabsAndKeepsComputerCards() {
    FilesWindow window(QUrl::fromLocalFile(folder),false,temporary.path()+"/view-menu.ini");
    window.setAttribute(Qt::WA_DeleteOnClose,false);window.show();
    auto *button=window.findChild<QToolButton *>("viewMode");QVERIFY(button);QVERIFY(button->isEnabled());
    QCOMPARE(button->menu()->actions().size(),5);
    for (auto *action : button->menu()->actions()) {
      action->trigger();QCOMPARE(window.browser()->viewMode,action->data().toInt());QVERIFY(action->isChecked());
      QVERIFY(button->toolTip().contains(action->text()));
    }
    window.openLocation(Fusion::computerUrl(),true);QVERIFY(!button->isEnabled());
    QVERIFY(window.browser()->findChild<QWidget *>("computerPage")->isVisible());
    window.openLocation(QUrl::fromLocalFile(folder));QVERIFY(button->isEnabled());
    QCOMPARE(window.browser()->viewMode,4);QVERIFY(window.browser()->details->isVisible());
  }
  void sidebarFolderDropsTransferInsteadOfPinning() {
    const auto base=folder+"/sidebar-drop";QDir().mkpath(base+"/target");
    write(base+"/item.txt","sidebar contents");
    const auto preferences=temporary.path()+"/sidebar-drop.ini";
    Fusion::Preferences settings(preferences);
    auto bookmarks=settings.places();
    bookmarks.append(QVariantMap{{"name","Drop target"},{"url",QUrl::fromLocalFile(base+"/target").toString()},{"icon","folder"}});
    settings.setPlaces(bookmarks);
    FilesWindow window(QUrl::fromLocalFile(base),false,preferences);
    window.setAttribute(Qt::WA_DeleteOnClose,false);window.show();
    auto *tree=window.findChild<QTreeWidget *>("places");
    auto matches=tree->findItems("Drop target",Qt::MatchExactly|Qt::MatchRecursive);QCOMPARE(matches.size(),1);
    tree->scrollToItem(matches.first());
    const auto point=tree->visualItemRect(matches.first()).center();
    QMimeData mime;mime.setUrls({QUrl::fromLocalFile(base+"/item.txt")});
    QDragEnterEvent enter(QPointF(point),Qt::MoveAction|Qt::CopyAction,&mime,Qt::LeftButton,Qt::NoModifier);
    QApplication::sendEvent(tree->viewport(),&enter);QVERIFY(enter.isAccepted());
    QSignalSpy finished(&window,&FilesWindow::operationFinished);
    QDropEvent drop(point,Qt::MoveAction|Qt::CopyAction,&mime,Qt::LeftButton,Qt::NoModifier);
    QApplication::sendEvent(tree->viewport(),&drop);QVERIFY(drop.isAccepted());QCOMPARE(drop.dropAction(),Qt::MoveAction);
    QTRY_COMPARE_WITH_TIMEOUT(finished.count(),1,10000);QCOMPARE(finished.first().first().toInt(),0);
    QVERIFY(!QFileInfo::exists(base+"/item.txt"));QVERIFY(QFileInfo::exists(base+"/target/item.txt"));
    QCOMPARE(Fusion::Preferences(preferences).places(),bookmarks);
  }
  void cancelTransferBeforeStartingChangesNothing() {
    const auto base = folder + "/cancel-before-start";
    QDir().mkpath(base + "/target"); write(base + "/file", "untouched");
    auto *job = Fusion::transferFiles({QUrl::fromLocalFile(base + "/file")},
        QUrl::fromLocalFile(base + "/target"), Fusion::TransferOperation::Move, nullptr);
    QVERIFY(job->kill());
    QTest::qWait(80);
    QVERIFY(QFileInfo::exists(base + "/file"));
    QVERIFY(!QFileInfo::exists(base + "/target/file"));
  }
  void administratorTransfers() {
    if (geteuid() != 0 || !qEnvironmentVariableIsSet("FUSION_FILES_ADMIN_CHECK"))
      QSKIP("Explicit root-fixture check, using the installed admin worker on a private session bus.");
    // Only the QTemporaryDir owned by this test is touched. No policy rules,
    // desktop preferences, or real protected user files are changed.
    const auto base = folder + "/administrator";
    QDir().mkpath(base + "/source/private"); QDir().mkpath(base + "/target");
    write(base + "/source/private/item # 100%.txt", "protected content");
    ::chmod(QFile::encodeName(base + "/source/private"), 0700);
    auto admin = [](const QString &path) { auto url = QUrl::fromLocalFile(path); url.setScheme("admin"); return url; };
    QWidget window;
    QTimer answer;connect(&answer,&QTimer::timeout,&window,[&]{
      auto *question=window.findChild<QDialog *>("transferConflictSummary");
      if (question && question->isVisible()) question->done(1);
    });answer.start(10);
    for (int n = 0; n < 2; ++n) {
      auto *job = Fusion::transferFiles({admin(base + "/source/private")}, QUrl::fromLocalFile(base + "/target"),
          Fusion::TransferOperation::Copy, &window);
      int error = -1; QString message;
      connect(job, &KJob::result, &window, [&](KJob *result) { error = result->error(); message = result->errorString(); });
      QTRY_VERIFY_WITH_TIMEOUT(error != -1, 15000);
      QVERIFY2(!error, qPrintable(message));
    }
    QFile copied(base + "/target/private/item # 100%.txt");
    QVERIFY(copied.open(QIODevice::ReadOnly)); QCOMPARE(copied.readAll(), QByteArray("protected content")); copied.close();
    write(base + "/source/move.txt", "move this"); write(base + "/target/other.txt", "keep this");
    auto *mime = new QMimeData; mime->setUrls({QUrl::fromLocalFile(base + "/source/move.txt")});
    KIO::setClipboardDataCut(mime, true); QApplication::clipboard()->setMimeData(mime);
    auto *move = Fusion::pasteFiles(admin(base + "/target"), &window);
    int error = -1; QString message;
    connect(move, &KJob::result, &window, [&](KJob *result) { error = result->error(); message = result->errorString(); });
    QTRY_VERIFY_WITH_TIMEOUT(error != -1, 15000);
    QVERIFY2(!error, qPrintable(message));
    QVERIFY(!QFileInfo::exists(base + "/source/move.txt"));
    QVERIFY(QFileInfo::exists(base + "/target/move.txt"));
    QCOMPARE(QApplication::clipboard()->mimeData()->urls(), QList<QUrl>{QUrl::fromLocalFile(base + "/target/move.txt")});
    QVERIFY(!KIO::isClipboardDataCut(QApplication::clipboard()->mimeData()));
    KIO::FileUndoManager::self()->undo();
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(base + "/source/move.txt"), 15000);
    QVERIFY(!QFileInfo::exists(base + "/target/move.txt"));
  }
  void customCommandsKeepFilenamesAsArguments() {
    const QString name = folder + "/a;$(touch sentinel) 'quote' %u.txt";
    const auto urls = QList<QUrl>{QUrl::fromLocalFile(name),
                                  QUrl::fromLocalFile(folder + "/second file")};
    QCOMPARE(Fusion::expandCommand("viewer -- %F", urls),
             QStringList({"viewer", "--", name, folder + "/second file"}));
    QCOMPARE(Fusion::expandCommand("viewer %f", urls),
             QStringList({"viewer", name}));
    QVERIFY(Fusion::expandCommand("viewer --files=%F", urls).isEmpty());
    QVERIFY(
        Fusion::expandCommand("viewer %F", {QUrl("smb://server/share/file")})
            .isEmpty());
  }
  void drivesIncludeUnmountedAndPreserveMountPaths() {
    const QByteArray json =
        R"({"blockdevices":[{"name":"nvme0n1","path":"/dev/nvme0n1","type":"disk","size":10000,"children":[{"name":"nvme0n1p1","path":"/dev/nvme0n1p1","type":"part","fstype":"ext4","label":"System","uuid":"aaa","size":4000,"mountpoints":["/"]},{"name":"nvme0n1p2","path":"/dev/nvme0n1p2","type":"part","fstype":"ntfs","label":"Windows","size":6000,"mountpoints":[null]}]},{"name":"sdb1","path":"/dev/sdb1","type":"part","fstype":"exfat","label":"USB","size":500,"rm":true,"mountpoints":["/run/media/fixture/My USB"]},{"name":"loop0","type":"loop","fstype":"squashfs","size":2}]})";
    const auto volumes = Drives::parse(json);
    QCOMPARE(volumes.size(), 3);
    QCOMPARE(volumes[0].mount, QString("/"));
    auto windows =
        std::find_if(volumes.begin(), volumes.end(),
                     [](const Volume &v) { return v.name == "Windows"; });
    QVERIFY(windows != volumes.end());
    QVERIFY(!windows->mounted());
    QVERIFY(windows->mountable());
    auto usb = std::find_if(volumes.begin(), volumes.end(),
                            [](const Volume &v) { return v.name == "USB"; });
    QVERIFY(usb != volumes.end());
    QVERIFY(usb->removable);
    QCOMPARE(usb->mount, QString("/run/media/fixture/My USB"));
    QCOMPARE(FusionVolumes::mount("/dev/sdb1", true),
             QStringList({"mount", "-b", "/dev/sdb1", "-o", "force"}));
    const auto encrypted = Drives::parse(
        R"({"blockdevices":[{"name":"sdc1","type":"part","fstype":"BitLocker","mountpoints":[null]},{"name":"sdd1","type":"part","fstype":"crypto_LUKS","mountpoints":[null]}]})");
    QCOMPARE(encrypted.size(), 2);
    for (const auto &volume : encrypted) {
      QVERIFY(volume.locked());
      QVERIFY(!volume.mountable());
    }
  }
  void privatePreferencesRoundTrip() {
    const QString path = temporary.path() + "/prefs/settings.ini";
    Fusion::Preferences settings(path);
    auto bookmarks = settings.places();
    QVERIFY(!bookmarks.isEmpty());
    bookmarks.append({{"name", "Private shortcut"},
                      {"url", QUrl::fromLocalFile(folder).toString()},
                      {"icon", "folder"}});
    settings.setPlaces(bookmarks);
    auto menu = settings.menu();
    menu[0]["enabled"] = false;
    settings.setMenu(menu);
    Fusion::Preferences restored(path);
    QCOMPARE(restored.places(), bookmarks);
    QCOMPARE(restored.menu(), menu);
  }
  void physicalDriveAncestry() {
    const auto volumes = computerVolumes();
    QCOMPARE(volumes.size(), 6);
    for (const auto &volume : volumes) {
      QVERIFY(!volume.driveKey().isEmpty());
      if (volume.device.startsWith("/dev/fusion-a")) {
        QCOMPARE(volume.driveKey(), QString("/dev/fusion-a"));
        QCOMPARE(volume.driveModel, QString("Fusion NVMe"));
        QCOMPARE(volume.driveSize, 1000000000000ULL);
      }
      if (volume.device == "/dev/fusion-c1") {
        QVERIFY(volume.usb());
        QVERIFY(!volume.removable);
        QCOMPARE(volume.transport, QString("usb"));
      }
    }
    const auto shared = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/a","type":"disk","children":[{"path":"/dev/md0","type":"raid1","fstype":"ext4","mountpoints":["/mnt/data"]}]},
      {"path":"/dev/b","type":"disk","children":[{"path":"/dev/md0","type":"raid1","fstype":"ext4","mountpoints":["/mnt/data"]}]}
    ]})");
    QCOMPARE(shared.size(), 1);
    QCOMPARE(shared.first().driveKey(), QString("/dev/md0"));
    QCOMPARE(shared.first().driveModel, QString("Multiple backing disks"));
  }
  void mountedRowsSidebarAndSplitter() {
    FilesWindow window(Fusion::computerUrl(), false,
                       temporary.path() + "/drive-layout.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.resize(1000, 900);
    window.show();
    window.drives->volumes = computerVolumes();
    emit window.drives->changed();
    auto *tab = window.browser();
    auto group = [tab](const QString &key) -> QWidget * {
      for (auto *widget : driveGroups(tab, "mountedDrives"))
        if (widget->property("driveKey").toString() == key)
          return widget;
      return nullptr;
    };
    QTRY_VERIFY(group("/dev/fusion-a"));
    QCOMPARE(driveGroups(tab, "mountedDrives").size(), 2);
    auto *row = group("/dev/fusion-a")->findChild<QListWidget *>();
    QCOMPARE(row->count(), 3);
    QVERIFY(!row->isWrapping());
    QCOMPARE(row->item(0)->data(Qt::UserRole).value<Volume>().device, QString("/dev/fusion-a2"));
    QCOMPARE(row->item(1)->data(Qt::UserRole).value<Volume>().device, QString("/dev/fusion-a3"));
    QCOMPARE(row->item(2)->data(Qt::UserRole).value<Volume>().device, QString("/dev/fusion-a1"));
    QVERIFY(!row->item(1)->data(Qt::UserRole).value<Volume>().mounted());
    QVERIFY(driveGroups(tab, "unmountedDrives").isEmpty());
    QCOMPARE(driveRow(tab, "/dev/fusion-c")->count(), 2);
    auto *places = window.findChild<QTreeWidget *>("places");
    auto sidebar = [places](const QString &name) -> QTreeWidgetItem * {
      for (int i = 0; i < places->topLevelItemCount(); ++i)
        if (places->topLevelItem(i)->text(0) == name)
          return places->topLevelItem(i);
      return nullptr;
    };
    QVERIFY(sidebar("This PC"));
    QCOMPARE(sidebar("This PC")->childCount(), 4);
    QVERIFY(sidebar("Unmounted drives"));
    QCOMPARE(sidebar("Unmounted drives")->childCount(), 2);
    QVERIFY(sidebar("Unmounted drives")->isExpanded());
    QVERIFY(places->indexOfTopLevelItem(sidebar("Unmounted drives")) >
            places->indexOfTopLevelItem(sidebar("Trash")));
    sidebar("Unmounted drives")->setExpanded(false);
    row->setCurrentRow(0);
    row->setFocus();
    const auto selected = tab->selectedVolume().device;
    emit window.drives->changed();
    QCOMPARE(group("/dev/fusion-a")->findChild<QListWidget *>(), row);
    QCOMPARE(tab->selectedVolume().device, selected);
    QVERIFY(!sidebar("Unmounted drives")->isExpanded());
    auto *splitter = tab->findChild<QSplitter *>("driveSections");
    QCOMPARE(splitter->orientation(), Qt::Vertical);
    QTest::qWait(100);
    auto *handle = splitter->handle(1);
    const auto middle = handle->rect().center();
    QTest::mousePress(handle, Qt::LeftButton, Qt::NoModifier, middle);
    QTest::mouseMove(handle, middle + QPoint(0, 35), 20);
    QTest::mouseRelease(handle, Qt::LeftButton, Qt::NoModifier,
                        middle + QPoint(0, 35));
    QVERIFY(!window.preferences.settings.value("computerSections")
                 .toByteArray()
                 .isEmpty());
    const auto sizes = splitter->sizes();
    emit window.drives->changed();
    QCOMPARE(splitter->sizes(), sizes);
    window.resize(800, 900);
    QTRY_VERIFY(row->horizontalScrollBar()->maximum() > 0);
    QCOMPARE(row->visualItemRect(row->item(0)).y(),
             row->visualItemRect(row->item(1)).y());
    row->horizontalScrollBar()->setValue(80);
    emit window.drives->changed();
    QTest::qWait(30);
    QCOMPARE(row->horizontalScrollBar()->value(), 80);
    window.activateWindow();
    row->setFocus();
    QTest::keyClick(row, Qt::Key_Return, Qt::AltModifier);
    QTRY_VERIFY(window.findChild<DriveProperties *>());
    auto *properties = window.findChild<DriveProperties *>();
    QCOMPARE(properties->findChild<QLabel *>("volumeDevice")->text(), selected);
    properties->close();
    QTRY_VERIFY(!window.findChild<DriveProperties *>());
    places->setCurrentItem(sidebar("This PC")->child(0));
    window.activateWindow();
    places->setFocus();
    QTRY_VERIFY(window.isActiveWindow());
    QTRY_VERIFY(places->hasFocus());
    QTest::keyClick(places, Qt::Key_Return, Qt::AltModifier);
    QTRY_VERIFY(window.findChild<DriveProperties *>());
    window.findChild<DriveProperties *>()->close();
    QTRY_VERIFY(!window.findChild<DriveProperties *>());
    for (auto &volume : window.drives->volumes)
      if (volume.device == "/dev/fusion-a3")
        volume.mount = "/media/Windows";
    emit window.drives->changed();
    QCOMPARE(row->count(), 3);
    QVERIFY(driveGroups(tab, "unmountedDrives").isEmpty());
    QCOMPARE(sidebar("This PC")->childCount(), 5);
    window.activateWindow();
    row->setFocus();
    QTRY_VERIFY(row->hasFocus());
    for (auto &volume : window.drives->volumes)
      if (volume.driveKey() == "/dev/fusion-a")
        volume.mount.clear();
    emit window.drives->changed();
    QVERIFY(!group("/dev/fusion-a"));
    QCOMPARE(driveGroups(tab, "unmountedDrives").size(), 1);
    QCOMPARE(driveRow(tab, "/dev/fusion-a"), row);
    QCOMPARE(row->count(), 3);
    QTRY_VERIFY(row->hasFocus());
    QCOMPARE(sidebar("This PC")->childCount(), 2);
    window.drives->volumes.clear();
    emit window.drives->changed();
    QCOMPARE(driveGroups(tab, "mountedDrives").size(), 0);
    QVERIFY(driveGroups(tab, "unmountedDrives").isEmpty());
    QVERIFY(driveGroups(tab, "usbDrives").isEmpty());
    QVERIFY(!sidebar("Unmounted drives"));
    window.close();
  }
  void mountedSectionFitsOnMountAndShrinksOnUnmount() {
    FilesWindow window(Fusion::computerUrl(), false,
                       temporary.path() + "/automatic-drive-layout.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.resize(1200, 1200); window.show();
    window.drives->volumes = computerVolumes();
    for (auto &volume : window.drives->volumes)
      if (volume.driveKey() == "/dev/fusion-b") volume.mount.clear();
    emit window.drives->changed();
    auto *tab = window.browser();
    auto *splitter = tab->findChild<QSplitter *>("driveSections");
    auto *mounted = tab->findChild<QScrollArea *>("mountedDrives");
    auto *row = driveRow(tab, "/dev/fusion-b");
    row->setCurrentRow(0); row->setFocus();
    QTest::qWait(100);
    const int original = splitter->sizes()[0];
    for (auto &volume : window.drives->volumes)
      if (volume.driveKey() == "/dev/fusion-b") volume.mount = "/media/Projects";
    emit window.drives->changed();
    QTRY_VERIFY(splitter->sizes()[0] > original + 100);
    QTRY_COMPARE(mounted->verticalScrollBar()->maximum(), 0);
    QCOMPARE(driveRow(tab, "/dev/fusion-b"), row);
    QCOMPARE(tab->selectedVolume().device, QString("/dev/fusion-b1"));
    auto verifyVisible = [&] {
      for (auto *group : driveGroups(tab, "mountedDrives")) {
        const QPoint bottom = group->mapTo(mounted->viewport(), group->rect().bottomRight());
        QVERIFY2(bottom.y() < mounted->viewport()->height(), "Mounted drive is below the visible pane");
      }
    };
    verifyVisible();
    // A saved small pane or dragging the handle cannot conceal mounted rows
    // while the surrounding window has room for them.
    splitter->setSizes({1, 200, 800}); QTest::qWait(40);
    verifyVisible();
    const auto stable = splitter->sizes();
    emit window.drives->changed(); QTest::qWait(40);
    QCOMPARE(splitter->sizes(), stable);
    // Content minima adapt instead of forcing the window beyond the screen.
    window.resize(800, 480);
    QTRY_VERIFY(window.height() <= 480);
    QTRY_VERIFY(tab->findChild<QScrollArea *>("computerDrivesScroll")->verticalScrollBar()->maximum() > 0);
    QTRY_COMPARE(mounted->verticalScrollBar()->maximum(), 0);
    window.resize(1200, 1200);
    QTRY_COMPARE(mounted->verticalScrollBar()->maximum(), 0);
    verifyVisible();
    for (auto &volume : window.drives->volumes)
      if (volume.driveKey() == "/dev/fusion-b") volume.mount.clear();
    emit window.drives->changed();
    // The outer scrollbar can change available width by a few pixels; the
    // pane still returns to one row and every card must remain visible.
    QTRY_VERIFY(qAbs(splitter->sizes()[0] - original) < 10);
    verifyVisible();
    QCOMPARE(driveGroups(tab, "mountedDrives").size(), 1);
    QCOMPARE(driveRow(tab, "/dev/fusion-b"), row);
    window.close();
  }
  void everyDriveSectionFitsItsRowsAfterHotplug() {
    FilesWindow window(Fusion::computerUrl(), false, temporary.path() + "/all-drive-layout.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.resize(1200, 900); window.show();
    window.drives->volumes = computerVolumes();
    auto *tab = window.browser();
    auto *splitter = tab->findChild<QSplitter *>("driveSections");
    auto *scroll = tab->findChild<QScrollArea *>("computerDrivesScroll");
    auto verify = [&] {
      for (const QString &name : {"mountedDrives", "usbDrives", "unmountedDrives"}) {
        auto *section = tab->findChild<QScrollArea *>(name);
        if (driveGroups(tab, name).isEmpty()) continue;
        QTRY_COMPARE(section->verticalScrollBar()->maximum(), 0);
        for (auto *group : driveGroups(tab, name)) {
          const auto bottom = group->mapTo(section->viewport(), group->rect().bottomRight());
          QVERIFY2(bottom.y() < section->viewport()->height(), qPrintable(name + " clips a drive row"));
        }
      }
    };
    emit window.drives->changed(); QTest::qWait(80); verify();
    const int usbBefore = splitter->sizes()[1];
    window.drives->volumes.append(Drives::parse(R"({"blockdevices":[
      {"path":"/dev/fusion-usb-extra","type":"disk","tran":"usb","fstype":"exfat","size":32000000000,"mountpoints":[null]},
      {"path":"/dev/fusion-unmounted-extra","type":"disk","tran":"sata","fstype":"ext4","size":1000000000000,"mountpoints":[null]}
    ]})"));
    emit window.drives->changed();
    QTRY_VERIFY(splitter->sizes()[1] > usbBefore + 100); verify();
    splitter->setSizes({1, 1, 1}); QTest::qWait(60); verify();
    window.resize(800, 480);
    QTRY_VERIFY(window.height() <= 480);
    QTRY_VERIFY(scroll->verticalScrollBar()->maximum() > 0); verify();
    scroll->verticalScrollBar()->setValue(scroll->verticalScrollBar()->maximum());
    const auto position = scroll->verticalScrollBar()->value();
    emit window.drives->changed(); QTest::qWait(40);
    QCOMPARE(scroll->verticalScrollBar()->value(), position);
    window.close();
  }
  void sidebarExpansionSurvivesReopenAndReconnect() {
    const auto settings = temporary.path() + "/sidebar.ini";
    const QStringList names{"This PC", "Quick access", "Unmounted drives"};
    auto sections = [](FilesWindow &window) {
      QMap<QString, QTreeWidgetItem *> result;
      auto *tree = window.findChild<QTreeWidget *>("places");
      for (int i = 0; i < tree->topLevelItemCount(); ++i)
        result.insert(tree->topLevelItem(i)->text(0), tree->topLevelItem(i));
      return result;
    };
    {
      FilesWindow window(Fusion::computerUrl(), false, settings);
      window.setAttribute(Qt::WA_DeleteOnClose, false);
      window.drives->volumes = computerVolumes();
      emit window.drives->changed();
      for (const auto &name : names) {
        QVERIFY(sections(window).value(name));
        QVERIFY(sections(window).value(name)->isExpanded());
        sections(window).value(name)->setExpanded(false);
      }
      window.drives->volumes.clear();
      emit window.drives->changed();
      QVERIFY(!sections(window).contains("Unmounted drives"));
      window.drives->volumes = computerVolumes();
      emit window.drives->changed();
      for (const auto &name : names)
        QVERIFY(!sections(window).value(name)->isExpanded());
      window.close();
    }
    {
      FilesWindow reopened(Fusion::computerUrl(), false, settings);
      reopened.setAttribute(Qt::WA_DeleteOnClose, false);
      reopened.drives->volumes = computerVolumes();
      emit reopened.drives->changed();
      for (const auto &name : names)
        QVERIFY(!sections(reopened).value(name)->isExpanded());
      sections(reopened).value("Quick access")->setExpanded(true);
      reopened.close();
    }
    FilesWindow reopened(Fusion::computerUrl(), false, settings);
    reopened.drives->volumes = computerVolumes();
    emit reopened.drives->changed();
    QVERIFY(sections(reopened).value("Quick access")->isExpanded());
    QVERIFY(!sections(reopened).value("This PC")->isExpanded());
    QVERIFY(!sections(reopened).value("Unmounted drives")->isExpanded());
  }
  void unmountedDriveRowsAndThemeShapes() {
    Fusion::Preferences preferences(temporary.path() + "/physical-rows.ini");
    Drives drives(nullptr, false);
    Browser tab(&preferences, &drives);
    tab.resize(1000, 1000);
    tab.navigate(Fusion::computerUrl());
    tab.show();
    drives.volumes = computerVolumes();
    drives.volumes.append(Drives::parse(R"({"blockdevices":[
      {"path":"/dev/fusion-d","type":"disk","model":"Archive SSD","size":1000000000000,"children":[
        {"path":"/dev/fusion-d1","type":"part","fstype":"vfat","size":512000000},
        {"path":"/dev/fusion-d2","type":"part","fstype":"ext4","size":900000000000},
        {"path":"/dev/fusion-d3","type":"part","fstype":"swap","size":8000000000}]},
      {"path":"/dev/fusion-e","type":"disk","model":"Empty disk","size":2000000000000}
    ]})"));
    emit drives.changed();
    QCOMPARE(driveGroups(&tab, "unmountedDrives").size(), 2);
    auto *row = driveRow(&tab, "/dev/fusion-d");
    QVERIFY(row);
    QCOMPARE(row->count(), 3);
    const QStringList expected{"/dev/fusion-d2", "/dev/fusion-d3", "/dev/fusion-d1"};
    for (int i = 0; i < expected.size(); ++i) {
      QCOMPARE(row->item(i)->data(Qt::UserRole).value<Volume>().device, expected[i]);
      QTRY_COMPARE(row->visualItemRect(row->item(i)).y(), row->visualItemRect(row->item(0)).y());
    }
    QCOMPARE(driveRow(&tab, "/dev/fusion-e")->count(), 1);
    auto *frame = qobject_cast<QGroupBox *>(row->parentWidget());
    QVERIFY(frame);
    auto theme = [&](int radius) {
      // A new theme can supply any shape. Neither the disk frame nor its
      // painted partition cards should need a theme-name special case.
      tab.setStyleSheet(QString("QWidget {background:#101010;} QLabel {background:transparent;} "
                               "QGroupBox {background:#345678; border:1px solid #44ddcc; border-radius:%1px; margin:0; padding:0;}")
                           .arg(radius));
      QApplication::processEvents();
    };
    theme(0);
    const auto square = tab.grab().toImage();
    const auto squareCard = row->viewport()->grab().toImage();
    theme(24);
    const auto rounded = tab.grab().toImage();
    const auto roundedCard = row->viewport()->grab().toImage();
    const auto frameCorner = frame->mapTo(&tab, QPoint(3, 3));
    QVERIFY(square.pixelColor(frameCorner) != rounded.pixelColor(frameCorner));
    const auto corner = row->visualItemRect(row->item(0)).topLeft() + QPoint(7, 7);
    QVERIFY(squareCard.pixelColor(corner) != roundedCard.pixelColor(corner));
    tab.resize(700, 1000);
    QTRY_VERIFY(row->horizontalScrollBar()->maximum() > 0);
    row->setCurrentRow(0);
    row->horizontalScrollBar()->setValue(90);
    std::reverse(drives.volumes.begin(), drives.volumes.end());
    emit drives.changed();
    QCOMPARE(driveRow(&tab, "/dev/fusion-d"), row);
    QCOMPARE(tab.selectedVolume().device, expected.first());
    QCOMPARE(row->horizontalScrollBar()->value(), 90);
    for (int i = 0; i < expected.size(); ++i)
      QCOMPARE(row->item(i)->data(Qt::UserRole).value<Volume>().device, expected[i]);
  }
  void propertiesOpenSystemCleaner() {
    const auto originalRoot = qgetenv("XETAL_FILES_ROOT");
    const auto result = temporary.path() + "/cleaner-arguments";
    const auto root = temporary.path() + "/cleaner-profile";
    QVERIFY(QDir().mkpath(root + "/scripts"));
    const auto script = root + "/scripts/control-panel.sh";
    write(
        script,
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$FUSION_CLEANER_TEST_RESULT\"\n");
    QVERIFY(QFile::setPermissions(script, QFile::ReadOwner | QFile::WriteOwner |
                                              QFile::ExeOwner));
    const auto restore = qScopeGuard([&] {
      qputenv("XETAL_FILES_ROOT", originalRoot);
      qunsetenv("FUSION_CLEANER_TEST_RESULT");
    });
    qputenv("FUSION_CLEANER_TEST_RESULT", result.toUtf8());
    Drives drives(nullptr, false);
    DriveProperties dialog(computerVolumes().first(), &drives);
    dialog.show();
    qputenv("XETAL_FILES_ROOT", root.toUtf8());
    auto *button = dialog.findChild<QPushButton *>("systemCleaner");
    QVERIFY(button);
    QTest::mouseClick(button, Qt::LeftButton);
    QTRY_VERIFY(QFileInfo::exists(result));
    QFile arguments(result);
    QVERIFY(arguments.open(QIODevice::ReadOnly));
    QCOMPARE(arguments.readAll(), QByteArray("--section\ncleaner\n"));
  }
  void propertiesUsageAndUnavailableSpace() {
    Drives drives(nullptr, false);
    auto volume = computerVolumes().first();
    volume.name = "Projects <b> & 100% %10 backups";
    volume.size = volume.total = 1000;
    volume.available = 200;
    volume.freeBytes = 300;
    volume.spaceKnown = true;
    drives.volumes = {volume};
    DriveProperties dialog(volume, &drives);
    dialog.show();
    auto value = [&dialog](const QString &name) {
      return dialog.findChild<QLabel *>(name);
    };
    QCOMPARE(value("volumeHeading")->textFormat(), Qt::PlainText);
    QCOMPARE(value("volumeHeading")->text(), volume.name);
    QCOMPARE(value("usedBytes")->text(), QString("700 bytes"));
    QCOMPARE(value("freeBytes")->text(), QString("200 bytes"));
    QCOMPARE(value("reservedBytes")->text(), QString("100 bytes"));
    QCOMPARE(value("capacityBytes")->text(),
             QLocale().toString(1000) + " bytes");
    QVERIFY(dialog.findChild<QPushButton *>("openVolume")->isVisible());
    QVERIFY(dialog.findChild<QWidget *>("storageChart")
                ->accessibleDescription()
                .contains("700 bytes"));
    drives.volumes[0].available = 400;
    drives.volumes[0].freeBytes = 450;
    emit drives.changed();
    QCOMPARE(value("usedBytes")->text(), QString("550 bytes"));
    QCOMPARE(value("freeBytes")->text(), QString("400 bytes"));
    drives.volumes[0].mount.clear();
    drives.volumes[0].total = 0;
    emit drives.changed();
    QCOMPARE(value("usedValue")->text(), QString("—"));
    QCOMPARE(value("freeBytes")->text(), QString("Unavailable"));
    QCOMPARE(value("capacityBytes")->text(),
             QLocale().toString(1000) + " bytes");
    QVERIFY(value("usageHint")->text().contains("Mount this volume"));
    QVERIFY(!dialog.findChild<QPushButton *>("openVolume")->isVisible());
    drives.volumes.clear();
    emit drives.changed();
    QCOMPARE(value("volumeStatus")->text(), QString("Disconnected"));
    for (auto *button : dialog.findChildren<QPushButton *>())
      if (button->text() == "Copy details") {
        QTest::mouseClick(button, Qt::LeftButton);
        QVERIFY(
            QApplication::clipboard()->text().startsWith(volume.name + '\n'));
        QVERIFY(QApplication::clipboard()->text().contains("Device: " +
                                                           volume.device));
      }
    dialog.close();
  }
  void computerClipboardAndDriveMenu() {
    const QString source = folder + "/usb-source",
                  destination = folder + "/usb-target";
    QDir().mkpath(source);
    QDir().mkpath(destination);
    write(source + "/copy # 100%.txt", "copied safely\n");
    write(source + "/move.txt", "moved safely\n");
    write(source + "/menu.txt", "pasted from the menu\n");
    QStorageInfo storage(destination);
    Volume usb;
    usb.device = QString::fromLocal8Bit(storage.device());
    usb.name = "Test USB";
    usb.mount = destination;
    usb.filesystem = "ext4";
    usb.transport = "usb"; // USB SSDs often report RM=0.
    usb.uuid = "test-only";
    QVERIFY(QFileInfo::exists(usb.device));
    FilesWindow window(QUrl::fromLocalFile(source), false,
                       temporary.path() + "/usb-copy.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.drives->volumes = {usb};
    emit window.drives->changed();
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 3);
    tab->selectUrl(QUrl::fromLocalFile(source + "/copy # 100%.txt"));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->mimeData()->urls().size(), 1);
    window.openLocation(Fusion::computerUrl());
    auto *usbRow = driveRow(tab, usb.driveKey());
    QVERIFY(usbRow);
    QCOMPARE(usbRow->count(), 1);
    auto selectDrive = [&] {
      usbRow->setCurrentRow(0);
      window.activateWindow();
      usbRow->setFocus();
      QTest::qWait(30);
    };
    selectDrive();
    QTest::keyClick(usbRow, Qt::Key_V, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(
        QFileInfo::exists(destination + "/copy # 100%.txt"), 10000);
    QVERIFY(QFileInfo::exists(source + "/copy # 100%.txt"));
    window.openLocation(QUrl::fromLocalFile(source));
    QTRY_COMPARE(tab->proxy->rowCount(), 3);
    tab->selectUrl(QUrl::fromLocalFile(source + "/move.txt"));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_X, Qt::ControlModifier);
    window.openLocation(Fusion::computerUrl());
    selectDrive();
    QTest::keyClick(usbRow, Qt::Key_V, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(destination + "/move.txt"),
                             10000);
    QTRY_VERIFY(!QFileInfo::exists(source + "/move.txt"));
    QTest::keyClick(usbRow, Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->mimeData()->urls(),
             QList<QUrl>{QUrl::fromLocalFile(destination)});
    auto *data = new QMimeData;
    data->setUrls({QUrl::fromLocalFile(source + "/menu.txt")});
    QApplication::clipboard()->setMimeData(data);
    bool copyEnabled = false, cutDisabled = false, pasteEnabled = false,
         arkPresent = false;
    QTimer::singleShot(0, &window, [&] {
      auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
      if (!menu)
        return;
      auto *copy = menu->findChild<QAction *>("copy");
      auto *cut = menu->findChild<QAction *>("cut");
      auto *paste = menu->findChild<QAction *>("paste");
      copyEnabled = copy && copy->isEnabled();
      cutDisabled = cut && !cut->isEnabled();
      pasteEnabled = paste && paste->isEnabled();
      arkPresent = menu->findChild<QMenu *>("arkMenu");
      if (paste)
        paste->trigger();
      menu->close();
    });
    window.drives->menu(usb, window.mapToGlobal(QPoint(30, 30)), &window);
    QVERIFY(copyEnabled && cutDisabled && pasteEnabled && arkPresent);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(destination + "/menu.txt"),
                             10000);
    write(source + "/disconnected.txt");
    data = new QMimeData;
    data->setUrls({QUrl::fromLocalFile(source + "/disconnected.txt")});
    QApplication::clipboard()->setMimeData(data);
    window.drives->volumes[0].mount.clear();
    emit window.drives->changed();
    selectDrive();
    QTest::keyClick(usbRow, Qt::Key_V, Qt::ControlModifier);
    QTest::qWait(100);
    QVERIFY(!QFileInfo::exists(destination + "/disconnected.txt"));
    QVERIFY(window.drives->mountedLocation(usb).isEmpty());
    QFile copied(destination + "/copy # 100%.txt");
    QVERIFY(copied.open(QIODevice::ReadOnly));
    QCOMPARE(copied.readAll(), QByteArray("copied safely\n"));
    window.close();
  }
  void defaultApplicationAndArkMenu() {
    const QString applications =
        qEnvironmentVariable("XDG_DATA_HOME") + "/applications";
    QDir().mkpath(applications);
    write(applications + "/fusion-test-editor.desktop",
          "[Desktop Entry]\nType=Application\nName=Fusion Test "
          "Editor\nExec=/bin/true %U\nMimeType=text/plain;\n");
    write(qEnvironmentVariable("XDG_CONFIG_HOME") + "/mimeapps.list",
          "[Default Applications]\ntext/plain=fusion-test-editor.desktop;\n");
    QCOMPARE(QProcess::execute("kbuildsycoca6", {"--noincremental"}), 0);
    const QString sample = folder + "/archive-menu";
    QDir().mkpath(sample);
    write(sample + "/archive me.txt", "archive fixture\n");
    FilesWindow window(QUrl::fromLocalFile(sample), false,
                       temporary.path() + "/menu.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 1);
    clickFile(tab, QUrl::fromLocalFile(sample + "/archive me.txt"));
    bool openNamed = false, chooser = false, copy = false, cut = false,
         paste = false;
    QStringList compression;
    QTimer::singleShot(0, &window, [&] {
      auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
      if (!menu)
        return;
      auto *open = menu->findChild<QAction *>("open");
      openNamed = open && open->text() == "Open with Fusion Test Editor";
      chooser = menu->findChild<QAction *>("openWith");
      copy = menu->findChild<QAction *>("copy");
      cut = menu->findChild<QAction *>("cut");
      paste = menu->findChild<QAction *>("paste");
      if (auto *ark = menu->findChild<QMenu *>("arkMenu"))
        for (auto *action : ark->actions())
          if (!action->isSeparator())
            compression << action->text();
      const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
      if (!capture.isEmpty())
        menu->grab().save(capture + "-menu.png");
      menu->close();
    });
    emit tab->contextRequested(window.mapToGlobal(QPoint(40, 80)));
    QVERIFY(openNamed && chooser && copy && cut && paste);
    QVERIFY2(compression.size() >= 2, qPrintable(compression.join(" | ")));
    QVERIFY2(std::any_of(compression.cbegin(), compression.cend(),
                         [](const QString &text) {
                           return text.contains("zip", Qt::CaseInsensitive);
                         }),
             qPrintable(compression.join(" | ")));
    QTimer::singleShot(0, &window, [&] {
      auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
      if (!menu)
        return;
      if (auto *ark = menu->findChild<QMenu *>("arkMenu"))
        for (auto *action : ark->actions())
          if (action->text().contains("zip", Qt::CaseInsensitive)) {
            action->trigger();
            break;
          }
      menu->close();
    });
    emit tab->contextRequested(window.mapToGlobal(QPoint(40, 80)));
    QTRY_COMPARE_WITH_TIMEOUT(
        QDir(sample).entryList({"*.zip"}, QDir::Files).size(), 1, 15000);
    const QString archive = QDir(sample).filePath(
        QDir(sample).entryList({"*.zip"}, QDir::Files).first());
    QProcess verify;
    verify.start("python3",
                 {"-c",
                  "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert "
                  "z.read('archive me.txt') == b'archive fixture\\n'",
                  archive});
    QVERIFY(verify.waitForFinished(5000));
    QCOMPARE(verify.exitCode(), 0);
    window.close();
  }
  void inlineRenameAcrossViews_data() {
    QTest::addColumn<int>("mode");
    for (int mode = 0; mode < 5; ++mode) QTest::newRow(qPrintable(QString::number(mode))) << mode;
  }
  void inlineRenameAcrossViews() {
    QFETCH(int, mode);
    const auto base = folder + "/inline-" + QString::number(mode);
    QDir().mkpath(base + "/Folder.with.dots");
    write(base + "/name.unknownext"); write(base + "/existing.txt", "keep this file");
    FilesWindow window(QUrl::fromLocalFile(base), false, temporary.path()+"/inline.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    auto *tab = window.browser(); tab->setView(mode);
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 3, 10000);
    auto start = [&](const QString &name) {
      clickFile(tab, QUrl::fromLocalFile(base+'/'+name)); focus(tab);
      QTest::keyClick(tab->view(), Qt::Key_F2);
    };
    start("name.unknownext");
    QTRY_VERIFY(tab->view()->findChild<QTextEdit *>("inlineRename"));
    auto *edit = tab->view()->findChild<QTextEdit *>("inlineRename");
    QCOMPARE(edit->textCursor().selectedText(), QString("name"));
    QCOMPARE(edit->toPlainText(), QString("name.unknownext"));
    QVERIFY(edit->viewport()->height() >= edit->fontMetrics().height());
    const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) window.grab().save(capture + "-inline-" + QString::number(mode) + ".png");
    edit->insertPlainText("typing");
    const auto originalIndex = tab->model->indexForUrl(QUrl::fromLocalFile(base+"/name.unknownext"));
    emit tab->model->dataChanged(originalIndex, originalIndex, {Qt::DecorationRole});
    QCoreApplication::processEvents();
    QCOMPARE(edit->toPlainText(), QString("typing.unknownext"));
    edit->setPlainText("cancelled.txt"); QTest::keyClick(edit, Qt::Key_Escape);
    QTRY_VERIFY(!tab->view()->findChild<QTextEdit *>("inlineRename"));
    QVERIFY(QFileInfo::exists(base+"/name.unknownext")); QVERIFY(!QFileInfo::exists(base+"/cancelled.txt"));
    start("name.unknownext");
    QTRY_VERIFY(tab->view()->findChild<QTextEdit *>("inlineRename"));
    edit = tab->view()->findChild<QTextEdit *>("inlineRename");
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    edit->setPlainText("existing.txt"); QTest::keyClick(edit, Qt::Key_Return);
    QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 1, 10000);
    QVERIFY(QFileInfo::exists(base+"/name.unknownext"));
    QFile untouched(base+"/existing.txt"); QVERIFY(untouched.open(QIODevice::ReadOnly));
    QCOMPARE(untouched.readAll(), QByteArray("keep this file"));
    start("Folder.with.dots");
    QTRY_VERIFY(tab->view()->findChild<QTextEdit *>("inlineRename"));
    edit = tab->view()->findChild<QTextEdit *>("inlineRename");
    QCOMPARE(edit->textCursor().selectedText(), QString("Folder.with.dots"));
    edit->setPlainText("Renamed folder"); QTest::keyClick(edit, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo(base+"/Renamed folder").isDir(), 10000);
    QVERIFY(!QFileInfo::exists(base+"/Folder.with.dots")); window.close();
  }
  void keyboardAndOperations() {
    const QString source = folder + "/source", dest = folder + "/destination",
                  deep = folder + "/a folder/#percent%/leaf";
    QDir().mkpath(source);
    QDir().mkpath(dest);
    QDir().mkpath(deep);
    const QString original = source + "/original.txt",
                  renamed = source + "/renamed # 100%.txt";
    write(original);
    FilesWindow window(QUrl::fromLocalFile(source), false,
                       temporary.path() + "/ui.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 1, 10000);
    clickFile(tab, QUrl::fromLocalFile(original));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_F2);
    QTRY_VERIFY(tab->view()->findChild<QTextEdit *>("inlineRename"));
    auto *edit = tab->view()->findChild<QTextEdit *>("inlineRename");
    QVERIFY(edit);
    QCOMPARE(edit->textCursor().selectedText(), QString("original"));
    QVERIFY(!window.findChild<KIO::RenameFileDialog *>());
    edit->setPlainText(QFileInfo(renamed).fileName());
    QTest::keyClick(edit, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(renamed), 10000);
    QVERIFY(!QFileInfo::exists(original));
    QTRY_VERIFY_WITH_TIMEOUT(
        tab->model->indexForUrl(QUrl::fromLocalFile(renamed)).isValid(), 10000);
    clickFile(tab, QUrl::fromLocalFile(renamed));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->mimeData()->urls(),
             QList<QUrl>{QUrl::fromLocalFile(renamed)});
    window.openLocation(QUrl::fromLocalFile(dest));
    QTRY_COMPARE(tab->location(), QUrl::fromLocalFile(dest));
    focus(tab);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
    const QString copy = dest + "/renamed # 100%.txt";
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(copy), 10000);
    QVERIFY(QFileInfo::exists(renamed));
    QTRY_VERIFY_WITH_TIMEOUT(
        tab->model->indexForUrl(QUrl::fromLocalFile(copy)).isValid(), 10000);
    clickFile(tab, QUrl::fromLocalFile(copy));
    focus(tab);
    QCOMPARE(tab->selectedUrls(), QList<QUrl>{QUrl::fromLocalFile(copy)});
    QSignalSpy trashKey(window.findChild<QAction *>("trash"),
                        &QAction::triggered);
    QTest::keyClick(tab->view(), Qt::Key_Delete);
    QCOMPARE(trashKey.count(), 1);
    QTRY_VERIFY_WITH_TIMEOUT(!QFileInfo::exists(copy), 10000);
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_Z, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(copy), 10000);
    window.openLocation(QUrl::fromLocalFile(source));
    QTRY_VERIFY_WITH_TIMEOUT(
        tab->model->indexForUrl(QUrl::fromLocalFile(renamed)).isValid(), 10000);
    clickFile(tab, QUrl::fromLocalFile(renamed));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_X, Qt::ControlModifier);
    window.openLocation(QUrl::fromLocalFile(deep));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(deep + "/renamed # 100%.txt"),
                             10000);
    QVERIFY(!QFileInfo::exists(renamed));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_L, Qt::ControlModifier);
    QVERIFY(tab->navigator->isUrlEditable());
    auto *address = tab->navigator->editor()->lineEdit();
    QVERIFY(address->hasFocus());
    QCOMPARE(address->selectedText(), deep);
    QTest::keyClick(address, Qt::Key_C, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->text(), deep);
    address->setText(source);
    QTest::keyClick(address, Qt::Key_Return);
    QTRY_COMPARE(tab->location().adjusted(QUrl::StripTrailingSlash),
                 QUrl::fromLocalFile(source));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_Left, Qt::AltModifier);
    QTRY_COMPARE(tab->location().adjusted(QUrl::StripTrailingSlash),
                 QUrl::fromLocalFile(deep));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_T, Qt::ControlModifier);
    QCOMPARE(window.findChild<QTabWidget *>()->count(), 2);
    QTest::keyClick(window.browser(), Qt::Key_W, Qt::ControlModifier);
    QCOMPARE(window.findChild<QTabWidget *>()->count(), 1);
    QVERIFY(finished.count() >= 3);
    window.close();
  }
  void selectedFileAddressKeepsFolderNavigation() {
    const QString base = folder + "/address-selection";
    QDir().mkpath(base + "/Destination");
    const auto here = QUrl::fromLocalFile(base);
    const auto file = QUrl::fromLocalFile(base + "/photo # 100% café.png");
    const auto destination = QUrl::fromLocalFile(base + "/Destination");
    write(file.toLocalFile());
    Fusion::Preferences prefs(temporary.path() + "/address.ini");
    Drives drives(nullptr, false);
    Browser tab(&prefs, &drives);
    tab.resize(1000, 600); tab.show(); tab.navigate(here);
    QTRY_COMPARE(tab.proxy->rowCount(), 2);
    auto *bar = tab.navigator;
    const int history = bar->historySize();
    QSignalSpy navigation(&tab, &Browser::locationChanged);
    QSignalSpy opened(&tab, &Browser::openRequested);
    for (int mode = 0; mode < 5; ++mode) {
      tab.setView(mode); focus(&tab);
      tab.selectUrl(file);
      QCOMPARE(bar->editor()->currentText(), file.toLocalFile());
      QCOMPARE(tab.location(), here);
      QCOMPARE(bar->historySize(), history);
      QCOMPARE(navigation.size(), 0);
      bar->setUrlEditable(false);
      auto *label = bar->findChild<QLabel *>("selectedFilePath");
      QVERIFY(label); QCOMPARE(label->text(), file.fileName());
      tab.editAddress();
      QCOMPARE(bar->editor()->lineEdit()->selectedText(), file.toLocalFile());
      const int openedBefore = opened.size();
      QTest::keyClick(bar->editor()->lineEdit(), Qt::Key_Return);
      QCOMPARE(opened.size(), openedBefore + 1);
      QCOMPARE(tab.location(), here);
      tab.selectAll();
      QCOMPARE(bar->editor()->currentText(), base);
      tab.selectUrl(file); tab.view()->clearSelection();
      QCOMPARE(bar->editor()->currentText(), base);
      tab.selectUrl(destination);
      QCOMPARE(bar->editor()->currentText(), base);
    }
    tab.selectUrl(file);
    // Typing a relative folder still resolves against the current folder.
    bar->editor()->lineEdit()->setText("Destination");
    QTest::keyClick(bar->editor()->lineEdit(), Qt::Key_Return);
    QCOMPARE(tab.location(), destination);
    QCOMPARE(bar->editor()->currentText(), destination.toLocalFile());
    QVERIFY(bar->goBack()); QCOMPARE(tab.location(), here);
    QCOMPARE(bar->editor()->currentText(), base);
    QVERIFY(bar->goForward()); QCOMPARE(tab.location(), destination);
    QVERIFY(bar->goUp()); QCOMPARE(tab.location(), here);
  }
  void mouseSelectionInEveryView() {
    const QString base = folder + "/mouse-selection";
    QDir().mkpath(base);
    write(base + "/first.txt");
    write(base + "/second.unknown-format", QByteArray(32, '\0'));
    FilesWindow window(QUrl::fromLocalFile(base), false,
                       temporary.path() + "/mouse.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 2);
    for (int mode = 0; mode < 5; ++mode) {
      tab->setView(mode);
      focus(tab);
      tab->view()->clearSelection();
      clickFile(tab, QUrl::fromLocalFile(base + "/first.txt"));
      QCOMPARE(tab->selectedUrls(), QList<QUrl>{QUrl::fromLocalFile(base + "/first.txt")});
      clickFile(tab, QUrl::fromLocalFile(base + "/second.unknown-format"), Qt::ControlModifier);
      QCOMPARE(tab->selectedUrls().size(), 2);
      QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
      QCOMPARE(QApplication::clipboard()->mimeData()->urls().size(), 2);
      QTest::keyClick(tab->view(), Qt::Key_A, Qt::ControlModifier);
      QCOMPARE(tab->selectedItems().size(), 2);
    }
    window.close();
  }
  void dragAndDropAcrossViews() {
    const QString base = folder + "/drag-views";
    QDir().mkpath(base + "/Destination");
    const auto first = QUrl::fromLocalFile(base + "/photo # 100% café.png");
    const auto second = QUrl::fromLocalFile(base + "/notes.txt");
    write(first.toLocalFile());
    write(second.toLocalFile());
    FilesWindow window(QUrl::fromLocalFile(base), false,
                       temporary.path() + "/drag-views.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 3, 10000);
    // Exercise both initial construction and changing back from compact mode.
    int sequence = 0;
    for (int mode : {2, 3, 0, 1, 4, 2}) {
      tab->setView(mode);
      focus(tab);
      QVERIFY2(tab->view()->dragEnabled(), "View changes must not disable file dragging");
      QVERIFY(tab->view()->viewport()->acceptDrops());
      clickFile(tab, first);
      clickFile(tab, second, Qt::ControlModifier);
      const auto indexes = tab->view()->selectionModel()->selectedIndexes();
      std::unique_ptr<QMimeData> outgoing(tab->proxy->mimeData(indexes));
      QVERIFY(outgoing);
      QVERIFY(outgoing->hasFormat("text/uri-list"));
      QCOMPARE(outgoing->urls().size(), 2);
      QVERIFY(outgoing->urls().contains(first));
      QVERIFY(outgoing->urls().contains(second));
      const auto destination = tab->proxy->mapFromSource(
          tab->model->indexForUrl(QUrl::fromLocalFile(base + "/Destination")));
      QVERIFY(destination.flags().testFlag(Qt::ItemIsDropEnabled));
      const QString incoming = temporary.path() + "/incoming-" + QString::number(++sequence) + ".txt";
      write(incoming, "dropped file contents\n");
      QMimeData mime;
      mime.setUrls({QUrl::fromLocalFile(incoming)});
      const auto point = filePoint(tab, destination);
      QDragEnterEvent enter(point, Qt::CopyAction, &mime, Qt::LeftButton, Qt::ControlModifier);
      QApplication::sendEvent(tab->view()->viewport(), &enter);
      QVERIFY(enter.isAccepted());
      QSignalSpy jobs(tab, &Browser::jobStarted);
      QDropEvent drop(point, Qt::CopyAction, &mime, Qt::LeftButton, Qt::ControlModifier);
      QApplication::sendEvent(tab->view()->viewport(), &drop);
      QVERIFY(drop.isAccepted());
      QCOMPARE(jobs.size(), 1);
      QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(base + "/Destination/" + QFileInfo(incoming).fileName()), 10000);
      QVERIFY(QFileInfo::exists(incoming));
    }
    window.close();
  }
  void iconPaddingIsBackgroundForClicksAndBoxSelection_data() {
    QTest::addColumn<bool>("longNames");
    QTest::newRow("short filenames") << false;
    QTest::newRow("wrapped screenshot filenames") << true;
  }
  void iconPaddingIsBackgroundForClicksAndBoxSelection() {
    QFETCH(bool, longNames);
    const QString base = folder + (longNames ? "/icon-hit-long" : "/icon-hit-short");
    QDir().mkpath(base);
    for (const auto &prefix : {"a", "b", "c", "d"})
      write(base + "/" + prefix + (longNames ? "-Screenshot-2026-11-02_01-11-25-n9Bmq.png" : ".txt"));
    FilesWindow window(QUrl::fromLocalFile(base), false, temporary.path() + "/icon-hit.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 4);
    for (int mode : {0, 1, 2, 3}) {
      tab->setView(mode);focus(tab);
      auto *view = tab->icons;
      const auto first = tab->proxy->index(0, 0), last = tab->proxy->index(3, 0);
      const QRect cell = view->visualRect(first);
      const QPoint icon = filePoint(tab, first);
      const QPoint padding = mode == 3 ? QPoint(cell.right() - 1, cell.center().y())
                                       : QPoint(cell.left() + 1, icon.y());
      // These coordinates used to hit the first file, even though they are
      // visibly outside its icon and filename.
      QCOMPARE(view->QListView::indexAt(padding), first);
      QVERIFY2(!view->indexAt(padding).isValid(), qPrintable(QString("mode %1, cell %2,%3 %4x%5, padding %6,%7")
          .arg(mode).arg(cell.x()).arg(cell.y()).arg(cell.width()).arg(cell.height()).arg(padding.x()).arg(padding.y())));
      QCOMPARE(view->indexAt(icon), first);
      const QPoint label = mode == 3 ? QPoint(cell.left() + view->iconSize().width() + 10, cell.center().y())
                                     : QPoint(cell.center().x(), cell.bottom() - 8);
      QCOMPARE(view->indexAt(label), first);
      QTest::mouseClick(view->viewport(), Qt::LeftButton, Qt::NoModifier, label);
      QCOMPARE(tab->selectedUrls().size(), 1);
      tab->selectAll();QCOMPARE(tab->selectedUrls().size(), 4);
      QTest::mouseClick(view->viewport(), Qt::LeftButton, Qt::NoModifier, padding);
      QVERIFY(tab->selectedUrls().isEmpty());

      // Starting inside a selected cell's padding must box-select, not export
      // the selected files in a native drag. End on background as well.
      tab->selectAll();
      const QRect endCell = view->visualRect(last);
      const QPoint end = mode == 3 ? QPoint(endCell.left() + 1, endCell.bottom() - 1)
                                   : QPoint(endCell.right() - 1, endCell.bottom() - 1);
      QTest::mousePress(view->viewport(), Qt::LeftButton, Qt::NoModifier, padding);
      QTest::mouseMove(view->viewport(), end, 20);
      QCOMPARE(tab->selectedUrls().size(), 4);
      QTest::mouseRelease(view->viewport(), Qt::LeftButton, Qt::NoModifier, end);
      QCOMPARE(tab->selectedUrls().size(), 4);
      QSignalSpy opened(tab, &Browser::openRequested);
      QTest::mouseDClick(view->viewport(), Qt::LeftButton, Qt::NoModifier, padding);
      QCOMPARE(opened.size(), 0);
      QTest::mouseRelease(view->viewport(), Qt::MiddleButton, Qt::NoModifier, padding);
      QCOMPARE(opened.size(), 0);
      QTest::mouseClick(view->viewport(), Qt::LeftButton, Qt::NoModifier, icon);
      QCOMPARE(tab->selectedUrls().size(), 1);
      QTest::mouseClick(view->viewport(), Qt::LeftButton, Qt::ShiftModifier, filePoint(tab, last));
      QCOMPARE(tab->selectedUrls().size(), 4);
    }
    window.close();
  }
  void unknownFilesAndScriptMenus() {
    const QString base = folder + "/script-menus";
    QDir().mkpath(base);
    const auto script = QUrl::fromLocalFile(base + "/a ; $(literal) # 100%.sh");
    const auto unknown = QUrl::fromLocalFile(base + "/data.unknown-format");
    write(script.toLocalFile(), "#!/usr/bin/env bash\nprintf 'fixture only'\n");
    write(unknown.toLocalFile(), QByteArray(32, '\0'));
    const auto command = Fusion::executionCommand(script);
    QCOMPARE(command, QStringList({"kitty", "--hold", "--directory", base, "-e",
                                  "/usr/bin/env", "bash", script.toLocalFile()}));
    QVERIFY(!QFileInfo(script.toLocalFile()).isExecutable());
    QVERIFY(Fusion::executionCommand(unknown).isEmpty());
    FilesWindow window(QUrl::fromLocalFile(base), false,
                       temporary.path() + "/scripts.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE(tab->proxy->rowCount(), 2);
    for (const auto &url : {unknown, script}) {
      clickFile(tab, url);
      QStringList actions;
      QTimer::singleShot(0, &window, [&] {
        auto *menu = qobject_cast<QMenu *>(QApplication::activePopupWidget());
        if (!menu) return;
        for (auto *action : menu->actions()) actions << action->objectName();
        menu->close();
      });
      const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(url));
      // Use the view's real right-click path, including hit testing.
      emit tab->view()->customContextMenuRequested(tab->view()->visualRect(index).center());
      for (const auto &id : {"open", "openWith", "copy", "cut", "paste", "rename", "trash"})
        QVERIFY2(actions.contains(id), id);
      if (url == script) QCOMPARE(actions.first(), QString("execute"));
      else QVERIFY(!actions.contains("execute"));
    }
    window.close();
  }
  void numberedPastesKeepBothAndSupportUndo() {
    const QString a = folder + "/numbered-a", b = folder + "/numbered-b";
    QDir().mkpath(a + "/project.v1/nested");
    QDir().mkpath(b);
    write(a + "/same.txt", "original source");
    write(a + "/.env", "dotfile");
    write(a + "/backup.tar.gz", "compound extension");
    write(a + "/project.v1/nested/data", "nested content");
    write(b + "/other.txt", "original destination");
    QVERIFY(QFile::link(a + "/missing", a + "/link"));
    FilesWindow window(QUrl::fromLocalFile(a), false,
                       temporary.path() + "/numbered.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    tab->setHidden(true);
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 5, 10000);
    bool popup = false;
    QTimer rejectConflicts;
    connect(&rejectConflicts, &QTimer::timeout, &window, [&] {
      for (auto *widget : QApplication::topLevelWidgets())
        if (auto *dialog = qobject_cast<QDialog *>(widget); dialog && dialog->isVisible()) {
          popup = true;
          dialog->reject();
        }
    });
    rejectConflicts.start(10);
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_A, Qt::ControlModifier);
    QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    for (int number = 1; number <= 2; ++number) {
      const auto suffix = "_copy" + QString::number(number);
      // Offscreen KIO job windows can take activation after the first paste.
      // Deliver each keyboard gesture to the file view as a real focused click would.
      focus(tab);
      QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
      QTRY_COMPARE_WITH_TIMEOUT(finished.count(), number, 15000);
      QCOMPARE(finished.last().first().toInt(), 0);
      for (const auto &name : {"same" + suffix + ".txt", ".env" + suffix,
                               "backup" + suffix + ".tar.gz", "project.v1" + suffix + "/nested/data"})
        QVERIFY2(QFileInfo::exists(a + "/" + name), qPrintable(name));
      QVERIFY(QFileInfo(a + "/link" + suffix).isSymbolicLink());
      QVERIFY(!popup);
    }
    // A cross-folder cut keeps the original name; Undo restores the source.
    focus(tab);
    clickFile(tab, QUrl::fromLocalFile(a + "/same.txt"));
    QTest::keyClick(tab->view(), Qt::Key_X, Qt::ControlModifier);
    QCOMPARE(QApplication::clipboard()->mimeData()->urls(), QList<QUrl>{QUrl::fromLocalFile(a + "/same.txt")});
    QVERIFY(KIO::isClipboardDataCut(QApplication::clipboard()->mimeData()));
    window.openLocation(QUrl::fromLocalFile(b));
    QTRY_COMPARE(tab->proxy->rowCount(), 1);
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 3, 15000);
    QCOMPARE(finished.last().first().toInt(), 0);
    QVERIFY(!QFileInfo::exists(a + "/same.txt"));
    QFile moved(b + "/same.txt"), existing(b + "/other.txt");
    QVERIFY(moved.open(QIODevice::ReadOnly));
    QVERIFY(existing.open(QIODevice::ReadOnly));
    QCOMPARE(moved.readAll(), QByteArray("original source"));
    QCOMPARE(existing.readAll(), QByteArray("original destination"));
    moved.close(); existing.close();
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_Z, Qt::ControlModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(a + "/same.txt"), 10000);
    QVERIFY(!QFileInfo::exists(b + "/same.txt"));
    QVERIFY(!popup);
    window.close();
  }
  void transferProgress() {
    if (!qEnvironmentVariableIsSet("FUSION_FILES_PROGRESS_CHECK"))
      QSKIP("Run by test_progress.py with the real Fusion JobView service.");
    const auto source = folder + "/Transfer source";
    const auto target = folder + "/Transfer target";
    QDir().mkpath(source);
    QDir().mkpath(target);
    for (int n = 0; n < 1024; ++n)
      write(source + "/file-" + QString::number(n), QByteArray(65536, char(n % 127)));
    FilesWindow window(QUrl::fromLocalFile(folder), false,
                       temporary.path() + "/progress.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_VERIFY(tab->model->indexForUrl(QUrl::fromLocalFile(source)).isValid());
    clickFile(tab, QUrl::fromLocalFile(source));
    focus(tab);
    QTest::keyClick(tab->view(), Qt::Key_C, Qt::ControlModifier);
    window.openLocation(QUrl::fromLocalFile(target));
    focus(tab);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    QTest::keyClick(tab->view(), Qt::Key_V, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 1, 30000);
    if (qEnvironmentVariableIsSet("FUSION_FILES_PROGRESS_CANCEL")) {
      QCOMPARE(finished.first().first().toInt(), int(KIO::ERR_USER_CANCELED));
      QCOMPARE(QDir(source).entryList(QDir::Files).size(), 1024);
      window.close();
      return;
    }
    QCOMPARE(finished.first().first().toInt(), 0);
    QCOMPARE(QDir(target + "/Transfer source").entryList(QDir::Files).size(), 1024);
    QFile last(target + "/Transfer source/file-1023");
    QVERIFY(last.open(QIODevice::ReadOnly));
    QCOMPARE(last.readAll(), QByteArray(65536, char(1023 % 127)));
    window.close();
  }
  void transferQuestions() {
    if (!qEnvironmentVariableIsSet("FUSION_FILES_QUESTIONS_CHECK"))
      QSKIP("Run by test_questions.py with the real expanding Fusion transfer windows.");
    QWidget owner;
    for (const auto operation : {Fusion::TransferOperation::Copy, Fusion::TransferOperation::Move}) {
      for (const auto mode : {"replace", "skip", "individual", "cancel"}) {
        const auto base = folder + "/questions-" + mode + QString::number(int(operation));
        for (const auto side : {"source", "target"}) {
          QDir().mkpath(base+"/"+side+"/Folder/nested");
          for (const auto name : {"a.txt", "Folder/b.txt", "Folder/nested/c.txt"})
            write(base+"/"+side+"/"+name, QByteArray(side));
        }
        write(base+"/source/Folder/new.txt", "new file");
        QTimer queued;
        connect(&queued, &QTimer::timeout, &owner, [&] {
          if (!QFileInfo::exists(base+"/target/Folder/new.txt")) return;
          if (QByteArray(mode)=="individual") {
            auto *queue=queueFor(base); if (!queue) return;
            auto *table=queue->findChild<QTableView *>("transferIssuesTable");
            table->clearSelection();
            for (int n=0;n<table->model()->rowCount();++n) {
              if (table->model()->index(n,2).data().toString()!="Needs a choice") continue;
              const auto choice=table->model()->index(n,3).data().toString().endsWith("/a.txt")?"replace":"skip";
              table->selectRow(n); queue->findChild<QCheckBox *>("similarTransferIssues")->setChecked(false);
              if (QByteArray(choice)=="replace") QTimer::singleShot(0,queue,[queue]{
                for(auto *dialog:queue->findChildren<QMessageBox *>()) dialog->button(QMessageBox::Yes)->click();
              });
              queue->findChild<QPushButton *>(QString("transferIssue_")+choice)->click();
              break;
            }
          } else answerQueue(base,mode);
        }); queued.start(100);
        auto *job = Fusion::transferFiles({QUrl::fromLocalFile(base+"/source/a.txt"), QUrl::fromLocalFile(base+"/source/Folder")},
            QUrl::fromLocalFile(base+"/target"), operation, &owner);
        int error = -1; connect(job, &KJob::result, &owner, [&](KJob *j) { error = j->error(); });
        QTRY_VERIFY_WITH_TIMEOUT(error != -1, 15000);
        QCOMPARE(error, QByteArray(mode) == "cancel" ? KIO::ERR_USER_CANCELED : 0);
        for (const auto name : {"a.txt", "Folder/b.txt", "Folder/nested/c.txt"}) {
          const bool replaced = QByteArray(mode) == "replace" || (QByteArray(mode) == "individual" && QByteArray(name) == "a.txt");
          QFile destination(base+"/target/"+name); QVERIFY(destination.open(QIODevice::ReadOnly));
          QCOMPARE(destination.readAll(), replaced ? QByteArray("source") : QByteArray("target"));
          QCOMPARE(QFileInfo::exists(base+"/source/"+name), operation == Fusion::TransferOperation::Copy || !replaced);
        }
        if (QByteArray(mode) != "cancel") QVERIFY(QFileInfo::exists(base+"/target/Folder/new.txt"));
        QVERIFY(!owner.findChild<QDialog *>("transferConflictSummary"));
        QVERIFY(!owner.findChild<QMessageBox *>("transferConflictQuestion"));
      }
    }
    const auto base = folder+"/questions-duplicate"; QDir().mkpath(base);
    write(base+"/a.txt", "original");
    for (int n=1; n<=2; ++n) {
      QMimeData mime; mime.setUrls({QUrl::fromLocalFile(base+"/a.txt")});
      QDropEvent event(QPointF(1,1), Qt::MoveAction|Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
      auto *job = Fusion::dropFiles(&event, QUrl::fromLocalFile(base), &owner, {});
      int error = -1; connect(job, &KJob::result, &owner, [&](KJob *j) { error = j->error(); });
      QTRY_COMPARE_WITH_TIMEOUT(error, 0, 15000);
      QVERIFY(QFileInfo::exists(base+"/a_copy"+QString::number(n)+".txt"));
      QVERIFY(!owner.findChild<QMessageBox *>("duplicateDropQuestion"));
    }
  }
  void transferCanPauseBeforeAccessCheckCompletes() {
    const auto base = folder+"/pause-before-access";
    QDir().mkpath(base+"/source"); QDir().mkpath(base+"/target");
    write(base+"/source/a.txt", "source");
    QWidget owner;
    auto *job = Fusion::transferFiles({QUrl::fromLocalFile(base+"/source/a.txt")},
        QUrl::fromLocalFile(base+"/target"), Fusion::TransferOperation::Copy, &owner);
    int error = -1; connect(job, &KJob::result, &owner, [&](KJob *j) { error = j->error(); });
    QVERIFY(job->suspend()); QTest::qWait(200);
    QVERIFY(job->isSuspended()); QCOMPARE(error, -1);
    QVERIFY(!QFileInfo::exists(base+"/target/a.txt"));
    QVERIFY(job->resume()); QTRY_COMPARE_WITH_TIMEOUT(error, 0, 10000);
    QVERIFY(QFileInfo::exists(base+"/target/a.txt"));
  }
  void newFolderAndPermanentDeleteCancellation() {
    const QString base = folder + "/new-folder-test";
    QDir().mkpath(base);
    FilesWindow window(QUrl::fromLocalFile(base), false,
                       temporary.path() + "/new-folder.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    focus(tab);
    QTimer::singleShot(30, [] {
      for (auto *widget : QApplication::topLevelWidgets())
        if (auto *dialog = qobject_cast<QInputDialog *>(widget)) {
          dialog->setTextValue("New # folder");
          dialog->accept();
        }
    });
    QTest::keyClick(tab->view(), Qt::Key_N,
                    Qt::ControlModifier | Qt::ShiftModifier);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo(base + "/New # folder").isDir(), 10000);
    QTRY_VERIFY_WITH_TIMEOUT(
        tab->model->indexForUrl(QUrl::fromLocalFile(base + "/New # folder"))
            .isValid(),
        10000);
    tab->selectUrl(QUrl::fromLocalFile(base + "/New # folder"));
    focus(tab);
    QTimer::singleShot(30, [] {
      for (auto *widget : QApplication::topLevelWidgets())
        if (auto *dialog = qobject_cast<QMessageBox *>(widget))
          dialog->reject();
    });
    QTest::keyClick(tab->view(), Qt::Key_Delete, Qt::ShiftModifier);
    QVERIFY(QFileInfo(base + "/New # folder").isDir());
    window.close();
  }
  void mountArgumentsUseMockToolsOnly() {
    const QString tools = temporary.path() + "/mock-tools",
                  log = temporary.path() + "/mount-args.json";
    QDir().mkpath(tools);
    write(tools + "/udisksctl", "#!/usr/bin/python3\nimport os,sys,json\nwith "
                                "open(os.environ['FUSION_TEST_DRIVE_LOG'],'w') "
                                "as f: json.dump(sys.argv[1:],f)\n");
    write(tools + "/lsblk", "#!/usr/bin/python3\nimport "
                            "os\nprint(os.environ['FUSION_TEST_LSBLK'])\n");
    QFile::setPermissions(tools + "/udisksctl", QFileDevice::ReadOwner |
                                                    QFileDevice::WriteOwner |
                                                    QFileDevice::ExeOwner);
    QFile::setPermissions(tools + "/lsblk", QFileDevice::ReadOwner |
                                                QFileDevice::WriteOwner |
                                                QFileDevice::ExeOwner);
    const auto oldPath = qgetenv("PATH");
    const auto cleanup = qScopeGuard([&] {
      qputenv("PATH", oldPath);
      qunsetenv("FUSION_TEST_DRIVE_LOG");
      qunsetenv("FUSION_TEST_LSBLK");
    });
    qputenv("PATH", tools.toUtf8());
    qputenv("FUSION_TEST_DRIVE_LOG", log.toUtf8());
    qputenv(
        "FUSION_TEST_LSBLK",
        R"({"blockdevices":[{"name":"fixture","path":"/dev/fusion-test-only","type":"part","fstype":"ext4","uuid":"fixture","size":100,"mountpoints":[null]}]})");
    Drives drives;
    QTRY_COMPARE_WITH_TIMEOUT(drives.volumes.size(), 1, 5000);
    QVERIFY(!QFileInfo::exists(log));
    drives.operate(drives.volumes.first(), "mount", nullptr);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(log), 5000);
    QTRY_VERIFY(!drives.busy());
    QFile args(log);
    QVERIFY(args.open(QIODevice::ReadOnly));
    QCOMPARE(QJsonDocument::fromJson(args.readAll()).array(),
             QJsonArray({"mount", "-b", "/dev/fusion-test-only"}));
  }
  void applicationChooserAndExplicitOpen() {
    const QString sample = folder + "/app-chooser";
    QDir().mkpath(sample);
    const auto file = QUrl::fromLocalFile(sample + "/open # % literal.txt");
    write(file.toLocalFile());
    const QString log = sample + "/opened.json";
    const QString program = sample + "/editor.py";
    write(program, "import json,os,signal,sys,time\nfrom pathlib import Path\n"
                   "signal.signal(signal.SIGPIPE,signal.SIG_DFL)\ntime.sleep(.15)\n"
                   "os.write(1,b'Application stdout\\n');os.write(2,b'Application stderr\\n')\nPath(" +
                   QJsonDocument(QJsonArray{log}).toJson(QJsonDocument::Compact).mid(1).chopped(1) + ").write_text(json.dumps(sys.argv[1:]))\n");
    write(qEnvironmentVariable("XDG_DATA_HOME") + "/applications/fusion-test-editor.desktop",
          "[Desktop Entry]\nType=Application\nName=Fusion Test Editor\nExec=/usr/bin/python3 \"" + program.toUtf8() + "\" %F\nIcon=text-editor\nMimeType=text/plain;\n");
    QCOMPARE(QProcess::execute("kbuildsycoca6", {"--noincremental"}), 0);
    FilesWindow window(QUrl::fromLocalFile(sample), false, temporary.path() + "/chooser.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    auto *tab = window.browser();
    QTRY_VERIFY(tab->model->indexForUrl(file).isValid());
    clickFile(tab, file);
    // An explicit menu action must work while an address/search editor owns focus.
    tab->filter->setFocus();
    window.runAction("open");
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(log), 10000);
    QFile opened(log); QVERIFY(opened.open(QIODevice::ReadOnly));
    QCOMPARE(QJsonDocument::fromJson(opened.readAll()).array(), QJsonArray{file.toLocalFile()});
    Fusion::ApplicationDialog chooser({KFileItem(file)}, &window);
    chooser.show();
    auto *list = chooser.findChild<QListWidget *>("applicationList");
    auto *search = chooser.findChild<QLineEdit *>("applicationSearch");
    QVERIFY(list && search);
    QTRY_VERIFY_WITH_TIMEOUT(list->count() > 0, 10000);
    search->setFocus(); QTest::keyClicks(search, "Fusion Test Editor");
    QCOMPARE(search->text(), QString("Fusion Test Editor"));
    QTRY_COMPARE(list->count(), 1);
    QCOMPARE(chooser.request().value("app").toString(), QString("fusion-test-editor.desktop"));
    QVERIFY(!chooser.request().value("remember").toBool());
    // The chosen application uses the same launcher as double-click, including
    // safe streams after the short-lived JSON helper has exited.
    opened.close(); QVERIFY(QFile::remove(log));
    auto request = chooser.request();
    request["urls"] = QJsonArray{file.toString(QUrl::FullyEncoded)};
    auto *job = Fusion::launchApplication(request, &window);
    int launchError = -1;
    connect(job, &KJob::result, &window, [&](KJob *result) { launchError = result->error(); });
    QTRY_COMPARE_WITH_TIMEOUT(launchError, 0, 10000);
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(log), 10000);
    QVERIFY(opened.open(QIODevice::ReadOnly));
    QCOMPARE(QJsonDocument::fromJson(opened.readAll()).array(), QJsonArray{file.toLocalFile()});
    const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) chooser.grab().save(capture + "-open-with.png");
    chooser.reject(); window.close();
  }
  void executableDoubleClickRunsWithoutChangingPermissions() {
    const QString sample = folder + "/executable-click";
    QDir().mkpath(sample + "/bin");
    const QString log = sample + "/executed";
    const auto script = QUrl::fromLocalFile(sample + "/test installer.run");
    write(script.toLocalFile(), "#!/usr/bin/python3\nfrom pathlib import Path\nPath(" + QJsonDocument(QJsonArray{log}).toJson(QJsonDocument::Compact).mid(1).chopped(1) + ").write_text('executed')\n");
    QFile::setPermissions(script.toLocalFile(), QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    // A test-only terminal launches the harmless fixture; no desktop terminal opens.
    const QString kitty = sample + "/bin/kitty";
    write(kitty, "#!/usr/bin/python3\nimport os,sys\na=sys.argv[sys.argv.index('-e')+1:];os.execvp(a[0],a)\n");
    QFile::setPermissions(kitty, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    const auto previousPath = qgetenv("PATH");
    qputenv("PATH", QFile::encodeName(sample + "/bin:") + previousPath);
    auto resetPath = qScopeGuard([&] { qputenv("PATH", previousPath); });
    const auto permissions = QFileInfo(script.toLocalFile()).permissions();
    FilesWindow window(QUrl::fromLocalFile(sample), false, temporary.path() + "/execute.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    auto *tab = window.browser();
    QTRY_VERIFY(tab->model->indexForUrl(script).isValid());
    clickFile(tab, script);
    const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(script));
    QTest::mouseDClick(tab->view()->viewport(), Qt::LeftButton, Qt::NoModifier, filePoint(tab, index));
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(log), 10000);
    QCOMPARE(QFileInfo(script.toLocalFile()).permissions(), permissions);
    window.close();
  }
  void thumbnailsConfigurationAndTrashAnimation() {
    const QString sample = folder + "/thumbnails";
    QDir().mkpath(sample);
    const auto file = QUrl::fromLocalFile(sample + "/red picture.png");
    QImage image(160, 100, QImage::Format_RGB32); image.fill(QColor("#eb425a")); QVERIFY(image.save(file.toLocalFile()));
    const QString settings = temporary.path() + "/thumbnails.ini";
    FilesWindow window(QUrl::fromLocalFile(sample), false, settings);
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    auto *tab = window.browser();
    auto *preview = window.findChild<QAction *>("previewPaneAction");
    QVERIFY(preview && preview->isChecked());
    QTRY_VERIFY(tab->model->indexForUrl(file).isValid());
    auto pixel = [&] {
      const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(file));
      const auto pixmap = qvariant_cast<QIcon>(index.data(Qt::DecorationRole)).pixmap(80, 80).toImage();
      return pixmap.isNull() ? QColor() : pixmap.pixelColor(pixmap.width()/2, pixmap.height()/2);
    };
    QTRY_VERIFY_WITH_TIMEOUT(pixel().red() > 210 && pixel().green() < 100, 15000);
    clickFile(tab, file); focus(tab);
    QSignalSpy finished(&window, &FilesWindow::operationFinished);
    QTest::keyClick(tab->view(), Qt::Key_Delete);
    QTRY_VERIFY_WITH_TIMEOUT(!finished.isEmpty(), 10000);
    QCOMPARE(finished.last().first().toInt(), 0);
    QVERIFY(!QFileInfo::exists(file.toLocalFile()));
    QVERIFY(window.findChild<QWidget *>("trashFlight"));
    const auto capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) { QTest::qWait(260); window.grab().save(capture + "-trash-flight.png"); }
    QTRY_VERIFY_WITH_TIMEOUT(!window.findChild<QWidget *>("trashFlight"), 2000);
    bool configured = false;
    QTimer::singleShot(0, &window, [&] {
      auto *dialog = window.findChild<QDialog *>("filesConfiguration");
      if (!dialog) return;
      dialog->findChild<QCheckBox *>("configureThumbnails")->setChecked(false);
      dialog->findChild<QCheckBox *>("configurePreview")->setChecked(false);
      dialog->findChild<QCheckBox *>("configureTrashAnimation")->setChecked(false);
      if (!capture.isEmpty()) dialog->grab().save(capture + "-configuration.png");
      configured = true; dialog->accept();
    });
    auto *action = window.findChild<QAction *>("configureFiles"); QVERIFY(action); action->trigger();
    QVERIFY(configured);
    QVERIFY(!preview->isChecked());
    QCOMPARE(window.preferences.settings.value("thumbnails").toBool(), false);
    window.close();
    FilesWindow reopened(QUrl::fromLocalFile(sample), false, settings);
    reopened.setAttribute(Qt::WA_DeleteOnClose, false);
    QVERIFY(!reopened.findChild<QAction *>("previewPaneAction")->isChecked());
    QCOMPARE(reopened.preferences.settings.value("trashAnimation").toBool(), false);
  }
  void permissionFailureRequestsAuthenticationAndCancellationKeepsFile() {
    const QString sample = folder + "/permission-retry", bin = sample + "/bin", protectedFolder = sample + "/protected";
    QDir().mkpath(bin); QDir().mkpath(protectedFolder);
    const auto file = QUrl::fromLocalFile(protectedFolder + "/keep.txt");
    write(file.toLocalFile());
    const QString request = sample + "/request.json";
    write(bin + "/pkexec", "#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\nPath(" + QJsonDocument(QJsonArray{request}).toJson(QJsonDocument::Compact).mid(1).chopped(1) + ").write_text(sys.stdin.read())\nsys.exit(126)\n");
    QFile::setPermissions(bin + "/pkexec", QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    const auto previousPath = qgetenv("PATH"); qputenv("PATH", QFile::encodeName(bin + ':') + previousPath);
    auto restore = qScopeGuard([&] { qputenv("PATH", previousPath); QFile::setPermissions(protectedFolder, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner); });
    QFile::setPermissions(protectedFolder, QFile::ReadOwner | QFile::ExeOwner);
    auto *job = new Fusion::RemovalJob({file}, false, nullptr);
    QSignalSpy finished(job, &KJob::result);
    int error = -1; connect(job, &KJob::result, this, [&](KJob *job) { error = job->error(); });
    QTRY_VERIFY_WITH_TIMEOUT(!finished.isEmpty(), 15000);
    QVERIFY(QFileInfo::exists(file.toLocalFile()));
    QFile record(request); QVERIFY(record.open(QIODevice::ReadOnly));
    const auto data = QJsonDocument::fromJson(record.readAll()).object();
    QCOMPARE(data.value("operation").toString(), QString("trash"));
    QCOMPARE(data.value("items").toArray().first().toObject().value("path").toString(), file.toLocalFile());
    QCOMPARE(error, int(KIO::ERR_USER_CANCELED));
  }
  void protectedRestoreUsesTrashMetadataAndKeepsCancelledItem() {
    const QString sample = folder + "/restore-retry", bin = sample + "/bin", destination = sample + "/protected";
    QDir().mkpath(bin); QDir().mkpath(destination);
    const QString trash = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) + "/Trash";
    QDir().mkpath(trash + "/files"); QDir().mkpath(trash + "/info");
    const QString name = "fusion-restore-fixture.txt", original = destination + "/original # name.txt";
    write(trash + "/files/" + name);
    write(trash + "/info/" + name + ".trashinfo", "[Trash Info]\nPath=" + QUrl::toPercentEncoding(original, "/") + "\nDeletionDate=2026-01-01T12:00:00\n");
    const auto url = QUrl("trash:/0-" + name);
    auto *stat = KIO::stat(url); stat->setAutoDelete(false);
    QVERIFY2(stat->exec(), qPrintable(stat->errorString()));
    const KFileItem item(stat->statResult(), url); delete stat;
    QCOMPARE(item.localPath(), trash + "/files/" + name);
    const QString request = sample + "/request.json";
    write(bin + "/pkexec", "#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\nPath(" + QJsonDocument(QJsonArray{request}).toJson(QJsonDocument::Compact).mid(1).chopped(1) + ").write_text(sys.stdin.read())\nsys.exit(126)\n");
    QFile::setPermissions(bin + "/pkexec", QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    const auto previousPath = qgetenv("PATH"); qputenv("PATH", QFile::encodeName(bin + ':') + previousPath);
    auto reset = qScopeGuard([&] { qputenv("PATH", previousPath); QFile::setPermissions(destination, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner); });
    QFile::setPermissions(destination, QFile::ReadOwner | QFile::ExeOwner);
    auto *job = new Fusion::RemovalJob(KFileItemList{item}, QString("restore"), nullptr);
    QSignalSpy finished(job, &KJob::result);
    int error = -1; connect(job, &KJob::result, this, [&](KJob *result) { error = result->error(); });
    QTRY_VERIFY_WITH_TIMEOUT(!finished.isEmpty(), 15000);
    QCOMPARE(error, int(KIO::ERR_USER_CANCELED));
    QVERIFY(QFileInfo::exists(item.localPath())); QVERIFY(!QFileInfo::exists(original));
    QFile record(request); QVERIFY(record.open(QIODevice::ReadOnly));
    const auto data = QJsonDocument::fromJson(record.readAll()).object();
    QCOMPARE(data.value("operation").toString(), QString("restore"));
    const auto selection = data.value("items").toArray().first().toObject();
    QCOMPARE(selection.value("path").toString(), item.localPath());
    QCOMPARE(selection.value("restoreTo").toString(), original);
    QVERIFY(selection.value("fromTrash").toBool());
    QFile::setPermissions(destination, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    auto *retry = new Fusion::RemovalJob(KFileItemList{item}, QString("restore"), nullptr);
    QSignalSpy restored(retry, &KJob::result);
    connect(retry, &KJob::result, this, [&](KJob *result) { error = result->error(); });
    QTRY_VERIFY_WITH_TIMEOUT(!restored.isEmpty(), 15000);
    QCOMPARE(error, 0); QVERIFY(QFileInfo::exists(original));
    QVERIFY(!QFileInfo::exists(item.localPath()));
  }
  void viewsAndScreenshots() {
    const QString sample = folder + "/preview";
    QDir().mkpath(sample + "/Projects");
    QDir().mkpath(sample + "/Documents");
    QDir().mkpath(sample + "/Wallpapers");
    write(sample + "/Welcome.txt",
          "Welcome to Fusion Files.\nYour files, your desktop.\n");
    write(sample + "/Notes.md", "# Ideas\nKeep the desktop simple.\n");
    QImage art(800, 500, QImage::Format_RGB32);
    QPainter painter(&art);
    QLinearGradient gradient(0, 0, 800, 500);
    gradient.setColorAt(0, QColor("#212344"));
    gradient.setColorAt(1, QColor("#ed5f79"));
    painter.fillRect(art.rect(), gradient);
    painter.end();
    art.save(sample + "/Sunset.png");
    const QString settings = temporary.path() + "/views.ini";
    FilesWindow window(QUrl::fromLocalFile(sample), false, settings);
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    window.show();
    auto *tab = window.browser();
    QTRY_COMPARE_WITH_TIMEOUT(tab->proxy->rowCount(), 6, 10000);
    for (int mode = 0; mode < 5; ++mode) {
      tab->setView(mode);
      QCOMPARE(tab->selectedUrls().size(), 0);
      QVERIFY(tab->view()->isVisible());
    }
    tab->details->setColumnHidden(KDirModel::Owner, false);
    tab->details->setColumnHidden(KDirModel::ModifiedTime, true);
    tab->saveView();
    window.preferences.settings.sync();
    Fusion::Preferences restored(settings);
    Browser another(&restored, window.drives);
    QVERIFY(!another.details->isColumnHidden(KDirModel::Owner));
    QVERIFY(another.details->isColumnHidden(KDirModel::ModifiedTime));
    const QString capture = qEnvironmentVariable("FUSION_FILES_CAPTURE");
    if (!capture.isEmpty()) {
      tab->setView(2);
      tab->selectUrl(QUrl::fromLocalFile(sample + "/Sunset.png"));
      if (!window.findChild<QAction *>("previewPaneAction")->isChecked()) window.runAction("preview");
      QTest::qWait(700);
      QVERIFY(window.grab().save(capture + "-folder.png"));
      window.openLocation(Fusion::computerUrl());
      window.drives->volumes = computerVolumes();
      emit window.drives->changed();
      window.runAction("preview");
      window.resize(1280, 1120);
      QTest::qWait(150);
      QVERIFY(window.grab().save(capture + "-computer.png"));
      auto system = *std::find_if(
          window.drives->volumes.cbegin(), window.drives->volumes.cend(),
          [](const Volume &v) { return v.mount == "/"; });
      system.available = system.total * 31 / 100;
      system.freeBytes = system.total * 36 / 100;
      system.uuid = "01234567-89ab-cdef-0123-456789abcdef";
      DriveProperties properties(system, window.drives, &window);
      properties.show();
      QTest::qWait(100);
      QVERIFY(properties.grab().save(capture + "-properties.png"));
      QVERIFY(Fusion::icon("fusion-computer")
                  .pixmap(256, 256)
                  .save(capture + "-icon.png"));
      properties.close();
    }
    window.close();
  }
};
QTEST_MAIN(FileTests)
#include "tests.moc"
