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
  dialog->setMinimumWidth(400);
  QFile style(root + "/theme/about.qss");
  if (style.open(QIODevice::ReadOnly)) dialog->setStyleSheet(QString::fromUtf8(style.readAll()));
  auto *layout = new QVBoxLayout(dialog);
  layout->setContentsMargins(22, 20, 22, 18);
  layout->setSpacing(14);
  layout->setSizeConstraint(QLayout::SetMinimumSize);
  const auto label = [](const QString &text, QWidget *owner,
                        const QString &name = QString()) {
    auto *widget = new QLabel(text, owner);
    widget->setTextFormat(Qt::PlainText);
    widget->setObjectName(name);
    widget->setWordWrap(true);
    widget->setTextInteractionFlags(Qt::TextSelectableByMouse | Qt::TextSelectableByKeyboard);
    return widget;
  };
  auto *content = dialog;
  auto *body = layout;
  auto *brand = new QHBoxLayout;
  brand->addWidget(label("HYPER FUSION", content, "aboutBrand"), 1);
  QFile version(root + "/VERSION");
  if (version.open(QIODevice::ReadOnly)) {
    const auto text = QString::fromUtf8(version.readAll()).trimmed();
    if (!text.isEmpty()) brand->addWidget(label(text, content, "aboutVersion"));
  }
  body->addLayout(brand);
  auto *logo = new QLabel(content);
  logo->setObjectName("aboutEngineLogo");
  logo->setAccessibleName("Xetal Engine");
  QPixmap pixmap(root + "/theme/assets/xetal-engine.png");
  if (!pixmap.isNull()) logo->setPixmap(pixmap.scaled(330, 60, Qt::KeepAspectRatio, Qt::SmoothTransformation));
  else logo->setText("XETAL ENGINE");
  logo->setAlignment(Qt::AlignCenter);
  logo->setFixedHeight(68);
  body->addWidget(logo);
  auto *titles = new QVBoxLayout;
  titles->setSpacing(6);
  auto *appLabel = label(appName, content, "aboutAppName");
  appLabel->setAlignment(Qt::AlignCenter);
  titles->addWidget(appLabel);
  auto *descriptionLabel = label(description, content, "aboutDescription");
  descriptionLabel->setProperty("aboutMuted", true);
  descriptionLabel->setAlignment(Qt::AlignCenter);
  titles->addWidget(descriptionLabel);
  body->addLayout(titles);

  auto *identityCard = new QFrame(content);
  identityCard->setObjectName("aboutIdentity");
  auto *details = new QVBoxLayout(identityCard);
  details->setContentsMargins(18, 16, 18, 16);
  details->setSpacing(8);
  auto *caption = label("CREATED BY", identityCard);
  caption->setProperty("aboutCaption", true);
  caption->setProperty("aboutMuted", true);
  details->addWidget(caption);
  details->addWidget(label(value("author", "Xetal — Thiago Costa"), identityCard, "aboutAuthor"));
  details->addSpacing(4);
  auto *contacts = new QHBoxLayout;
  contacts->setSpacing(12);
  const auto contact = [&](const QString &service, const QString &key) {
    const auto username = value(key, "xetal");
    auto *card = new QFrame(identityCard);
    card->setProperty("aboutContact", true);
    auto *row = new QHBoxLayout(card);
    row->setContentsMargins(14, 12, 14, 12);
    row->setSpacing(10);
    auto *column = new QVBoxLayout;
    column->setSpacing(4);
    row->addLayout(column, 1);
    auto *serviceLabel = label(service, card);
    serviceLabel->setProperty("aboutMuted", true);
    column->addWidget(serviceLabel);
    auto *handle = label(username, card, "about" + service);
    handle->setProperty("aboutHandle", true);
    column->addWidget(handle);
    auto *copy = new QPushButton("Copy", card);
    copy->setObjectName("copy" + service + "Username");
    copy->setAccessibleName("Copy " + service + " username");
    copy->setToolTip("Copy " + service + " username");
    copy->setAutoDefault(false);
    auto *reset = new QTimer(copy);
    reset->setSingleShot(true);
    QObject::connect(reset, &QTimer::timeout, copy, [copy] { copy->setText("Copy"); });
    QObject::connect(copy, &QPushButton::clicked, copy, [copy, reset, username] {
      QApplication::clipboard()->setText(username);
      copy->setText("Copied");
      reset->start(1600);
    });
    row->addWidget(copy);
    contacts->addWidget(card, 1);
  };
  contact("Discord", "discord");
  contact("Echo", "echo");
  details->addLayout(contacts);
  body->addWidget(identityCard);
  if (!credits.isEmpty()) {
    auto *creditLabel = label(credits, content, "aboutCredits");
    creditLabel->setProperty("aboutMuted", true);
    body->addWidget(creditLabel);
  }
  auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close, dialog);
  buttons->button(QDialogButtonBox::Close)->setDefault(true);
  QObject::connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);
  layout->addWidget(buttons);
  const auto fitContents = [dialog, layout] {
    dialog->ensurePolished();
    const auto available = dialog->screen()->availableGeometry();
    int width = qMax(layout->minimumSize().width(), qMin(580, available.width() - 40));
    int height = qMax(layout->minimumSize().height(), layout->totalHeightForWidth(width));
    // Keep text at its normal size on shorter displays. A content minimum
    // prevents saved window geometry from clipping contacts or credits.
    if (height > available.height() - 72) {
      width = qMax(width, qMin(720, available.width() - 40));
      height = qMax(layout->minimumSize().height(), layout->totalHeightForWidth(width));
    }
    dialog->setMinimumSize(width, height);
    dialog->resize(width, height);
  };
  fitContents();
  dialog->open();
  QTimer::singleShot(0, dialog, fitContents);
  buttons->button(QDialogButtonBox::Close)->setFocus();
  return dialog;
}

} // namespace FusionAbout
