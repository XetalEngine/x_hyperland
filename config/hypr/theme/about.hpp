#pragma once

#include <QClipboard>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTimer>
#include <QtWidgets>

namespace FusionAbout {

inline QDialog *show(QWidget *parent, const QString &root,
                     const QString &appName, const QString &description,
                     const QString &credits = {}) {
  if (auto *existing = parent->findChild<QDialog *>("fusionAboutDialog")) {
    existing->show();
    existing->raise();
    existing->activateWindow();
    return existing;
  }

  QFile file(root + "/theme/about.json");
  QJsonObject identity;
  if (file.open(QIODevice::ReadOnly))
    identity = QJsonDocument::fromJson(file.readAll()).object();
  const auto value = [&identity](const QString &key, const QString &fallback) {
    const auto text = identity.value(key).toString().trimmed();
    return text.isEmpty() ? fallback : text;
  };

  auto *dialog = new QDialog(parent);
  dialog->setObjectName("fusionAboutDialog");
  dialog->setWindowTitle("About " + appName);
  dialog->setWindowIcon(parent->windowIcon());
  dialog->setAttribute(Qt::WA_DeleteOnClose);
  dialog->setWindowModality(Qt::WindowModal);
  dialog->setMinimumWidth(440);
  dialog->setStyleSheet(R"(
    QDialog#fusionAboutDialog { background: palette(window); color: palette(window-text); }
    QDialog#fusionAboutDialog QLabel { background: transparent; color: palette(window-text); border: none; padding: 0; }
    QLabel#aboutAppName { font-size: 23px; font-weight: 700; }
    QLabel#aboutBrand { color: palette(highlight); font-weight: 700; letter-spacing: 2px; }
    QLabel#aboutAuthor { font-size: 17px; font-weight: 600; }
    QFrame#aboutIdentity { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }
    QDialog#fusionAboutDialog QPushButton { min-height: 22px; padding: 5px 14px; }
  )");
  auto *layout = new QVBoxLayout(dialog);
  layout->setContentsMargins(24, 24, 24, 20);
  layout->setSpacing(18);

  const auto label = [](const QString &text, QWidget *owner,
                        const QString &name = QString()) {
    auto *widget = new QLabel(text, owner);
    widget->setTextFormat(Qt::PlainText);
    widget->setObjectName(name);
    widget->setWordWrap(true);
    widget->setTextInteractionFlags(Qt::TextSelectableByMouse |
                                    Qt::TextSelectableByKeyboard);
    return widget;
  };
  auto *header = new QHBoxLayout;
  header->setSpacing(16);
  auto appIcon = parent->windowIcon();
  if (appIcon.isNull())
    appIcon = dialog->style()->standardIcon(QStyle::SP_MessageBoxInformation);
  auto *icon = new QLabel(dialog);
  icon->setFixedSize(48, 48);
  icon->setPixmap(appIcon.pixmap(48, 48));
  header->addWidget(icon);
  auto *titles = new QVBoxLayout;
  titles->setSpacing(4);
  titles->addWidget(label("HYPER FUSION", dialog, "aboutBrand"));
  titles->addWidget(label(appName, dialog, "aboutAppName"));
  header->addLayout(titles, 1);
  layout->addLayout(header);
  layout->addWidget(label(description, dialog));

  auto *identityCard = new QFrame(dialog);
  identityCard->setObjectName("aboutIdentity");
  auto *details = new QVBoxLayout(identityCard);
  details->setContentsMargins(18, 16, 18, 16);
  details->setSpacing(10);
  details->addWidget(label("Author", identityCard));
  details->addWidget(label(value("author", "Xetal — Thiago Costa"),
                           identityCard, "aboutAuthor"));
  details->addSpacing(8);
  auto *contacts = new QGridLayout;
  contacts->setHorizontalSpacing(18);
  contacts->setVerticalSpacing(10);
  contacts->setColumnStretch(1, 1);
  const auto contact = [&](int row, const QString &service,
                           const QString &key) {
    const auto username = value(key, "xetal");
    contacts->addWidget(label(service, identityCard), row, 0);
    contacts->addWidget(label(username, identityCard, "about" + service),
                        row, 1);
    auto *copy = new QPushButton("Copy", identityCard);
    copy->setObjectName("copy" + service + "Username");
    copy->setAccessibleName("Copy " + service + " username");
    copy->setToolTip("Copy " + service + " username");
    copy->setAutoDefault(false);
    copy->setMinimumWidth(86);
    auto *reset = new QTimer(copy);
    reset->setSingleShot(true);
    QObject::connect(reset, &QTimer::timeout, copy,
                     [copy] { copy->setText("Copy"); });
    QObject::connect(copy, &QPushButton::clicked, copy,
                     [copy, reset, username] {
      QApplication::clipboard()->setText(username);
      copy->setText("Copied");
      reset->start(1600);
    });
    contacts->addWidget(copy, row, 2);
  };
  contact(0, "Discord", "discord");
  contact(1, "Echo", "echo");
  details->addLayout(contacts);
  layout->addWidget(identityCard);
  if (!credits.isEmpty())
    layout->addWidget(label(credits, dialog, "aboutCredits"));
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close, dialog);
  buttons->button(QDialogButtonBox::Close)->setDefault(true);
  QObject::connect(buttons, &QDialogButtonBox::rejected,
                   dialog, &QDialog::reject);
  layout->addWidget(buttons);
  dialog->resize(480, dialog->sizeHint().height());
  dialog->open();
  buttons->button(QDialogButtonBox::Close)->setFocus();
  return dialog;
}

} // namespace FusionAbout
