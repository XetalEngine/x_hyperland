#include "search_presets.h"
#include "window.h"
#include <QScopeGuard>
#include <QtTest>

class SearchWindow : public FilesWindow {
public:
  SearchWindow(const QString &folder, const QString &settings)
      : FilesWindow(QUrl::fromLocalFile(folder), false, settings) {
    setAttribute(Qt::WA_DeleteOnClose, false);
  }
  QList<QUrl> opened;

protected:
  void openItem(const KFileItem &item, bool = false) override {
    opened << item.url();
  }
};

class SearchTests : public QObject {
  Q_OBJECT
  QTemporaryDir temporary;
  QString folder;
  static void write(const QString &path, const QByteArray &contents) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile file(path);
    QVERIFY(file.open(QIODevice::WriteOnly));
    QCOMPARE(file.write(contents), contents.size());
  }
  static void show(SearchWindow &window) {
    window.resize(1200, 800);
    window.show();
    window.activateWindow();
    window.browser()->view()->setFocus();
    QTest::qWait(60);
  }
  static QPushButton *button(QWidget *widget, const QString &text) {
    for (auto *candidate : widget->findChildren<QPushButton *>())
      if (candidate->text() == text)
        return candidate;
    return nullptr;
  }
  static void screenshot(QWidget *widget, const QString &name) {
    const auto directory = qEnvironmentVariable("FUSION_FILES_TEST_SHOTS");
    if (!directory.isEmpty()) {
      QDir().mkpath(directory);
      widget->grab().save(directory + "/" + name + ".png");
    }
  }
  static bool advanced(SearchPane *pane, const QString &query,
                       bool regex = false) {
    bool applied = false;
    QTimer::singleShot(0, pane, [&] {
      auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      if (!dialog)
        return;
      auto *text = dialog->findChild<QLineEdit *>("advancedQuery");
      auto *contents = dialog->findChild<QCheckBox *>("searchContents");
      auto *mode = dialog->findChild<QComboBox *>("contentMatchMode");
      auto *workers = dialog->findChild<QSpinBox *>("searchWorkers");
      if (!text || !contents || !mode || !workers) {
        dialog->reject();
        return;
      }
      text->setText(query);
      contents->setChecked(true);
      mode->setCurrentIndex(regex ? 1 : 0);
      workers->setValue(3);
      dialog->findChild<QLineEdit *>("searchNamePatterns")->setText("*.txt");
      QTest::qWait(60);
      screenshot(dialog, "advanced-search");
      applied = true;
      dialog->findChild<QDialogButtonBox *>()
          ->button(QDialogButtonBox::Ok)
          ->click();
    });
    auto *check = pane->findChild<QCheckBox *>("advancedSearch");
    if (check->isChecked())
      pane->findChild<QPushButton *>("searchOptions")->click();
    else
      check->setChecked(true);
    return applied;
  }
