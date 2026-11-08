#include "deb_page.h"
#include "aur_helpers.h"
#include <QtWidgets>

namespace {
bool webUrl(const QUrl &url) {
  return url.isValid() && (url.scheme() == "https" || url.scheme() == "http") &&
         !url.host().isEmpty() && url.userInfo().isEmpty();
}

QLabel *label(const QString &text, const char *name, QWidget *parent) {
  auto *result = new QLabel(text, parent);
  result->setObjectName(name);
  result->setTextFormat(Qt::PlainText);
  result->setWordWrap(true);
  return result;
}

class AppCard final : public QPushButton {
  QJsonObject app;
  QString fallback;
  bool tested;
  bool suggestion;

public:
  AppCard(const QJsonObject &data, const QString &root, QWidget *parent)
      : QPushButton(parent), app(data),
        fallback(root + "/control_panel/assets/deb/" + data["icon"].toString() + ".svg"),
        tested(data["status"] == "tested" &&
               QDate::fromString(data["tested_on"].toString(), Qt::ISODate).isValid()),
        suggestion(data["id"] == "suggest") {
    setObjectName("debApp_" + data["id"].toString());
    setText(data["name"].toString());
    setProperty("tested", tested);
    setProperty("downloadUrl", data["url"].toString());
    setProperty("testedOn", data["tested_on"].toString());
    setAccessibleName(text() + (tested ? ": tested working, " + testDate()
                                      : suggestion ? ": share a test result" : ": untested"));
    setAccessibleDescription(data["note"].toString() + ". " + data["url"].toString());
    setToolTip(suggestion ? "Tell Xetal about an application you tried."
                         : accessibleName() + "\n" + data["note"].toString() +
                               "\nOpen the official download page: " + data["url"].toString());
    setCursor(Qt::PointingHandCursor);
    setMinimumWidth(220);
    setMinimumHeight(222);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  }
  QString testDate() const {
    return QLocale(QLocale::English).toString(
        QDate::fromString(app["tested_on"].toString(), Qt::ISODate), "MMM d, yyyy");
  }
  void paintEvent(QPaintEvent *) override {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    // Button styles can replace Base with a gradient brush whose color() is
    // black. Cards paint their own surface, so use the desktop's solid palette.
    const auto pal = qApp->palette();
    const bool active = underMouse() || hasFocus() || isDown();
    const auto corner = qApp->property("xetalPanelCardRadius");
    const int radius = corner.isValid() ? corner.toInt() : 12;
    p.setBrush(pal.color(active ? QPalette::AlternateBase : QPalette::Base));
    p.setPen(QPen(pal.color(active ? QPalette::Link : QPalette::Midlight), hasFocus() ? 2 : 1));
    p.drawRoundedRect(QRectF(rect()).adjusted(1, 1, -1, -1), radius, radius);
    auto f = font();
    f.setPointSizeF(qMax(8., font().pointSizeF() - 1));
    f.setBold(true);
    p.setFont(f);
    const QString status = tested ? "Tested working" : suggestion ? "Not listed?" : "Untested";
    const int pillWidth = p.fontMetrics().horizontalAdvance(status) + 20;
    p.setPen(Qt::NoPen);
    p.setBrush(pal.color(tested ? QPalette::Highlight : QPalette::AlternateBase));
    p.drawRoundedRect(QRectF(16, 14, pillWidth, 25), 6, 6);
    p.setPen(pal.color(tested ? QPalette::HighlightedText : QPalette::Text));
    p.drawText(QRect(16, 14, pillWidth, 25), Qt::AlignCenter, status);
    const auto icon = QIcon::fromTheme(app["icon"].toString(),
        QFile::exists(fallback) ? QIcon(fallback) : style()->standardIcon(QStyle::SP_FileIcon));
    icon.paint(&p, QRect(18, 53, 54, 54));
    f = font(); f.setBold(true); f.setPointSizeF(font().pointSizeF() + 1);
    p.setFont(f); p.setPen(pal.color(QPalette::Text));
    p.drawText(QRect(18, 117, width() - 36, 25), Qt::AlignVCenter,
               p.fontMetrics().elidedText(text(), Qt::ElideRight, width() - 36));
    f = font(); p.setFont(f); p.setPen(pal.color(QPalette::PlaceholderText));
    p.drawText(QRect(18, 148, width() - 36, 22), Qt::AlignVCenter,
               tested ? testDate() : suggestion ? "Help grow this list" : "No report yet");
    p.setPen(pal.color(QPalette::Link));
    p.drawText(QRect(18, height() - 37, width() - 36, 22), Qt::AlignVCenter,
               suggestion ? "Share a test result  →" : "Official download  ↗");
  }
};
} // namespace

