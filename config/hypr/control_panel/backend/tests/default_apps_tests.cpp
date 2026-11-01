#include "default_apps.h"
#include <QJsonDocument>
#include <QtTest>
#include <QtWidgets>

class DefaultAppsTests final : public QObject {
  Q_OBJECT
  QTemporaryDir fixture;
  QString helper;
  static void write(const QString &path, const QByteArray &data) {
    QFile file(path);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(data);
  }
  QByteArray calls() {
    QFile file(fixture.filePath("calls"));
    return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray();
  }
  void selectApp(const QString &id, bool showAll = false) {
    QTimer::singleShot(30, qApp, [id, showAll] {
      auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      QVERIFY(dialog);
      auto *list = dialog->findChild<QListWidget *>("defaultsAppList");
      QVERIFY(list);
      if (showAll)
        dialog->findChild<QCheckBox *>("defaultsAllApps")->setChecked(true);
      for (int i = 0; i < list->count(); ++i)
        if (list->item(i)->data(Qt::UserRole).toString() == id) {
          QVERIFY(!list->item(i)->isHidden());
          list->setCurrentRow(i);
          auto *use = dialog->findChild<QPushButton *>("defaultsUseApp");
          QVERIFY(use->isEnabled());
          use->click();
          return;
        }
      QFAIL("Missing fixture application");
    });
  }
private slots:
  void initTestCase() {
    QVERIFY(fixture.isValid());
    qApp->setQuitOnLastWindowClosed(false);
    qApp->setStyle("Fusion");
    QIcon::setThemeSearchPaths({QDir::homePath() + "/.local/share/icons",
                                "/usr/local/share/icons", "/usr/share/icons"});
    QIcon::setFallbackThemeName("Papirus-Dark");
    const auto themePath = qEnvironmentVariable("FUSION_DEFAULT_APPS_THEME");
    if (!themePath.isEmpty()) {
      QFile file(themePath);
      QVERIFY(file.open(QIODevice::ReadOnly));
      const auto theme = QJsonDocument::fromJson(file.readAll()).object();
      QPalette palette;
      const auto roles = QMetaEnum::fromType<QPalette::ColorRole>();
      const auto colors = theme["colors"].toObject();
      for (auto it = colors.begin(); it != colors.end(); ++it) {
        const auto role = roles.keyToValue(it.key().toUtf8());
        if (role >= 0)
          palette.setColor(QPalette::All, QPalette::ColorRole(role),
                           QColor(it.value().toString()));
      }
      qApp->setPalette(palette);
      qApp->setFont(QFont(theme["font"].toString(), 10));
      qApp->setProperty("xetalPanelCardRadius", theme["cardRadius"].toInt());
      QIcon::setThemeName(theme["iconTheme"].toString());
      qApp->setStyleSheet(theme["stylesheet"].toString());
    }
    helper = fixture.filePath("helper.py");
    write(helper, R"PY(import json,sys
from pathlib import Path
root=Path(__file__).parent
roles=[('browser','Web browser','x-scheme-handler/https','internet-web-browser'),('email','Email','x-scheme-handler/mailto','internet-mail'),('files','File manager','inode/directory','system-file-manager'),('music','Music','audio/mpeg','audio-x-generic'),('video','Video','video/mp4','video-x-generic'),('images','Images','image/png','image-x-generic'),('pdf','PDF reader','application/pdf','application-pdf'),('text','Text editor','text/plain','text-x-generic'),('archives','Archives','application/zip','package-x-generic'),('documents','Documents','application/vnd.oasis.opendocument.text','x-office-document'),('spreadsheets','Spreadsheets','text/csv','x-office-spreadsheet'),('presentations','Presentations','application/vnd.ms-powerpoint','x-office-presentation')]
state=root/'state.json'
values=json.loads(state.read_text()) if state.exists() else {}
action=sys.argv[1]
if action=='snapshot':
    apps=[dict(id='fixture-old.desktop',name='Fixture Old',description='The previous application',icon='internet-web-browser',types=[r[2] for r in roles]),dict(id='fixture-new.desktop',name='Fixture New',description='A new application',icon='applications-internet',types=['application/pdf','x-scheme-handler/https']),dict(id='fixture-other.desktop',name='Fixture Other',description='Another installed app',icon='applications-other',types=[])]
    print(json.dumps(dict(revision='fixture-revision',apps=apps,roles=[dict(id=r[0],title=r[1],description='Choose your preferred application',icon=r[3],types=[r[2]],default=values.get(r[2],'fixture-old.desktop'),mixed=False) for r in roles],filetypes=[dict(id=r[2],name=r[1],extensions='*.pdf' if r[0]=='pdf' else '',default=values.get(r[2],'fixture-old.desktop')) for r in roles])))
else:
    data=json.load(sys.stdin)
    with (root/'calls').open('a') as f:f.write(json.dumps(dict(action=action,**data))+'\n')
    if (root/'fail').exists():
        print(json.dumps(dict(error='Fixture cannot save defaults.')));sys.exit(1)
    if action=='apply':
        mime=next(r[2] for r in roles if r[0]==data['role']) if 'role' in data else data['type']
        values[mime]=data['app'];state.write_text(json.dumps(values))
        print(json.dumps(dict(ok=True,undo='fixture-undo',message='The new default was saved.')))
    else:
        state.unlink(missing_ok=True)
        print(json.dumps(dict(ok=True,message='Your previous defaults were restored.')))
)PY");
  }
  void init() {
    for (const auto &name : {"calls", "state.json", "fail"})
      QFile::remove(fixture.filePath(name));
  }
  void inventoryAndSearchAreReadOnly() {
    DefaultApps page(helper);
    page.resize(1100, 900);
    page.show();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_browser"));
    QVERIFY(calls().isEmpty());
    page.focusSearch();
    auto *search = page.findChild<QLineEdit *>("defaultsTypeSearch");
    search->setText(".pdf");
    auto *tree = page.findChild<QTreeWidget *>("defaultsTypes");
    int visible = 0;
    for (int i = 0; i < tree->topLevelItemCount(); ++i)
      if (!tree->topLevelItem(i)->isHidden()) {
        ++visible;
        QCOMPARE(tree->topLevelItem(i)->data(0, Qt::UserRole).toString(),
                 QString("application/pdf"));
      }
    QCOMPARE(visible, 1);
    page.findChild<QPushButton *>("defaultsRefresh")->click();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultsRefresh")->isEnabled());
    QVERIFY(calls().isEmpty());
  }
  void cancelledPickerDoesNotSave() {
    DefaultApps page(helper);
    page.resize(1100, 900);
    page.show();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_browser"));
    QTimer::singleShot(30, qApp, [] {
      auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
      QVERIFY(dialog);
      dialog->reject();
    });
    page.findChild<QPushButton *>("defaultRole_browser")->click();
    QVERIFY(calls().isEmpty());
  }
  void choosingAndUndoingUpdateTheCards() {
    DefaultApps page(helper);
    page.resize(1100, 900);
    page.show();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_browser"));
    selectApp("fixture-new.desktop");
    page.findChild<QPushButton *>("defaultRole_browser")->click();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_browser")
                    ->accessibleName()
                    .contains("Fixture New"));
    QVERIFY(calls().contains("fixture-revision"));
    QVERIFY(calls().contains("\"role\": \"browser\""));
    auto *undo = page.findChild<QPushButton *>("defaultsUndo");
    QVERIFY(undo->isVisible());
    undo->click();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_browser")
                    ->accessibleName()
                    .contains("Fixture Old"));
    QVERIFY(calls().contains("fixture-undo"));
    QVERIFY(!undo->isVisible());
  }
  void individualTypeCanUseAnyInstalledApp() {
    DefaultApps page(helper);
    page.resize(1100, 900);
    page.show();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_pdf"));
    page.focusSearch();
    page.findChild<QLineEdit *>("defaultsTypeSearch")->setText(".pdf");
    auto *tree = page.findChild<QTreeWidget *>("defaultsTypes");
    for (int i = 0; i < tree->topLevelItemCount(); ++i)
      if (!tree->topLevelItem(i)->isHidden())
        tree->setCurrentItem(tree->topLevelItem(i));
    selectApp("fixture-other.desktop", true);
    page.findChild<QPushButton *>("defaultsChangeType")->click();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_pdf")
                    ->accessibleName()
                    .contains("Fixture Other"));
    QVERIFY(calls().contains("\"type\": \"application/pdf\""));
    QVERIFY(!calls().contains("\"role\""));
  }
  void saveErrorsRemainVisibleWithoutChangingCards() {
    write(fixture.filePath("fail"), "yes");
    DefaultApps page(helper);
    page.resize(1100, 900);
    page.show();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_browser"));
    selectApp("fixture-new.desktop");
    page.findChild<QPushButton *>("defaultRole_browser")->click();
    QTRY_VERIFY(page.findChild<QLabel *>("defaultsStatus")
                    ->text()
                    .contains("Fixture cannot save"));
    QVERIFY(page.findChild<QPushButton *>("defaultRole_browser")
                ->accessibleName()
                .contains("Fixture Old"));
    QVERIFY(page.findChild<QPushButton *>("defaultsRefresh")->isEnabled());
  }
  void responsiveLayoutAndPreview() {
    const auto realHelper =
        qEnvironmentVariable("FUSION_DEFAULT_APPS_PREVIEW_HELPER");
    DefaultApps page(realHelper.isEmpty() ? helper : realHelper);
    page.resize(1260, 870);
    page.show();
    QTRY_VERIFY(page.findChild<QPushButton *>("defaultRole_browser"));
    auto position = [&page](const QString &id) {
      return page.findChild<QPushButton *>("defaultRole_" + id)->geometry();
    };
    QTRY_COMPARE(position("browser").y(), position("files").y());
    page.resize(700, 1100);
    QTRY_VERIFY(position("files").y() > position("browser").y());
    const auto capture = qEnvironmentVariable("FUSION_DEFAULT_APPS_CAPTURE");
    if (!capture.isEmpty()) {
      page.resize(1260, 870);
      QTest::qWait(150);
      page.resize(1260, 870);
      QTest::qWait(30);
      QVERIFY(page.grab().save(capture + "-cards.png"));
      page.focusSearch();
      page.findChild<QLineEdit *>("defaultsTypeSearch")->setText("pdf");
      QVERIFY(page.grab().save(capture + "-types.png"));
      QTimer::singleShot(100, qApp, [capture] {
        auto *dialog =
            qobject_cast<QDialog *>(QApplication::activeModalWidget());
        QVERIFY(dialog);
        QVERIFY(dialog->grab().save(capture + "-picker.png"));
        dialog->reject();
      });
      page.findChild<QPushButton *>("defaultRole_browser")->click();
    }
    QVERIFY(calls().isEmpty());
  }
};
QTEST_MAIN(DefaultAppsTests)
#include "default_apps_tests.moc"