private slots:
  void initTestCase() {
    QVERIFY(temporary.isValid());
    qApp->setQuitOnLastWindowClosed(false);
    qApp->setDesktopFileName("xetal-files");
    folder = temporary.path() + "/Search examples";
    write(folder + "/holiday.JPG", "image fixture");
    write(folder + "/README", "extensionless fixture");
    write(folder + "/Project notes.txt",
          "Start\r\nBLABLABAL twice BLABLABAL\r\nEnd\r\n");
    write(folder + "/Project/report.txt",
          "Nothing here\nBLABLABAL in the project\nOne more BLABLABAL\n");
    write(folder + "/Project/unrelated.csv", "BLABLABAL\n");
  }
  void extensionsNormalizeAndRejectMistakes() {
    QStringList values;
    QString error;
    QVERIFY(FusionSearch::extensions(".txt, HTML, *.cpp\npy; .tar.gz, .txt",
                                     &values, &error));
    QCOMPARE(values, QStringList({".txt", ".HTML", ".cpp", ".py", ".tar.gz"}));
    QCOMPARE(FusionSearch::extensionPatterns(values),
             QString("*.txt;*.HTML;*.cpp;*.py;*.tar.gz"));
    QCOMPARE(FusionSearch::extensionText("*.txt;*.cpp"), QString(".txt, .cpp"));
    for (const auto &invalid :
         {".", "../txt", "*.foo*", "foo?", "c:\\txt", "[ab]"}) {
      QVERIFY2(!FusionSearch::extensions(invalid, &values, &error), invalid);
      QVERIFY(!error.isEmpty());
    }
    QVERIFY(FusionSearch::extensions(" , \n", &values, &error));
    QVERIFY(values.isEmpty());
    QVERIFY(error.isEmpty());
  }
  void presetFilesRoundTripValidateAndWatch() {
    const auto directory = temporary.path() + "/preset-store";
    SearchPresets presets(directory);
    QSignalSpy changed(&presets, &SearchPresets::changed);
    QString error;
    auto chosen = FusionSearch::defaults();
    chosen["query"] = "needle[0-9]+";
    chosen["root"] = folder;
    chosen["contents"] = true;
    chosen["regex"] = true;
    chosen["extensions"] = ".txt, HTML, *.cpp";
    chosen["workers"] = 7;
    QVERIFY(presets.save("Notes and code", chosen, false, &error));
    const auto path = presets.pathForName("Notes and code");
    QCOMPARE(presets.files(), QStringList{path});
    QVERIFY(!changed.isEmpty());
    QJsonObject loaded;
    QVERIFY(SearchPresets::load(path, &loaded, &error));
    QCOMPARE(loaded["extensions"].toString(), QString(".txt, .HTML, .cpp"));
    QCOMPARE(loaded["types"].toString(), QString("*.txt;*.HTML;*.cpp"));
    QCOMPARE(loaded["workers"].toInt(), 7);
    QVERIFY(!(QFile::permissions(path) &
              (QFileDevice::ReadGroup | QFileDevice::ReadOther)));
    chosen["workers"] = 3;
    QVERIFY(!presets.save("Notes and code", chosen, false, &error));
    QVERIFY(SearchPresets::load(path, &loaded, &error));
    QCOMPARE(loaded["workers"].toInt(), 7);
    QVERIFY(presets.save("Notes and code", chosen, true, &error));
    QVERIFY(SearchPresets::load(path, &loaded, &error));
    QCOMPARE(loaded["workers"].toInt(), 3);
    QVERIFY(presets.pathForName("../outside").isEmpty());
    QVERIFY(!presets.save("../outside", chosen, true, &error));
    const auto second = directory + "/Externally copied.json";
    QVERIFY(QFile::copy(path, second));
    QTRY_COMPARE_WITH_TIMEOUT(presets.files().size(), 2, 2500);
    QVERIFY(QFile::remove(path));
    QTRY_COMPARE_WITH_TIMEOUT(presets.files(), QStringList{second}, 2500);
    QVERIFY(QDir(directory).removeRecursively());
    QTRY_VERIFY_WITH_TIMEOUT(presets.files().isEmpty(), 2500);
    QVERIFY(presets.save("After folder recreation", chosen, false, &error));
    QCOMPARE(presets.files().size(), 1);
    const auto valid = presets.files().first();
    auto invalid = chosen;
    invalid["workers"] = 33;
    QVERIFY(!presets.save("Invalid", invalid, false, &error));
    invalid = chosen;
    invalid["contents"] = "true";
    QVERIFY(!presets.save("Invalid", invalid, false, &error));
    invalid = chosen;
    invalid["min_size"] = 3 * 1048576;
    invalid["max_size"] = 1048576;
    QVERIFY(!presets.save("Invalid", invalid, false, &error));
    const auto bad = directory + "/Invalid.json";
    const auto before = loaded;
    write(bad, "{broken json");
    QVERIFY(!SearchPresets::load(bad, &loaded, &error));
    QCOMPARE(loaded, before);
    write(bad, QByteArray(128 * 1024 + 1, 'x'));
    QVERIFY(!SearchPresets::load(bad, &loaded, &error));
    QCOMPARE(loaded, before);
    write(bad,
          R"({"format":"hyperfusion.files.search","version":2,"settings":{}})");
    QVERIFY(!SearchPresets::load(bad, &loaded, &error));
    QVERIFY(QFile::link(valid, directory + "/Linked.json"));
    QVERIFY(!presets.save("Linked", chosen, true, &error));
    QVERIFY(error.contains("symbolic"));
  }
  void editableExtensionGroupsFilterRealResults() {
    SearchWindow window(folder, temporary.path() + "/extensions.ini");
    show(window);
    window.runAction("search");
    auto *pane = window.browser()->search;
    bool checked = false;
    QTimer::singleShot(0, pane, [&] {
      auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      QVERIFY(dialog);
      auto cleanup = qScopeGuard([dialog] {
        if (dialog->isVisible())
          dialog->reject();
      });
      auto *editor = dialog->findChild<QPlainTextEdit *>("searchExtensions");
      QVERIFY(editor);
      QCOMPARE(editor->lineWrapMode(), QPlainTextEdit::WidgetWidth);
      QCOMPARE(editor->wordWrapMode(),
               QTextOption::WrapAtWordBoundaryOrAnywhere);
      auto group = [dialog](int index) {
        return dialog->findChild<QCheckBox *>("searchTypeGroup" +
                                              QString::number(index));
      };
      group(0)->setChecked(true);
      QVERIFY(editor->toPlainText().contains(".txt"));
      QVERIFY(!editor->toPlainText().contains('*'));
      group(4)->setChecked(true);
      group(0)->setChecked(false);
      QVERIFY(editor->toPlainText().contains(".log"));
      QVERIFY(!editor->toPlainText().contains(".txt"));
      editor->setPlainText(".txt, .custom, .html");
      group(1)->setChecked(true);
      QVERIFY(editor->toPlainText().contains(".cpp"));
      group(2)->setChecked(true);
      screenshot(dialog, "search-extensions");
      group(1)->setChecked(false);
      QVERIFY(editor->toPlainText().contains(".custom"));
      QVERIFY(editor->toPlainText().contains(".html"));
      editor->setPlainText(".csv");
      dialog->findChild<QCheckBox *>("searchContents")->setChecked(true);
      dialog->findChild<QLineEdit *>("advancedQuery")->setText("BLABLABAL");
      dialog->findChild<QLineEdit *>("searchNamePatterns")->setText("*");
      checked = true;
      dialog->findChild<QDialogButtonBox *>()
          ->button(QDialogButtonBox::Ok)
          ->click();
    });
    pane->findChild<QCheckBox *>("advancedSearch")->setChecked(true);
    QVERIFY(checked);
    QTRY_VERIFY_WITH_TIMEOUT(!pane->running(), 10000);
    QCOMPARE(pane->results->model()->rowCount(), 1);
    QCOMPARE(pane->results->model()->index(0, 0).data().toString(),
             QString("unrelated.csv"));
  }
  void presetsRestoreWholeDialogAndDisappearWhenDeleted() {
    QVERIFY(qEnvironmentVariable("FUSION_FILES_ISOLATED") == "1");
    SearchWindow window(folder, temporary.path() + "/presets-ui.ini");
    show(window);
    window.runAction("search");
    auto *pane = window.browser()->search;
    const auto presetDirectory =
        Fusion::root() + "/file_manager/state/search-presets";
    const auto first = presetDirectory + "/Regression search.json";
    const auto second = presetDirectory + "/Regression copy.json";
    auto filesCleanup = qScopeGuard([&] {
      QFile::remove(first);
      QFile::remove(second);
    });
    bool checked = false;
    QTimer::singleShot(0, pane, [&] {
      auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      QVERIFY(dialog);
      auto cleanup = qScopeGuard([dialog] {
        if (dialog->isVisible())
          dialog->reject();
      });
      auto edit = [dialog](const QString &name) {
        return dialog->findChild<QLineEdit *>(name);
      };
      auto check = [dialog](const QString &name) {
        return dialog->findChild<QCheckBox *>(name);
      };
      auto spin = [dialog](const QString &name) {
        return dialog->findChild<QSpinBox *>(name);
      };
      auto combo = [dialog](const QString &name) {
        return dialog->findChild<QComboBox *>(name);
      };
      auto save = [dialog](const QString &name) {
        QTimer::singleShot(0, dialog, [name] {
          if (auto *prompt = qobject_cast<QInputDialog *>(
                  QApplication::activeModalWidget())) {
            prompt->setTextValue(name);
            prompt->accept();
          }
        });
        dialog->findChild<QPushButton *>("saveSearchPreset")->click();
      };
      edit("searchRoot")->setText(folder + "/Project");
      edit("advancedQuery")->setText("needle[0-9]+");
      check("searchContents")->setChecked(true);
      combo("contentMatchMode")->setCurrentIndex(1);
      edit("searchNamePatterns")->setText("*.txt;*.cpp");
      edit("searchExclusions")->setText("build;node_modules");
      auto *extensions =
          dialog->findChild<QPlainTextEdit *>("searchExtensions");
      extensions->setPlainText(".txt, .cpp, .custom");
      for (const auto &key : {"recursive", "hidden", "case", "word", "follow",
                              "binary", "multiline", "folders"})
        check("searchFlag_" + QString(key))
            ->setChecked(QString(key) != "folders" &&
                         QString(key) != "recursive");
      spin("searchMinimumSize")->setValue(2);
      spin("searchMaximumSize")->setValue(16);
      check("searchAfterEnabled")->setChecked(true);
      check("searchBeforeEnabled")->setChecked(true);
      auto *from = dialog->findChild<QDateEdit *>("searchAfterDate");
      auto *to = dialog->findChild<QDateEdit *>("searchBeforeDate");
      from->setDate(QDate(2020, 1, 2));
      to->setDate(QDate(2024, 1, 3));
      combo("searchEncoding")
          ->setCurrentIndex(combo("searchEncoding")->findData("windows-1252"));
      spin("searchWorkers")->setValue(5);
      spin("searchResultLimit")->setValue(321);
      save("Regression search");
      QVERIFY(QFileInfo::exists(first));
      auto *list = combo("searchPresetList");
      QCOMPARE(list->currentData().toString(), first);
      QJsonObject saved;
      QString error;
      QVERIFY(SearchPresets::load(first, &saved, &error));
      edit("searchRoot")->clear();
      edit("advancedQuery")->setText("changed");
      check("searchContents")->setChecked(false);
      combo("contentMatchMode")->setCurrentIndex(0);
      edit("searchNamePatterns")->clear();
      edit("searchExclusions")->clear();
      extensions->clear();
      for (auto *flag : dialog->findChildren<QCheckBox *>(
               QRegularExpression("searchFlag_.*")))
        flag->setChecked(false);
      spin("searchMinimumSize")->setValue(0);
      spin("searchMaximumSize")->setValue(0);
      check("searchAfterEnabled")->setChecked(false);
      check("searchBeforeEnabled")->setChecked(false);
      from->setDate(QDate::currentDate());
      to->setDate(QDate::currentDate());
      combo("searchEncoding")->setCurrentIndex(0);
      spin("searchWorkers")->setValue(1);
      spin("searchResultLimit")->setValue(1);
      dialog->findChild<QPushButton *>("loadSearchPreset")->click();
      QCOMPARE(edit("advancedQuery")->text(), QString("needle[0-9]+"));
      QCOMPARE(extensions->toPlainText(), QString(".txt, .cpp, .custom"));
      QCOMPARE(spin("searchWorkers")->value(), 5);
      QVERIFY(!pane->running());
      save("Regression copy");
      QJsonObject reSaved;
      QVERIFY(SearchPresets::load(second, &reSaved, &error));
      QCOMPARE(reSaved,
               saved); // Every field must survive a UI load/save round trip.
      screenshot(dialog, "search-presets");
      QVERIFY(QFile::remove(second));
      QTRY_COMPARE_WITH_TIMEOUT(list->findData(second), -1, 2500);
      QVERIFY(list->currentData().toString().isEmpty());
      QVERIFY(
          !dialog->findChild<QPushButton *>("loadSearchPreset")->isEnabled());
      QCOMPARE(edit("advancedQuery")->text(), QString("needle[0-9]+"));
      QVERIFY(QFile::remove(first));
      QTRY_COMPARE_WITH_TIMEOUT(list->count(), 1, 2500);
      checked = true;
    });
    pane->findChild<QCheckBox *>("advancedSearch")->setChecked(true);
    QVERIFY(checked);
    QVERIFY(pane->query->text().isEmpty());
  }
  void shortcutsFocusAndIndependentFilter() {
    SearchWindow window(folder, temporary.path() + "/keys.ini");
    show(window);
    auto *tab = window.browser();
    tab->filter->setText("notes");
    QTest::keyClick(&window, Qt::Key_F, Qt::ControlModifier);
    QVERIFY(tab->searchActive());
    QVERIFY(tab->search->query->hasFocus());
    QCOMPARE(tab->filter->text(), QString("notes"));
    QVERIFY(tab->filter->isVisible());
    QVERIFY(!tab->stack->isVisible());
    QTest::keyClicks(tab->search->query, "*.jpg");
    QTest::keyClick(tab->search->query, Qt::Key_Return);
    QTRY_COMPARE_WITH_TIMEOUT(tab->search->results->model()->rowCount(), 1,
                              10000);
    QTRY_VERIFY(!tab->search->running());
    QCOMPARE(tab->search->results->model()->index(0, 0).data().toString(),
             QString("holiday.JPG"));
    QTest::keyClick(&window, Qt::Key_F,
                    Qt::ControlModifier | Qt::ShiftModifier);
    QVERIFY(!tab->searchActive());
    QVERIFY(tab->filter->hasFocus());
    QVERIFY(tab->stack->isVisible());
    QCOMPARE(tab->filter->selectedText(), QString("notes"));
    QTest::keyClick(&window, Qt::Key_F, Qt::ControlModifier);
    QVERIFY(tab->search->query->hasFocus());
    QCOMPARE(tab->search->query->selectedText(), QString("*.jpg"));
    QTest::keyClick(tab->search->query, Qt::Key_Escape);
    QVERIFY(!tab->searchActive());
  }
  void contentResultsPreviewAndReveal() {
    SearchWindow window(folder, temporary.path() + "/content.ini");
    show(window);
    window.runAction("search");
    auto *pane = window.browser()->search;
    QVERIFY(advanced(pane, "BLABLABAL"));
    QTRY_VERIFY_WITH_TIMEOUT(!pane->running(), 10000);
    QCOMPARE(pane->results->model()->rowCount(), 3);
    pane->results->sortByColumn(0, Qt::AscendingOrder);
    auto *model = pane->results->model();
    QCOMPARE(model->index(0, 0).data().toString(),
             QString("Project notes.txt"));
    QCOMPARE(model->index(0, 2).data().toInt(), 2);
    QCOMPARE(model->index(0, 3).data().toInt(), 2);
    QCOMPARE(model->index(0, 5).data().toString(),
             folder + "/Project notes.txt");
    QVERIFY(model->index(0, 6).data().toString().contains("BLABLABAL"));
    pane->results->setCurrentIndex(model->index(0, 0));
    pane->results->setFocus();
    QCOMPARE(window.browser()->selectedUrls(),
             QList<QUrl>{QUrl::fromLocalFile(folder + "/Project notes.txt")});
    window.runAction("copyPath");
    QCOMPARE(QApplication::clipboard()->text(), folder + "/Project notes.txt");
    bool previewed = false;
    QTimer::singleShot(0, pane, [&] {
      auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      if (!dialog)
        return;
      auto *text = dialog->findChild<QPlainTextEdit *>();
      previewed = text && text->isReadOnly() &&
                  text->toPlainText().contains("BLABLABAL");
      dialog->reject();
    });
    window.runAction("open");
    QVERIFY(previewed);
    QVERIFY(window.opened.isEmpty());
    screenshot(&window, "search-results");
    QVERIFY(button(pane, "Open file"));
    button(pane, "Open file")->click();
    QCOMPARE(window.opened.size(), 1);
    // Destructive keyboard commands must never target a stale folder selection.
    window.runAction("trash");
    QVERIFY(QFileInfo::exists(folder + "/Project notes.txt"));
    pane->results->setCurrentIndex(model->index(1, 0));
    QVERIFY(button(pane, "Show in folder"));
    button(pane, "Show in folder")->click();
    QVERIFY(!window.browser()->searchActive());
    QCOMPARE(window.browser()->location().toLocalFile(), folder + "/Project");
    QTRY_COMPARE(
        window.browser()->selectedUrls(),
        QList<QUrl>{QUrl::fromLocalFile(folder + "/Project/report.txt")});
  }
  void invalidRegexAndRecovery() {
    SearchWindow window(folder, temporary.path() + "/errors.ini");
    show(window);
    window.runAction("search");
    auto *pane = window.browser()->search;
    QVERIFY(advanced(pane, "[", true));
    QTRY_VERIFY_WITH_TIMEOUT(!pane->running(), 10000);
    QCOMPARE(pane->results->model()->rowCount(), 0);
    QVERIFY(pane->findChild<QLabel *>("searchStatus")
                ->text()
                .contains("regex", Qt::CaseInsensitive));
    pane->query->setText("BLA[A-Z]+");
    pane->start();
    QTRY_VERIFY_WITH_TIMEOUT(!pane->running(), 10000);
    QCOMPARE(pane->results->model()->rowCount(), 3);
  }
  void cancelRestartAndCloseDiscardOldResults() {
    SearchWindow window(folder, temporary.path() + "/cancel.ini");
    show(window);
    window.runAction("search");
    auto *pane = window.browser()->search;
    for (int i = 0; i < 5; ++i) {
      pane->query->setText("*");
      pane->start();
      pane->cancel();
    }
    pane->query->setText("no-file-has-this-name");
    pane->start();
    QTRY_VERIFY_WITH_TIMEOUT(!pane->running(), 10000);
    QCOMPARE(pane->results->model()->rowCount(), 0);
    QVERIFY(pane->findChild<QLabel *>("searchStatus")
                ->text()
                .startsWith("Finished"));
    pane->query->setText("*");
    pane->start();
    window.close();
    QVERIFY(!pane->running());
    auto readersStopped = [] {
      const auto processes = qApp->findChildren<QProcess *>();
      return std::all_of(processes.cbegin(), processes.cend(),
                         [](QProcess *process) {
                           return process->state() == QProcess::NotRunning;
                         });
    };
    QTRY_VERIFY_WITH_TIMEOUT(readersStopped(), 3000);
  }
  void changingFolderClearsOldResults() {
    SearchWindow window(folder, temporary.path() + "/scope.ini");
    show(window);
    window.runAction("search");
    auto *pane = window.browser()->search;
    pane->query->setText("*.jpg");
    pane->start();
    QTRY_VERIFY_WITH_TIMEOUT(!pane->running(), 10000);
    QCOMPARE(pane->results->model()->rowCount(), 1);
    window.browser()->closeSearch();
    window.runAction("search");
    QCOMPARE(pane->results->model()->rowCount(), 1);
    window.openLocation(QUrl::fromLocalFile(folder + "/Project"));
    window.runAction("search");
    QCOMPARE(pane->results->model()->rowCount(), 0);
    pane->query->setText("*.txt");
    pane->start();
    QTRY_VERIFY_WITH_TIMEOUT(!pane->running(), 10000);
    QCOMPARE(pane->results->model()->rowCount(), 1);
    QCOMPARE(pane->results->model()->index(0, 0).data().toString(),
             QString("report.txt"));
  }
  void cancellingAdvancedKeepsSimpleSearch() {
    SearchWindow window(folder, temporary.path() + "/advanced-cancel.ini");
    show(window);
    window.runAction("search");
    auto *pane = window.browser()->search;
    QTimer::singleShot(0, pane, [] {
      if (auto *dialog =
              qobject_cast<QDialog *>(QApplication::activeModalWidget()))
        dialog->reject();
    });
    pane->findChild<QCheckBox *>("advancedSearch")->setChecked(true);
    QVERIFY(!pane->findChild<QCheckBox *>("advancedSearch")->isChecked());
    QVERIFY(!pane->findChild<QPushButton *>("searchOptions")->isVisible());
    pane->query->setText("*.");
    pane->start();
    QTRY_VERIFY_WITH_TIMEOUT(!pane->running(), 10000);
    QVERIFY(pane->results->model()->rowCount() >= 1);
  }
};
QTEST_MAIN(SearchTests)
#include "search_tests.moc"
