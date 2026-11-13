#include "window.h"
#include "picker.h"
#include <KDirLister>
#include <QtTest>

class NavigationTests : public QObject {
  Q_OBJECT
  QTemporaryDir temporary;
  QUrl folder(const QString &name) {
    const auto path = temporary.path() + '/' + name;
    QDir().mkpath(path);
    return QUrl::fromLocalFile(path);
  }
  static QUrl file(const QUrl &base, int number) {
    return QUrl::fromLocalFile(base.toLocalFile() + QString("/File %1.txt").arg(number, 3, 10, QChar('0')));
  }
  static void listed(Browser *tab, int first = 0, int count = 200, bool complete = true) {
    // Feed the real KDirModel through KDirLister's public asynchronous signals.
    // No worker, user files, mounts or desktop D-Bus services are involved.
    tab->model->dirLister()->stop();
    KFileItemList items;
    for (int i = first; i < first + count; ++i)
      items << KFileItem(file(tab->location(), i), "text/plain", S_IFREG);
    emit tab->model->dirLister()->itemsAdded(tab->location(), items);
    if (complete) emit tab->model->dirLister()->listingDirCompleted(tab->location());
  }
  static void select(Browser *tab, const QList<QUrl> &urls) {
    tab->view()->clearSelection();
    for (const auto &url : urls) {
      const auto index = tab->proxy->mapFromSource(tab->model->indexForUrl(url));
      QVERIFY(index.isValid());
      tab->view()->selectionModel()->select(index, QItemSelectionModel::Select | QItemSelectionModel::Rows);
      tab->view()->selectionModel()->setCurrentIndex(index, QItemSelectionModel::NoUpdate);
    }
  }
private slots:
  void initTestCase() {
    QVERIFY(temporary.isValid());
    qApp->setQuitOnLastWindowClosed(false);
    qApp->setDesktopFileName("xetal-files");
  }
  void historyKeepsVisitsAndDropsOnlyTheForwardBranch() {
    PathBar bar;
    const auto a = folder("history-a"), b = folder("history-b"), c = folder("history-c");
    bar.setLocationUrl(a); bar.setVisitState({{"y", 123}, {"filter", "*.jpg"}});
    bar.setLocationUrl(b); bar.setVisitState({{"y", 456}});
    QVERIFY(bar.goBack()); QCOMPARE(bar.visitState().value("y").toInt(), 123);
    PathBar restored;
    restored.restoreSession(bar.session());
    QCOMPARE(restored.locationUrl(), a); QVERIFY(restored.goForward());
    QCOMPARE(restored.locationUrl(), b); QCOMPARE(restored.visitState().value("y").toInt(), 456);
    bar.setLocationUrl(c); QVERIFY(!bar.goForward());
    QVERIFY(bar.goBack()); QCOMPARE(bar.locationUrl(), a);
    QCOMPARE(bar.visitState().value("filter").toString(), QString("*.jpg"));
    for (int i = 0; i < 140; ++i) bar.setLocationUrl(QUrl("computer:/?visit=" + QString::number(i)));
    QCOMPARE(bar.historySize(), 100);
    restored.restoreSession(bar.session()); QCOMPARE(restored.historySize(), 100);
    const auto before = restored.session();
    restored.restoreSession({{"urls", QVariantList{a}}, {"visits", QVariantList{}}, {"position", -1}});
    QCOMPARE(restored.session(), before);
  }
  void folderViewsStaySeparate() {
    const auto a = QUrl::fromLocalFile(temporary.path() + "/a");
    const auto b = QUrl::fromLocalFile(temporary.path() + "/b");
    Fusion::Preferences prefs(temporary.path() + "/folder-views.ini");
    prefs.settings.setValue("view", 2);
    prefs.settings.setValue("preview", true);
    prefs.setFolderView(a, {{"view", 4}, {"preview", false}});
    QCOMPARE(prefs.folderView(a).value("view").toInt(), 4);
    QCOMPARE(prefs.folderView(QUrl(a.toString() + "/")).value("view").toInt(), 4);
    QCOMPARE(prefs.folderView(b).value("view").toInt(), 2);
    QVERIFY(prefs.folderView(b).value("preview").toBool());
    QCOMPARE(prefs.settings.value("view").toInt(), 2);
    prefs.folderViewScope = "picker/example/folderViews";
    QCOMPARE(prefs.folderView(a).value("view").toInt(), 2);
    prefs.setFolderView(a, {{"view", 3}});
    prefs.folderViewScope = "folderViews";
    QCOMPARE(prefs.folderView(a).value("view").toInt(), 4);
    prefs.setFolderView(QUrl("sftp://alice:secret@host/path/"), {{"view", 1}});
    QCOMPARE(prefs.folderView(QUrl("sftp://alice:changed@host/path")).value("view").toInt(), 1);
    for (const auto &key : prefs.settings.allKeys()) QVERIFY(!key.contains("secret") && !key.contains("alice"));
  }
  void backAndForwardRestoreAfterTheWholeListing_data() {
    QTest::addColumn<int>("mode");
    for (int mode = 0; mode < 5; ++mode) QTest::newRow(qPrintable(QString::number(mode))) << mode;
  }
  void backAndForwardRestoreAfterTheWholeListing() {
    QFETCH(int, mode);
    Fusion::Preferences prefs(temporary.path() + "/navigation-" + QString::number(mode) + ".ini");
    prefs.settings.setValue("thumbnails", false);
    Drives drives(nullptr, false);
    Browser tab(&prefs, &drives);
    const auto a = folder("navigation-a"), b = folder("navigation-b");
    tab.resize(700, 500); tab.show(); tab.navigate(a); listed(&tab);
    tab.setView(mode); tab.filter->setText("File");
    const QList<QUrl> selection{file(a, 175), file(a, 177)};
    select(&tab, selection);
    QTRY_VERIFY(tab.view()->verticalScrollBar()->maximum() > 0 || tab.view()->horizontalScrollBar()->maximum() > 0);
    tab.view()->verticalScrollBar()->setValue(tab.view()->verticalScrollBar()->maximum() / 2);
    tab.view()->horizontalScrollBar()->setValue(tab.view()->horizontalScrollBar()->maximum() / 2);
    const auto scroll = tab.view()->verticalScrollBar()->value();
    const auto horizontal = tab.view()->horizontalScrollBar()->value();
    tab.beginSearch(); // Searching must not replace the underlying folder selection.
    tab.navigate(b); listed(&tab); tab.setView(4); select(&tab, {file(b, 22)});
    QVERIFY(tab.navigator->goBack()); listed(&tab, 0, 100, false);
    QCoreApplication::processEvents(); QVERIFY(tab.selectedUrls().isEmpty());
    listed(&tab, 100, 100);
    QTRY_COMPARE(tab.selectedUrls(), selection);
    QCOMPARE(tab.filter->text(), QString("File")); QCOMPARE(tab.viewMode, mode);
    QTRY_COMPARE(tab.view()->verticalScrollBar()->value(), scroll);
    QTRY_COMPARE(tab.view()->horizontalScrollBar()->value(), horizontal);
    QVERIFY(tab.navigator->goForward()); listed(&tab);
    QTRY_COMPARE(tab.selectedUrls(), QList<QUrl>{file(b, 22)});
    QCOMPARE(tab.viewMode, 4); QVERIFY(tab.filter->text().isEmpty());
    // A cached selection may reference files deleted since the last visit.
    QVERIFY(tab.navigator->goBack()); listed(&tab, 0, 176);
    QTRY_COMPARE(tab.selectedUrls(), QList<QUrl>{file(a, 175)});
  }
  void newerNavigationAndExplicitSelectionWin() {
    Fusion::Preferences prefs(temporary.path() + "/async.ini");
    prefs.settings.setValue("thumbnails", false);
    Drives drives(nullptr, false); Browser tab(&prefs, &drives);
    const auto a = folder("async-a"), b = folder("async-b");
    tab.navigate(a); listed(&tab); select(&tab, {file(a, 80)});
    tab.navigate(b); listed(&tab); select(&tab, {file(b, 50)});
    QVERIFY(tab.navigator->goBack()); tab.model->dirLister()->stop();
    QVERIFY(tab.navigator->goForward()); listed(&tab, 0, 40, false);
    emit tab.model->dirLister()->listingDirCompleted(a);
    QCoreApplication::processEvents(); QVERIFY(tab.selectedUrls().isEmpty());
    listed(&tab, 40, 160); QTRY_COMPARE(tab.selectedUrls(), QList<QUrl>{file(b, 50)});
    QVERIFY(tab.navigator->goBack()); listed(&tab, 0, 40, false);
    tab.selectUrl(file(a, 120)); // Show in folder must take priority over old state.
    listed(&tab, 40, 160); QTRY_COMPARE(tab.selectedUrls(), QList<QUrl>{file(a, 120)});
  }
  void viewColumnsSortAndPreviewPersistPerFolder() {
    const auto a = folder("views-a"), b = folder("views-b");
    const auto path = temporary.path() + "/views.ini";
    Fusion::Preferences prefs(path);
    prefs.settings.setValue("thumbnails", false);
    Drives drives(nullptr, false);
    {
      Browser tab(&prefs, &drives);
      tab.navigate(a); listed(&tab); tab.setView(4); tab.setPreview(false, 345);
      tab.setHidden(true); tab.setThumbnails(true);
      tab.details->setColumnHidden(KDirModel::Owner, false);
      tab.details->header()->resizeSection(KDirModel::Name, 417);
      tab.details->sortByColumn(KDirModel::Size, Qt::DescendingOrder);
      tab.navigate(b); listed(&tab);
      QCOMPARE(tab.viewMode, 2); QVERIFY(tab.previewVisible);
      QVERIFY(!tab.model->dirLister()->showHiddenFiles()); QVERIFY(!tab.thumbnailsVisible);
      QVERIFY(tab.details->isColumnHidden(KDirModel::Owner));
      tab.setView(3); tab.setPreview(true, 260);
      QVERIFY(tab.navigator->goBack()); listed(&tab);
      QCOMPARE(tab.viewMode, 4); QVERIFY(!tab.previewVisible); QCOMPARE(tab.previewWidth, 345);
      QVERIFY(tab.model->dirLister()->showHiddenFiles()); QVERIFY(tab.thumbnailsVisible);
      QVERIFY(!tab.details->isColumnHidden(KDirModel::Owner));
      QCOMPARE(tab.details->columnWidth(KDirModel::Name), 417);
      QCOMPARE(tab.proxy->sortColumn(), int(KDirModel::Size));
      QCOMPARE(tab.proxy->sortOrder(), Qt::DescendingOrder);
    }
    prefs.settings.sync();
    Fusion::Preferences reopened(path); Browser tab(&reopened, &drives);
    tab.navigate(a); listed(&tab);
    QCOMPARE(tab.viewMode, 4); QVERIFY(!tab.previewVisible); QCOMPARE(tab.previewWidth, 345);
    tab.navigate(b); listed(&tab); QCOMPARE(tab.viewMode, 3); QCOMPARE(tab.previewWidth, 260);
  }
  void reopenClosedTabWithKeyboardRestoresHistoryAndSelection() {
    const auto a = folder("closed-a"), b = folder("closed-b");
    FilesWindow window(Fusion::computerUrl(), false, temporary.path() + "/closed.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show(); window.activateWindow();
    window.openLocation(a, true); listed(window.browser());
    window.browser()->setView(4); select(window.browser(), {file(a, 85)});
    window.openLocation(b); listed(window.browser());
    QVERIFY(window.browser()->navigator->goBack()); listed(window.browser());
    QTRY_COMPARE(window.browser()->selectedUrls(), QList<QUrl>{file(a, 85)});
    const auto saved = window.browser()->session();
    window.runAction("closeTab");
    auto *tabs = window.findChild<QTabWidget *>("folderTabs"); QCOMPARE(tabs->count(), 1);
    window.browser()->setFocus();
    QTest::keyClick(&window, Qt::Key_T, Qt::ControlModifier | Qt::ShiftModifier);
    QTRY_COMPARE(tabs->count(), 2); listed(window.browser());
    QTRY_COMPARE(window.browser()->selectedUrls(), QList<QUrl>{file(a, 85)});
    QCOMPARE(window.browser()->navigator->session(), saved);
    QVERIFY(!window.findChild<QAction *>("reopenClosedTabAction")->isEnabled());
    QVERIFY(window.browser()->navigator->goForward()); QCOMPARE(window.browser()->location(), b);
    window.browser()->model->dirLister()->stop();
    window.close();
  }
  void folderPreviewFollowsTabsAndKeepsItsWidth() {
    const QUrl a("computer:/?preview=a"), b("computer:/?preview=b");
    FilesWindow window(a, false, temporary.path() + "/preview.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
    auto *pane = window.findChild<QStackedWidget *>("previewStack");
    auto *split = qobject_cast<QSplitter *>(pane->parentWidget());
    auto sizes = split->sizes(); sizes[2] = 340; split->setSizes(sizes);
    const auto width = pane->width(); QVERIFY(width > 270);
    window.runAction("preview"); QVERIFY(!pane->isVisible());
    window.openLocation(b, true); QVERIFY(pane->isVisible());
    auto *tabs = window.findChild<QTabWidget *>("folderTabs"); tabs->setCurrentIndex(0);
    QVERIFY(!pane->isVisible()); window.runAction("preview");
    QTRY_COMPARE(pane->width(), width); window.close();
  }
  void pickerViewDoesNotOverwriteFiles() {
    const auto url = folder("picker-view");
    const auto path = temporary.path() + "/picker.ini";
    Fusion::Preferences prefs(path);
    prefs.setFolderView(url, {{"view", 4}, {"preview", false}});
    prefs.settings.sync();
    const QJsonObject request{{"method", "OpenFile"}, {"app_id", "org.example.Test"},
                             {"current_folder", url.toLocalFile()}};
    {
      PickerWindow picker(request, path, false);
      picker.setAttribute(Qt::WA_DeleteOnClose, false);
      picker.browser()->model->dirLister()->stop();
      QCOMPARE(picker.browser()->viewMode, 2);
      picker.browser()->setView(3); picker.browser()->setPreview(true, 310);
      picker.close();
    }
    prefs.settings.sync();
    QCOMPARE(prefs.folderView(url).value("view").toInt(), 4);
    QVERIFY(!prefs.folderView(url).value("preview").toBool());
    PickerWindow reopened(request, path, false);
    reopened.setAttribute(Qt::WA_DeleteOnClose, false);
    reopened.browser()->model->dirLister()->stop();
    QCOMPARE(reopened.browser()->viewMode, 3); QCOMPARE(reopened.browser()->previewWidth, 310);
    reopened.close();
  }
  void navigationSidebarKeepsItsSavedWidth() {
    const auto path = temporary.path() + "/sidebar.ini";
    int sidebarWidth = 0, previewWidth = 0;
    {
      FilesWindow window(Fusion::computerUrl(), false, path);
      window.setAttribute(Qt::WA_DeleteOnClose, false); window.show();
      auto *tree = window.findChild<QTreeWidget *>("places");
      auto *split = qobject_cast<QSplitter *>(tree->parentWidget());
      auto sizes = split->sizes(); sizes[0] = 275; sizes[2] = 335;
      split->setSizes(sizes); QTest::qWait(10);
      sidebarWidth = tree->width(); previewWidth = split->widget(2)->width();
      QVERIFY(sidebarWidth > 210); QVERIFY(previewWidth > 270);
      window.close();
    }
    FilesWindow reopened(Fusion::computerUrl(), false, path);
    reopened.setAttribute(Qt::WA_DeleteOnClose, false); reopened.show();
    auto *tree = reopened.findChild<QTreeWidget *>("places");
    QTRY_VERIFY(qAbs(tree->width() - sidebarWidth) <= 3);
    QTRY_VERIFY(qAbs(reopened.findChild<QStackedWidget *>("previewStack")->width() - previewWidth) <= 3);
    reopened.close();
  }
  void compactToolbarAndComputerCapture() {
    FilesWindow window(Fusion::computerUrl(), false, temporary.path() + "/layout.ini");
    window.setAttribute(Qt::WA_DeleteOnClose, false);
    if (window.browser()->previewVisible) window.runAction("preview");
    window.drives->volumes = Drives::parse(R"({"blockdevices":[
      {"path":"/dev/fusion-a","type":"disk","model":"Samsung SSD 970 EVO Plus 2TB","tran":"nvme","size":2000000000000,"children":[
        {"path":"/dev/fusion-a1","type":"part","fstype":"ext4","label":"HyperFusion","size":1998000000000,"mountpoints":["/"]},
        {"path":"/dev/fusion-a2","type":"part","fstype":"vfat","label":"FUSION_EFI","size":1024000000,"mountpoints":["/boot/efi"]},
        {"path":"/dev/fusion-a3","type":"part","parttype":"21686148-6449-6e6f-744e-656564454649","size":1000000}]},
      {"path":"/dev/fusion-b","type":"disk","model":"SATA SSD","tran":"sata","size":1000000000000,"children":[
        {"path":"/dev/fusion-b1","type":"part","fstype":"apfs","label":"Storage","size":999000000000},
        {"path":"/dev/fusion-b2","type":"part","fstype":"vfat","label":"EFI","size":200000000}]},
      {"path":"/dev/fusion-c","type":"disk","model":"Samsung SSD 970 EVO Plus 1TB","tran":"nvme","size":1000000000000,"fstype":"ntfs","label":"Windows_10_Guest_NVME"},
      {"path":"/dev/fusion-d","type":"disk","model":"SATA SSD","tran":"sata","size":1000000000000,"fstype":"ext4","label":"Projects"}
    ]})");
    for (auto &volume : window.drives->volumes) if (volume.mounted()) {
      volume.total = volume.size; volume.available = volume.size * .64; volume.spaceKnown = true;
    }
    emit window.drives->changed(); window.resize(1440, 850); window.show();
    // Allow the normal appearance helper and Qt layouts to finish.
    QTest::qWait(500);
    auto *toolbar = window.findChild<QToolBar *>("filesToolbar");
    auto *bar = window.findChild<QTabBar *>("folderTabBar");
    QVERIFY(toolbar->isAncestorOf(window.browser()->navigationRow));
    QVERIFY(bar->height() < 42);
    QVERIFY(window.browser()->mapTo(&window, QPoint()).y() < 100);
    auto *shelf = window.browser()->findChild<DriveShelf *>();
    for (auto *usage : shelf->findChildren<QProgressBar *>("volumeUsage"))
      if (usage->isVisible()) QVERIFY(usage->height() <= 6);
    const auto artifacts = qEnvironmentVariable("FUSION_FILES_ARTIFACTS");
    if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/compact-computer.png"));
    window.activateWindow(); shelf->selectDevice("/dev/fusion-c", true);
    VolumeCard *focusedCard = nullptr;
    for (auto *card : shelf->findChildren<VolumeCard *>())
      if (card->volume().device == "/dev/fusion-c") focusedCard = card;
    QVERIFY(focusedCard);
    QTRY_VERIFY(focusedCard->findChild<QPushButton *>("mountVolume")->isVisible());
    if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/shelf-mount.png"));
    shelf->findChild<QToolButton *>("computerListView")->click();
    QTRY_VERIFY(focusedCard->height() < 104);
    QTest::qWait(100);
    if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/storage-list.png"));
    shelf->findChild<QToolButton *>("computerShelfView")->click();
    shelf->selectDevice({}); window.browser()->navigator->editor()->setFocus();
    window.resize(760, 500); QTest::qWait(100);
    QCOMPARE(window.width(), 760);
    QVERIFY(window.browser()->navigator->editor()->isVisible());
    QVERIFY(window.browser()->navigator->editor()->width() >= 160);
    const auto *address = window.browser()->navigationRow.data();
    const auto *editor = window.browser()->navigator->editor();
    const auto *filter = window.browser()->filter;
    const QRect editorRect(editor->mapTo(address, QPoint()), editor->size());
    const QRect filterRect(filter->mapTo(address, QPoint()), filter->size());
    QVERIFY(address->rect().contains(editorRect));
    QVERIFY(address->rect().contains(filterRect));
    QVERIFY(!editorRect.intersects(filterRect));
    QVERIFY(window.findChild<QToolButton *>("fileOptions")->isVisible());
    auto *controls = window.findChild<QWidget *>("windowControls");
    QVERIFY(controls->isVisible());
    QVERIFY(window.rect().contains(QRect(controls->mapTo(&window, QPoint()), controls->size())));
    if (!artifacts.isEmpty()) QVERIFY(window.grab().save(artifacts + "/compact-small.png"));
    auto *scroll = window.browser()->findChild<QScrollArea *>("computerDrivesScroll");
    QVERIFY(scroll->verticalScrollBar()->maximum() > 0);
    auto *row = shelf->findChildren<VolumeCard *>().last();
    shelf->selectDevice(row->volume().device);
    const auto device = window.browser()->selectedVolume().device;
    scroll->verticalScrollBar()->setValue(scroll->verticalScrollBar()->maximum() / 2);
    const auto position = scroll->verticalScrollBar()->value();
    window.openLocation(folder("after-computer")); window.browser()->model->dirLister()->stop();
    shelf->selectDevice({}); scroll->verticalScrollBar()->setValue(0);
    QVERIFY(window.browser()->navigator->goBack());
    QTRY_COMPARE(window.browser()->selectedVolume().device, device);
    QTRY_COMPARE(scroll->verticalScrollBar()->value(), position);
    window.close();
  }
};
QTEST_MAIN(NavigationTests)
#include "navigation_tests.moc"
