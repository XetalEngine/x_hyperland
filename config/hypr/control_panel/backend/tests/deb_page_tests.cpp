#include "deb_page.h"
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
    QPushButton yay, paru;
    auto *install = new QPushButton;
    DebInstallerPage page(root, install, &yay, &paru);
    QList<bool> calls;
    connect(install, &QPushButton::clicked, this, [&] { calls.append(install->property("debCheckOnly").toBool()); });
    install->click();
    button(page, "checkDebButton")->click();
    install->click();
    QCOMPARE(calls, QList<bool>({false, true, false}));
    QSignalSpy yayClicks(&yay, &QPushButton::clicked), paruClicks(&paru, &QPushButton::clicked);
    button(page, "debYayInstall")->click();
    button(page, "debParuInstall")->click();
    QCOMPARE(yayClicks.count(), 1);
    QCOMPARE(paruClicks.count(), 1);
    QVERIFY(opened.isEmpty());
  }

  void chromeResultAndOfficialDownload() {
    QPushButton yay, paru;
    DebInstallerPage page(root, new QPushButton, &yay, &paru);
    auto *chrome = button(page, "debApp_chrome");
    QVERIFY(chrome);
    QVERIFY(chrome->property("tested").toBool());
    QCOMPARE(chrome->property("testedOn").toString(), QString("2026-11-07"));
    chrome->click();
    QCOMPARE(opened, QList<QUrl>({QUrl("https://www.google.com/chrome/?platform=linux")}));
    for (const auto *name : {"debApp_discord", "debApp_vscode"}) {
      auto *card = button(page, name);
      QVERIFY(card);
      QVERIFY(!card->property("tested").toBool());
      QVERIFY(card->accessibleName().contains("untested"));
      QVERIFY(card->property("testedOn").toString().isEmpty());
    }
  }

  void feedbackRequiresReproducibleDetailsAndOpensOnlyOnRequest() {
    QPushButton yay, paru;
    DebInstallerPage page(root, new QPushButton, &yay, &paru);
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

  void cardsReflowWithoutHorizontalScrolling() {
    QPushButton yay, paru;
    DebInstallerPage page(root, new QPushButton, &yay, &paru);
    page.resize(1240, 850);
    page.show();
    auto *chrome = button(page, "debApp_chrome");
    auto *suggest = button(page, "debApp_suggest");
    auto *scroll = page.findChild<QScrollArea *>("debScroll");
    QTRY_COMPARE(chrome->y(), suggest->y());
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