DebInstallerPage::DebInstallerPage(const QString &profileRoot, QPushButton *install,
                                 QPushButton *installYay, QPushButton *installParu,
                                 QWidget *parent)
    : QWidget(parent), root(profileRoot) {
  setObjectName("debInstallTab");
  auto *outer = new QVBoxLayout(this);
  outer->setContentsMargins(0, 0, 0, 0);
  auto *scroll = new QScrollArea(this);
  scroll->setObjectName("debScroll");
  scroll->setFrameShape(QFrame::NoFrame);
  scroll->setWidgetResizable(true);
  auto *body = new QWidget(scroll);
  auto *layout = new QVBoxLayout(body);
  layout->setContentsMargins(4, 4, 12, 12);
  layout->setSpacing(16);
  scroll->setWidget(body);
  outer->addWidget(scroll);

  auto *hero = new QFrame(body);
  hero->setObjectName("debHero");
  auto *intro = new QVBoxLayout(hero);
  intro->setContentsMargins(22, 18, 22, 18);
  intro->setSpacing(8);
  auto *heading = new QHBoxLayout;
  heading->addWidget(label("DEBIAN PACKAGES  /  ARCH LINUX", "debEyebrow", hero), 1);
  auto *badge = label("Experimental", "debExperimental", hero);
  badge->setWordWrap(false);
  heading->addWidget(badge);
  intro->addLayout(heading);
  intro->addWidget(label("Bring your .deb apps to Arch", "debTitle", hero));
  intro->addWidget(label("Choose a trusted .deb file. Hyper Fusion checks its dependencies, converts it, "
                        "and installs it with pacman. Some apps need extra compatibility work.", "debDescription", hero));
  layout->addWidget(hero);

  auto *helpers = new QFrame(body);
  helpers->setObjectName("debHelpers");
  auto *helpersLayout = new QVBoxLayout(helpers);
  helpersLayout->setContentsMargins(16, 12, 16, 12);
  helpersLayout->setSpacing(8);
  helpersLayout->addWidget(label("AUR helpers · one is enough", "debSectionTitle", helpers));
  auto *helperRow = new QHBoxLayout;
  for (const auto &name : {QString("yay"), QString("paru")}) {
    const QString title = name == "yay" ? "Yay" : "Paru";
    auto *status = new QLabel(helpers);
    status->setObjectName("deb" + title + "Status");
    auto *button = new QPushButton("Install " + title, helpers);
    button->setObjectName("deb" + title + "Install");
    auto *existing = name == "yay" ? installYay : installParu;
    connect(button, &QPushButton::clicked, existing, &QPushButton::click);
    const auto refresh = [status, button, name, title] {
      const bool installed = HyperPanel::aurHelperInstalled(name);
      status->setText(title + (installed ? ": ✓ Installed" : ": Not installed"));
      button->setVisible(!installed);
    };
    refresh();
    auto *timer = new QTimer(helpers);
    connect(timer, &QTimer::timeout, this, [this, refresh] { if (isVisible()) refresh(); });
    timer->start(2000);
    helperRow->addWidget(status);
    helperRow->addWidget(button);
    helperRow->addStretch();
  }
  helpersLayout->addLayout(helperRow);
  helpersLayout->addWidget(label("Arch repositories are checked first. Yay or Paru handles supported AUR dependencies and Debtap. "
                                "Review package changes in the terminal.", "debMuted", helpers));
  layout->addWidget(helpers);

  auto *actions = new QHBoxLayout;
  install->setText("Choose .deb and install…");
  install->setProperty("debPrimary", true);
  install->setEnabled(true);
  install->setToolTip("Check dependencies, convert, and review the pacman installation in a terminal.");
  install->setIcon(QIcon::fromTheme("application-x-deb"));
  actions->addWidget(install);
  install->show();
  auto *check = new QPushButton("Check dependencies only…", body);
  check->setObjectName("checkDebButton");
  check->setToolTip("Inspect the .deb and existing package databases without installing anything.");
  actions->addWidget(check);
  actions->addStretch();
  connect(check, &QPushButton::clicked, this, [install] {
    install->setProperty("debCheckOnly", true);
    install->click();
    install->setProperty("debCheckOnly", false);
  });
  layout->addLayout(actions);
  layout->addWidget(label("Unresolved dependencies stop installation and are explained in the terminal.", "debMuted", body));

  QFile source(root + "/control_panel/deb_apps.json");
  const bool loaded = source.open(QIODevice::ReadOnly);
  const auto catalog = loaded ? QJsonDocument::fromJson(source.readAll()).object() : QJsonObject();
  contacts = catalog["feedback"].toObject();
  auto *catalogTitle = new QHBoxLayout;
  catalogTitle->addWidget(label("App compatibility", "debCatalogTitle", body), 1);
  auto *count = label("", "debMuted", body);
  catalogTitle->addWidget(count);
  layout->addLayout(catalogTitle);
  layout->addWidget(label("Test results are snapshots, not a promise for every version. Untested means we have no result yet. "
                          "Select an icon to visit the app’s official download page.", "debMuted", body));
  appGrid = new QWidget(body);
  appGrid->setObjectName("debAppGrid");
  grid = new QGridLayout(appGrid);
  grid->setContentsMargins(0, 0, 0, 0);
  grid->setSpacing(12);
  int tested = 0;
  for (const auto &value : catalog["apps"].toArray()) {
    const auto data = value.toObject();
    const QUrl url(data["url"].toString(), QUrl::StrictMode);
    if (data["id"].toString().isEmpty() || data["name"].toString().isEmpty() || !webUrl(url)) continue;
    auto *card = new AppCard(data, root, appGrid);
    if (card->property("tested").toBool()) ++tested;
    connect(card, &QPushButton::clicked, this, [this, url] {
      if (!QDesktopServices::openUrl(url))
        QMessageBox::warning(this, "Could not open the browser", "Open this download page in your browser:\n" + url.toString());
    });
    cards.append(card);
  }
  count->setText(QString("%1 tested  ·  %2 untested").arg(tested).arg(cards.size() - tested));
  if (cards.isEmpty())
    layout->addWidget(label("The app catalog could not be loaded. You can still choose a .deb file above.", "debMuted", body));
  auto *suggest = new AppCard({{"id", "suggest"}, {"name", "Your .deb app"},
                               {"icon", "list-add"}, {"note", "Share a working app or a failure with Xetal"}}, root, appGrid);
  cards.append(suggest);
  connect(suggest, &QPushButton::clicked, this, &DebInstallerPage::feedback);
  appGrid->installEventFilter(this);
  arrangeCards();
  layout->addWidget(appGrid);

  auto *feedbackBox = new QFrame(body);
  feedbackBox->setObjectName("debFeedbackBox");
  auto *feedbackRow = new QHBoxLayout(feedbackBox);
  feedbackRow->setContentsMargins(18, 14, 18, 14);
  auto *copy = new QVBoxLayout;
  copy->addWidget(label("Help the next app work.", "debSectionTitle", feedbackBox));
  copy->addWidget(label("Send Xetal the app name, .deb download link and error via Echo or Discord so we can improve support.", "debMuted", feedbackBox));
  feedbackRow->addLayout(copy, 1);
  auto *report = new QPushButton("Send feedback…", feedbackBox);
  report->setObjectName("debFeedbackButton");
  report->setIcon(QIcon::fromTheme("mail-message-new"));
  connect(report, &QPushButton::clicked, this, &DebInstallerPage::feedback);
  feedbackRow->addWidget(report);
  layout->addWidget(feedbackBox);
  layout->addStretch();
}

