#pragma once
#include <QDir>
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QImageReader>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMovie>
#include <QPainter>
#include <QPainterPath>
#include <QSettings>
#include <QWidget>

namespace FusionAccounts {
inline QString avatarPath(const QString &user, const QString &home, const QString &root,
                          bool current, const QString &accounts = "/var/lib/AccountsService") {
  QStringList paths;
  if (current) {
    QFile file(root + "/theme/state.json");
    const auto state = file.open(QIODevice::ReadOnly) ? QJsonDocument::fromJson(file.readAll()).object() : QJsonObject();
    auto choice = state.value("avatar").toString("assets/account.gif");
    if (!choice.isEmpty() && choice != "auto") {
      if (choice.startsWith("~/")) choice = home + choice.mid(1);
      paths << (QDir::isAbsolutePath(choice) ? choice : root + "/theme/" + choice);
    }
  }
  // Match the desktop's account-image precedence; never use this session's
  // chosen avatar for another account in the table.
  paths << home + "/.face.icon" << home + "/.face";
  QSettings account(accounts + "/users/" + user, QSettings::IniFormat);
  paths << account.value("User/Icon").toString() << accounts + "/icons/" + user;
  if (current) paths << root + "/theme/assets/account.gif" << root + "/startup/assets/xetal-mascot.png";
  for (const auto &path : paths)
    if (!path.isEmpty() && QFileInfo(path).isFile() && QImageReader(path).canRead()) return path;
  return {};
}

inline QPixmap cropped(const QPixmap &source, int size) {
  if (source.isNull()) return {};
  auto scaled = source.scaled(size, size, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
  QPixmap result(size, size); result.fill(Qt::transparent);
  QPainter paint(&result); paint.setRenderHint(QPainter::Antialiasing);
  QPainterPath clip; clip.addEllipse(result.rect()); paint.setClipPath(clip);
  paint.drawPixmap((size-scaled.width())/2, (size-scaled.height())/2, scaled);
  return result;
}

class Avatar final : public QWidget {
public:
  explicit Avatar(QWidget *parent = nullptr) : QWidget(parent) { setFixedSize(72,72); }
  void setSource(const QString &path) {
    const auto modified = QFileInfo(path).lastModified();
    if (source == path && stamp == modified) return;
    source = path; stamp = modified;
    delete movie; movie = nullptr;
    still = QPixmap(path);
    if (QImageReader(path).supportsAnimation()) {
      movie = new QMovie(path, QByteArray(), this);
      connect(movie, &QMovie::frameChanged, this, [this] { update(); });
      if (isVisible()) movie->start();
    }
    update();
  }
protected:
  void paintEvent(QPaintEvent *) override {
    QPainter painter(this);
    const auto frame = movie && !movie->currentPixmap().isNull() ? movie->currentPixmap() : still;
    painter.drawPixmap(0,0,cropped(frame,72));
  }
  void showEvent(QShowEvent *event) override {
    QWidget::showEvent(event);
    if (movie) { if (movie->state() == QMovie::NotRunning) movie->start(); else movie->setPaused(false); }
  }
  void hideEvent(QHideEvent *event) override {
    if (movie) movie->setPaused(true);
    QWidget::hideEvent(event);
  }
private:
  QString source;
  QDateTime stamp;
  QPixmap still;
  QMovie *movie = nullptr;
};
}
