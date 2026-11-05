#include "picker.h"
#include <QtTest>

class PickerTests : public QObject {
  Q_OBJECT
  QTemporaryDir temp;
  QString folder;
  QJsonObject request(const QString &method = "OpenFile") {
    return {{"method", method}, {"app_id", "org.example.PickerTest"},
            {"current_folder", folder}, {"title", "Choose a file"}};
  }
  QString settings() { return temp.path()+"/settings.ini"; }
  void prepare(PickerWindow &picker) {
    picker.setAttribute(Qt::WA_DeleteOnClose, false);
    picker.show();
    QTRY_VERIFY(picker.browser()->model->rowCount() >= 3);
  }
  QJsonObject result(QSignalSpy &spy) {
    return spy.isEmpty() ? QJsonObject{} : spy.first().first().toJsonObject();
  }
private slots:
  void initTestCase() {
    qApp->setQuitOnLastWindowClosed(false);
    folder = temp.path()+"/fixtures";
    QVERIFY(QDir().mkpath(folder+"/Folder"));
    for (const auto &name : {"notes %.txt", "photo.png", "executable.sh"}) {
      QFile file(folder+'/'+name); QVERIFY(file.open(QIODevice::WriteOnly)); file.write("test data");
    }
    QFile::setPermissions(folder+"/executable.sh", QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
  }
  void openExecutableReturnsUri() {
    PickerWindow picker(request(), settings(), false); prepare(picker);
    QSignalSpy spy(&picker, &PickerWindow::finished);
    const QUrl url = QUrl::fromLocalFile(folder+"/executable.sh");
    const KFileItem item(url);
    emit picker.browser()->openRequested(item, false);
    QCOMPARE(spy.size(), 1);
    QCOMPARE(result(spy)["uris"].toArray().first().toString(), url.toString(QUrl::FullyEncoded));
  }
  void multiSelectionAndEncodedNames() {
    auto input = request(); input["multiple"] = true;
    PickerWindow picker(input, settings(), false); prepare(picker);
    auto *browser = picker.browser();
    auto *selection = browser->view()->selectionModel();
    for (const auto &name : {"notes %.txt", "photo.png"}) {
      const auto index = browser->proxy->mapFromSource(browser->model->indexForUrl(QUrl::fromLocalFile(folder+'/'+name)));
      QVERIFY(index.isValid()); selection->select(index, QItemSelectionModel::Select | QItemSelectionModel::Rows);
    }
    QCOMPARE(browser->selectedUrls().size(), 2);
    QSignalSpy spy(&picker, &PickerWindow::finished); picker.acceptSelection();
    QVERIFY2(!spy.isEmpty(), qPrintable(browser->notice->text()));
    QCOMPARE(result(spy)["uris"].toArray().size(), 2);
    QVERIFY(QJsonDocument(result(spy)).toJson().contains("notes%20%25.txt"));
  }
  void filtersAndDirectorySelection() {
    auto input = request(); input["filters"] = QJsonArray{QJsonArray{"Images", QJsonArray{QJsonArray{0, "*.png"}}}};
    PickerWindow picker(input, settings(), false); prepare(picker);
    QTRY_COMPARE(picker.browser()->proxy->rowCount(), 2); // Directory plus PNG.
    picker.close();
    input["directory"] = true;
    PickerWindow dirs(input, settings(), false); prepare(dirs);
    QTRY_COMPARE(dirs.browser()->proxy->rowCount(), 1);
    QSignalSpy spy(&dirs, &PickerWindow::finished); dirs.acceptSelection();
    QCOMPARE(result(spy)["uris"].toArray().first().toString(), QUrl::fromLocalFile(folder).toString());
  }
  void saveExtensionAndOverwriteCancel() {
    auto input = request("SaveFile");
    input["filters"] = QJsonArray{QJsonArray{"PNG image", QJsonArray{QJsonArray{0, "*.png"}}}};
    PickerWindow picker(input, settings(), false); prepare(picker);
    picker.findChild<QLineEdit *>("pickerName")->setText("new image");
    QSignalSpy spy(&picker, &PickerWindow::finished); picker.acceptSelection();
    QCOMPARE(result(spy)["uris"].toArray().first().toString(), QUrl::fromLocalFile(folder+"/new image.png").toString(QUrl::FullyEncoded));
    QVERIFY(!QFileInfo::exists(folder+"/new image.png")); // Chooser never writes content.
    PickerWindow overwrite(input, settings(), false); prepare(overwrite);
    overwrite.findChild<QLineEdit *>("pickerName")->setText("photo");
    QSignalSpy cancelled(&overwrite, &PickerWindow::finished);
    QTimer::singleShot(30, [] { for (auto *widget : QApplication::topLevelWidgets())
      if (auto *box = qobject_cast<QMessageBox *>(widget)) box->done(QMessageBox::Cancel); });
    overwrite.acceptSelection();
    QCOMPARE(cancelled.size(), 0); QVERIFY(overwrite.isVisible()); overwrite.close();
    QCOMPARE(result(cancelled)["response"].toInt(), 1);
  }
  void saveSelectedExtension_data() {
    QTest::addColumn<QString>("typed");
    QTest::addColumn<QJsonArray>("patterns");
    QTest::addColumn<QString>("fallback");
    QTest::addColumn<QString>("expected");
    const QJsonArray png{QJsonArray{0, "*.png"}};
    QTest::newRow("no extension") << "drawing" << png << "" << "drawing.png";
    QTest::newRow("incomplete extension") << "drawing.pn" << png << "" << "drawing.pn.png";
    QTest::newRow("other extension") << "drawing.jpg" << png << "" << "drawing.jpg.png";
    QTest::newRow("already correct") << "drawing.png" << png << "" << "drawing.png";
    QTest::newRow("upper case") << "drawing.PNG" << png << "" << "drawing.PNG";
    const QJsonArray chromiumPng{QJsonArray{0, "*.[pP][nN][gG]"}};
    QTest::newRow("Chrome no extension") << "drawing" << chromiumPng << "" << "drawing.png";
    QTest::newRow("Chrome incomplete extension") << "drawing.pn" << chromiumPng << "" << "drawing.pn.png";
    QTest::newRow("Chrome already present") << "drawing.png" << chromiumPng << "" << "drawing.png";
    QTest::newRow("Chrome mixed case") << "drawing.PnG" << chromiumPng << "" << "drawing.PnG";
    QTest::newRow("Chrome compound") << "backup" << QJsonArray{QJsonArray{0,"*.[tT][aA][rR].[gG][zZ]"}} << "" << "backup.tar.gz";
    QTest::newRow("ambiguous class") << "drawing" << QJsonArray{QJsonArray{0,"*.jp[eg]"}} << "" << "drawing";
    QTest::newRow("range is not a suffix") << "drawing" << QJsonArray{QJsonArray{0,"*.[a-z]"}} << "" << "drawing";
    QTest::newRow("compound") << "backup.tar" << QJsonArray{QJsonArray{0,"*.tar.gz"}} << "" << "backup.tar.tar.gz";
    QTest::newRow("compound present") << "backup.tar.gz" << QJsonArray{QJsonArray{0,"*.tar.gz"}} << "" << "backup.tar.gz";
    QTest::newRow("alternate extension") << "drawing.jpeg" << QJsonArray{QJsonArray{0,"*.jpg"},QJsonArray{0,"*.jpeg"}} << "" << "drawing.jpeg";
    QTest::newRow("mime filter") << "drawing.pn" << QJsonArray{QJsonArray{1,"image/png"}} << "" << "drawing.pn.png";
    QTest::newRow("mime present") << "drawing.PNG" << QJsonArray{QJsonArray{1,"image/png"}} << "" << "drawing.PNG";
    QTest::newRow("all files") << "drawing.pn" << QJsonArray{QJsonArray{0,"*"}} << "" << "drawing.pn";
    QTest::newRow("no format") << "drawing.pn" << QJsonArray{} << "" << "drawing.pn";
    QTest::newRow("default suffix") << "drawing.pn" << QJsonArray{} << "png" << "drawing.pn.png";
    QTest::newRow("selected beats default") << "drawing" << png << "jpg" << "drawing.png";
  }
  void saveSelectedExtension() {
    QFETCH(QString, typed); QFETCH(QJsonArray, patterns); QFETCH(QString, fallback); QFETCH(QString, expected);
    auto input = request("SaveFile");
    const QJsonArray chosen{"Chosen type", patterns};
    input["filters"] = QJsonArray{QJsonArray{"Unselected type", QJsonArray{QJsonArray{0,"*.txt"}}}, chosen};
    input["current_filter"] = chosen; input["default_suffix"] = fallback;
    PickerWindow picker(input, settings(), false); prepare(picker);
    picker.findChild<QLineEdit *>("pickerName")->setText(typed);
    QSignalSpy spy(&picker, &PickerWindow::finished); picker.acceptSelection();
    QCOMPARE(result(spy)["uris"].toArray().first().toString(), QUrl::fromLocalFile(folder+'/'+expected).toString(QUrl::FullyEncoded));
    QCOMPARE(result(spy)["current_filter"].toArray(), chosen);
    QVERIFY(!QFileInfo::exists(folder+'/'+expected));
  }
  void saveMultipleAvoidsCollisions() {
    auto input = request("SaveFiles"); input["files"] = QJsonArray{"photo.png", "photo.png", "other.txt"};
    PickerWindow picker(input, settings(), false); prepare(picker);
    QSignalSpy spy(&picker, &PickerWindow::finished); picker.acceptSelection();
    auto uris = result(spy)["uris"].toArray(); QCOMPARE(uris.size(), 3);
    QVERIFY(uris[0].toString().endsWith("photo_copy1.png"));
    QVERIFY(uris[1].toString().endsWith("photo_copy2.png"));
  }
  void separateGeometryAndDesktop() {
    auto input = request("SaveFile");
    PickerWindow picker(input, settings(), false); prepare(picker);
    bool desktop = false;
    for (auto *tree : picker.findChildren<QTreeWidget *>())
      for (QTreeWidgetItemIterator it(tree); *it; ++it) desktop |= (*it)->text(0) == "Desktop";
    QVERIFY(desktop);
    picker.resize(780, 550); picker.close();
    PickerWindow again(input, settings(), false); again.setAttribute(Qt::WA_DeleteOnClose, false);
    QCOMPARE(again.size(), QSize(780, 550));
    Fusion::Preferences preferences(settings()); QVERIFY(!preferences.settings.contains("geometry"));
    again.close();
  }
  void compactActionsWhenResized_data() {
    QTest::addColumn<QString>("method"); QTest::addColumn<bool>("extraChoices");
    for (const auto &method : {"OpenFile", "SaveFile", "SaveFiles"})
      for (const bool choices : {false, true})
        QTest::newRow(qPrintable(QString(method)+(choices ? " with choices" : ""))) << QString(method) << choices;
  }
  void compactActionsWhenResized() {
    QFETCH(QString, method); QFETCH(bool, extraChoices);
    auto input = request(method);
    if (extraChoices) input["choices"] = QJsonArray{
      QJsonArray{"metadata", "Keep metadata", QJsonArray{}, "true"},
      QJsonArray{"quality", "Quality", QJsonArray{QJsonArray{"high", "High"}, QJsonArray{"low", "Low"}}, "high"}};
    PickerWindow picker(input, settings(), false); prepare(picker);
    auto *actions = picker.findChild<QFrame *>("pickerActions"); QVERIFY(actions);
    picker.resize(1100, 650); QTest::qWait(100);
    const int compact = actions->height(), browserHeight = picker.browser()->height();
    picker.resize(1100, 1000);
    QTRY_COMPARE(actions->height(), compact);
    QVERIFY(picker.browser()->height() >= browserHeight+340);
    QVERIFY(actions->height() <= actions->sizeHint().height()+2);
    for (const auto *control : {static_cast<QWidget *>(picker.findChild<QLineEdit *>("pickerName")),
                               static_cast<QWidget *>(picker.findChild<QPushButton *>("pickerAccept"))}) {
      QVERIFY(control && control->isVisible());
      QVERIFY(actions->rect().contains(QRect(control->mapTo(actions, QPoint()), control->size())));
    }
    const auto artifacts = qEnvironmentVariable("FUSION_PICKER_ARTIFACTS");
    if (!artifacts.isEmpty()) {
      QDir().mkpath(artifacts);
      QVERIFY(picker.grab().save(artifacts+'/'+method+(extraChoices ? "-choices" : "")+".png"));
    }
    picker.close();
  }
};
QTEST_MAIN(PickerTests)
#include "picker_tests.moc"