bool DebInstallerPage::eventFilter(QObject *watched, QEvent *event) {
  if (watched == appGrid && event->type() == QEvent::Resize) arrangeCards();
  return QWidget::eventFilter(watched, event);
}

void DebInstallerPage::arrangeCards() {
  const int next = qBound(1, (appGrid->width() + 12) / 242, 4);
  if (next == columns) return;
  while (auto *item = grid->takeAt(0)) delete item;
  for (int i = 0; i < 4; ++i) grid->setColumnStretch(i, i < next ? 1 : 0);
  for (int i = 0; i < cards.size(); ++i) grid->addWidget(cards[i], i / next, i % next);
  columns = next;
}

void DebInstallerPage::feedback() {
  auto *dialog = new QDialog(this);
  dialog->setObjectName("debFeedbackDialog");
  dialog->setWindowTitle(".deb feedback · Hyper Fusion");
  dialog->setAttribute(Qt::WA_DeleteOnClose);
  dialog->setProperty("xetalWindowSized", true);
  dialog->setWindowModality(Qt::WindowModal);
  dialog->resize(660, 560);
  auto *layout = new QVBoxLayout(dialog);
  layout->setContentsMargins(22, 20, 22, 20);
  layout->setSpacing(12);
  layout->addWidget(label("Tell Xetal what happened", "debCatalogTitle", dialog));
  layout->addWidget(label("Include the original .deb download page so we can reproduce the problem and add support. "
                          "Copy your report, then paste it into your message. Nothing is sent automatically.", "debMuted", dialog));
  auto *form = new QFormLayout;
  form->setFieldGrowthPolicy(QFormLayout::ExpandingFieldsGrow);
  auto *app = new QLineEdit(dialog);
  app->setObjectName("debFeedbackApp");
  app->setPlaceholderText("Application name");
  form->addRow("Application", app);
  auto *version = new QLineEdit(dialog);
  version->setObjectName("debFeedbackVersion");
  version->setPlaceholderText("Version, if known");
  form->addRow("App version", version);
  auto *url = new QLineEdit(dialog);
  url->setObjectName("debFeedbackUrl");
  url->setPlaceholderText("https://… (where to get the .deb)");
  form->addRow("Download link", url);
  auto *result = new QComboBox(dialog);
  result->setObjectName("debFeedbackResult");
  result->addItems({"Installation failed", "Installed, but the app failed to launch", "Installed and launched successfully"});
  form->addRow("Result", result);
  layout->addLayout(form);
  auto *details = new QPlainTextEdit(dialog);
  details->setObjectName("debFeedbackDetails");
  details->setPlaceholderText("What happened? Paste the relevant error, or describe what you tested.");
  details->setAccessibleName("Error or test details");
  details->setMinimumHeight(90);
  layout->addWidget(details, 1);
  const auto username = contacts["echo_username"].toString("xetal");
  layout->addWidget(label("Echo: Friends → Add friend → " + username + ". Once accepted, open the conversation and paste your report.\n" +
                          contacts["discord_hint"].toString("In Discord, open your conversation with Xetal and paste your report."), "debMuted", dialog));
  auto *status = label("", "debFeedbackStatus", dialog);
  status->setAccessibleName("Feedback status");
  layout->addWidget(status);
  auto *buttons = new QHBoxLayout;
  auto *copy = new QPushButton("Copy report", dialog);
  copy->setObjectName("debCopyReport");
  auto *echo = new QPushButton("Copy && open Echo", dialog);
  echo->setObjectName("debOpenEcho");
  auto *discord = new QPushButton("Copy && open Discord", dialog);
  discord->setObjectName("debOpenDiscord");
  const auto copyReport = [app, version, url, result, details, status] {
    if (app->text().trimmed().isEmpty()) {
      status->setText("Enter the application name."); app->setFocus(); return false;
    }
    const QUrl download(url->text().trimmed(), QUrl::StrictMode);
    if (!webUrl(download)) {
      status->setText("Enter an http or https download link for the .deb."); url->setFocus(); return false;
    }
    if (details->toPlainText().trimmed().isEmpty()) {
      status->setText("Add the error or a few details about what you tested."); details->setFocus(); return false;
    }
    const auto report = QString("Hyper Fusion · Experimental .deb installer\n"
                               "Application: %1\nVersion: %2\n.deb download: %3\nResult: %4\n"
                               "System: %5 (%6)\nDate: %7\n\nDetails:\n%8")
        .arg(app->text().trimmed(), version->text().trimmed().isEmpty() ? "Not specified" : version->text().trimmed(),
             download.toString(), result->currentText(), QSysInfo::prettyProductName(), QSysInfo::currentCpuArchitecture(),
             QDate::currentDate().toString(Qt::ISODate), details->toPlainText().trimmed());
    QApplication::clipboard()->setText(report);
    status->setText("Report copied. Paste it into your message to Xetal.");
    return true;
  };
  connect(copy, &QPushButton::clicked, dialog, [copyReport] { copyReport(); });
  const auto openContact = [copyReport, status](const QString &target) {
    if (!copyReport()) return;
    const QUrl url(target, QUrl::StrictMode);
    if (!webUrl(url) || !QDesktopServices::openUrl(url))
      status->setText("Report copied. Could not open the browser; open your chat app and paste it there.");
  };
  connect(echo, &QPushButton::clicked, dialog, [openContact, this] {
    openContact(contacts["echo_url"].toString("https://www.xetal.net/community/site/echo-web/"));
  });
  connect(discord, &QPushButton::clicked, dialog, [openContact, this] {
    openContact(contacts["discord_url"].toString("https://discord.com/channels/@me"));
  });
  for (auto *button : {copy, echo, discord}) { button->setAutoDefault(false); buttons->addWidget(button); }
  layout->addLayout(buttons);
  auto *close = new QDialogButtonBox(QDialogButtonBox::Close, dialog);
  connect(close, &QDialogButtonBox::rejected, dialog, &QDialog::reject);
  layout->addWidget(close);
  dialog->open();
  app->setFocus();
}
