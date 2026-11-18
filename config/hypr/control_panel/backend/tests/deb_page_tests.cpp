#include "deb_page.h"
#include "deb_prerequisites.h"
#include <QtTest>
#include <QtWidgets>

class DebPageTests final : public QObject {
  Q_OBJECT
  QList<QUrl> opened;
  QString root = QStringLiteral(DEB_PROFILE_ROOT);

  static QPushButton *button(QWidget &page, const char *name) {
    return page.findChild<QPushButton *>(name);
  }
  static QDialog *report(DebInstallerPage &page) {
    button(page, "debFeedbackButton")->click();
    return page.findChild<QDialog *>("debFeedbackDialog");
  }
  static void fillReport(QDialog &dialog) {
    dialog.findChild<QLineEdit *>("debFeedbackApp")->setText("Example app");
    dialog.findChild<QLineEdit *>("debFeedbackVersion")->setText("1.2.3");
    dialog.findChild<QLineEdit *>("debFeedbackUrl")->setText("https://example.org/download?format=deb");
    dialog.findChild<QPlainTextEdit *>("debFeedbackDetails")->setPlainText("Missing library: libexample.so\nNo window opened.");
  }

private slots:
  void captureUrl(const QUrl &url) { opened.append(url); }
  void initTestCase() {
    qApp->setQuitOnLastWindowClosed(false);
    qApp->setStyle("Fusion");
    QDesktopServices::setUrlHandler("https", this, "captureUrl");
    const auto themePath = qEnvironmentVariable("DEB_PAGE_THEME");
    if (!themePath.isEmpty()) {
      QFile file(themePath);
      QVERIFY(file.open(QIODevice::ReadOnly));
      const auto theme = QJsonDocument::fromJson(file.readAll()).object();
      QPalette palette;
      const auto roles = QMetaEnum::fromType<QPalette::ColorRole>();
      const auto colors = theme["colors"].toObject();
      for (auto it = colors.begin(); it != colors.end(); ++it) {
        const auto role = roles.keyToValue(it.key().toUtf8());
        if (role >= 0) palette.setColor(QPalette::All, QPalette::ColorRole(role), QColor(it.value().toString()));
      }
      qApp->setPalette(palette);
      qApp->setFont(QFont(theme["font"].toString(), 10));
      qApp->setProperty("xetalPanelCardRadius", theme["cardRadius"].toInt());
      QIcon::setThemeName(theme["iconTheme"].toString());
      qApp->setStyleSheet(theme["stylesheet"].toString());
    }
  }
  void init() { opened.clear(); }
  void cleanupTestCase() { QDesktopServices::unsetUrlHandler("https"); }

  void installAndCheckKeepOriginalActions() {
    auto *install = new QPushButton;
    DebInstallerPage page(root, install);
    QList<bool> calls;
    connect(install, &QPushButton::clicked, this, [&] { calls.append(install->property("debCheckOnly").toBool()); });
    install->click();
    button(page, "checkDebButton")->click();
    install->click();
    QCOMPARE(calls, QList<bool>({false, true, false}));
    QVERIFY(opened.isEmpty());
  }

  void prerequisitesAreRequestedOnlyForInstallation() {
    struct RestorePath { QByteArray value = qgetenv("PATH"); ~RestorePath() { qputenv("PATH",value); } } restore;
    QTemporaryDir directory; QVERIFY(directory.isValid());
    qputenv("PATH",directory.path().toUtf8());
    DebInstallerPage page(root, new QPushButton);
    page.show(); QTest::qWait(40);
    QVERIFY(page.findChildren<QMessageBox *>().isEmpty());
    QCOMPARE(HyperPanel::confirmDebHelpers(&page, true), HyperPanel::DebHelpers::Ready);
    for (bool accept : {false, true}) {
      QTimer::singleShot(0, &page, [&page, accept] {
        auto *prompt = page.findChild<QMessageBox *>("debHelperPrompt"); QVERIFY(prompt);
        QVERIFY(prompt->informativeText().contains("both Yay and Paru"));
        prompt->button(accept ? QMessageBox::Yes : QMessageBox::No)->click();
      });
      QCOMPARE(HyperPanel::confirmDebHelpers(&page, false), accept ? HyperPanel::DebHelpers::InstallBoth : HyperPanel::DebHelpers::Cancel);
    }
    for (const auto &name : {QString("yay"), QString("paru")}) {
      QFile executable(directory.filePath(name)); QVERIFY(executable.open(QIODevice::WriteOnly));
      executable.write("#!/bin/sh\nexit 0\n"); executable.close();
      QVERIFY(executable.setPermissions(QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner));
      QCOMPARE(HyperPanel::confirmDebHelpers(&page, false), HyperPanel::DebHelpers::Ready);
      QVERIFY(executable.remove());
    }
    const QString file = "/tmp/app's $(literal).deb";
    auto args = HyperPanel::debTerminalArguments(root, file, false, HyperPanel::DebHelpers::InstallBoth);
    QCOMPARE(args, QStringList({"-e", "python3", root + "/control_panel/aur_helper_install.py", "--wait", "--deb", file, "both"}));
    args = HyperPanel::debTerminalArguments(root, file, true, HyperPanel::DebHelpers::Ready);
    QVERIFY(args.contains("--check")); QVERIFY(!args.contains("--deb")); QCOMPARE(args.last(), file);
    QVERIFY(HyperPanel::debTerminalArguments(root, file, false, HyperPanel::DebHelpers::Cancel).isEmpty());
  }

  void fileSelectionIsVisibleAndWaitsForInstall() {
    QTemporaryDir temp;
    const auto path = temp.path()+"/package's $(literal) <b>.deb";
    QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); file.write("fixture"); file.close();
    auto *install = new QPushButton;
    DebInstallerPage page(root, install);
    QSignalSpy clicks(install, &QPushButton::clicked);
    page.selectPackage(path);
    QCOMPARE(clicks.count(), 0);
    QCOMPARE(install->property("debSelectedFile").toString(), path);
    auto *label = page.findChild<QLabel *>("selectedDebPackage");
    QVERIFY(label);
    QCOMPARE(label->textFormat(), Qt::PlainText);
    QVERIFY(label->text().contains(path));
    QVERIFY(!page.findChild<QWidget *>("selectedDebPackageRow")->isHidden());
    button(page, "checkDebButton")->click();
    QCOMPARE(clicks.count(), 1);
    QCOMPARE(install->property("debSelectedFile").toString(), path);
    button(page, "chooseAnotherDebPackage")->click();
    QCOMPARE(clicks.count(), 2);
    QVERIFY(install->property("debSelectedFile").toString().isEmpty());
    QVERIFY(page.findChild<QWidget *>("selectedDebPackageRow")->isHidden());
    QVERIFY(opened.isEmpty());
  }

  void reportedResultsAndOfficialDownloads() {
    DebInstallerPage page(root, new QPushButton);
    auto *chrome = button(page, "debApp_chrome");
    QVERIFY(chrome);
    QVERIFY(chrome->property("tested").toBool());
    QCOMPARE(chrome->property("testedOn").toString(), QString("2026-11-07"));
    chrome->click();
    QCOMPARE(opened, QList<QUrl>({QUrl("https://www.google.com/chrome/?platform=linux")}));
    auto *discord = button(page, "debApp_discord");
    QVERIFY(discord);
    QVERIFY(discord->property("tested").toBool());
    QCOMPARE(discord->property("testedOn").toString(), QString("2026-11-08"));
    QVERIFY(discord->accessibleName().contains("tested working"));
    discord->click();
    QCOMPARE(opened.last(), QUrl("https://discord.com/download"));
    auto *vscode = button(page, "debApp_vscode");
    QVERIFY(vscode);
    QVERIFY(vscode->property("tested").toBool());
    QVERIFY(vscode->accessibleName().contains("tested working"));
    QCOMPARE(vscode->property("testedOn").toString(), QString("2026-11-08"));
    vscode->click();
    QCOMPARE(opened.last(), QUrl("https://code.visualstudio.com/download"));
  }

  void feedbackRequiresReproducibleDetailsAndOpensOnlyOnRequest() {
    DebInstallerPage page(root, new QPushButton);
    auto *dialog = report(page);
    QVERIFY(dialog);
    QVERIFY(opened.isEmpty());
    QApplication::clipboard()->setText("untouched");
    button(*dialog, "debOpenEcho")->click();
    QVERIFY(opened.isEmpty());
    QCOMPARE(QApplication::clipboard()->text(), QString("untouched"));
    fillReport(*dialog);
    auto *url = dialog->findChild<QLineEdit *>("debFeedbackUrl");
    for (const auto &invalid : {"file:///tmp/private.deb", "javascript:alert(1)", "https://user:secret@example.org/a.deb"}) {
      url->setText(invalid);
      button(*dialog, "debCopyReport")->click();
      QCOMPARE(QApplication::clipboard()->text(), QString("untouched"));
    }
    fillReport(*dialog);
    button(*dialog, "debCopyReport")->click();
    const auto message = QApplication::clipboard()->text();
    QVERIFY(message.contains("Application: Example app\nVersion: 1.2.3"));
    QVERIFY(message.contains(".deb download: https://example.org/download?format=deb"));
    QVERIFY(message.contains("Result: Installation failed"));
    QVERIFY(message.contains("Missing library: libexample.so\nNo window opened."));
    QVERIFY(opened.isEmpty());
    button(*dialog, "debOpenEcho")->click();
    QCOMPARE(opened.size(), 1);
    QCOMPARE(opened.last(), QUrl("https://www.xetal.net/community/site/echo-web/"));
    button(*dialog, "debOpenDiscord")->click();
    QCOMPARE(opened.size(), 2);
    QFile source(root + "/control_panel/deb_apps.json");
    QVERIFY(source.open(QIODevice::ReadOnly));
    const auto contacts = QJsonDocument::fromJson(source.readAll()).object()["feedback"].toObject();
    QCOMPARE(opened.last(), QUrl(contacts["discord_url"].toString()));
    dialog->reject();
  }

  void automatedLaunchResultDoesNotClaimReportedWorking() {
    QTemporaryDir directory;
    QVERIFY(directory.isValid());
    QVERIFY(QDir(directory.path()).mkpath("control_panel"));
    QFile catalog(directory.path() + "/control_panel/deb_apps.json");
    QVERIFY(catalog.open(QIODevice::WriteOnly));
    const QJsonObject app{{"id", "example"}, {"name", "Example app"},
                          {"url", "https://example.org/download"}, {"status", "launch_tested"},
                          {"tested_on", "2026-11-08"},
                          {"note", "Automated install, launch and removal; features not tested."}};
    catalog.write(QJsonDocument(QJsonObject{{"apps", QJsonArray{app}}}).toJson());
    catalog.close();
    DebInstallerPage page(directory.path(), new QPushButton);
    auto *card = button(page, "debApp_example");
    QVERIFY(card);
    QVERIFY(card->property("launchTested").toBool());
    QVERIFY(!card->property("tested").toBool());
    QVERIFY(card->accessibleName().contains("launch tested, Nov 8, 2026"));
    QVERIFY(card->toolTip().contains("features not tested"));
    card->click();
    QCOMPARE(opened.last(), QUrl("https://example.org/download"));
  }

  void cardsReflowWithoutHorizontalScrolling() {
    DebInstallerPage page(root, new QPushButton);
    page.resize(1240, 850);
    page.show();
    auto *chrome = button(page, "debApp_chrome");
    auto *suggest = button(page, "debApp_suggest");
    auto *scroll = page.findChild<QScrollArea *>("debScroll");
    QTRY_COMPARE(chrome->y(), button(page, "debApp_vscode")->y());
    QTRY_COMPARE(chrome->y(), 0);
    QCOMPARE(scroll->horizontalScrollBar()->maximum(), 0);
    // Styled buttons may carry gradient brushes; custom cards must still use
    // the selected light/dark palette rather than painting a black surface.
    const auto surface = chrome->grab().toImage().pixelColor(12, 100);
    QVERIFY(surface == qApp->palette().color(QPalette::Base) ||
            surface == qApp->palette().color(QPalette::AlternateBase));
    const auto capture = qEnvironmentVariable("DEB_PAGE_CAPTURE");
    if (!capture.isEmpty()) { QDir().mkpath(capture); page.grab().save(capture + "/wide.png"); }
    page.resize(700, 520);
    QTRY_VERIFY(suggest->y() > chrome->y());
    QCOMPARE(scroll->horizontalScrollBar()->maximum(), 0);
    QVERIFY(scroll->verticalScrollBar()->maximum() > 0);
    auto *feedback = button(page, "debFeedbackButton");
    scroll->ensureWidgetVisible(feedback);
    QTRY_VERIFY(scroll->viewport()->rect().contains(feedback->mapTo(scroll->viewport(), feedback->rect().center())));
    if (!capture.isEmpty()) {
      page.grab().save(capture + "/compact.png");
      auto *dialog = report(page);
      fillReport(*dialog);
      QTest::qWait(30);
      dialog->grab().save(capture + "/feedback.png");
      dialog->reject();
    }
  }
};

QTEST_MAIN(DebPageTests)
#include "deb_page_tests.moc"
