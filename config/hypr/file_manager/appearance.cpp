#include "appearance.h"
#include <QApplication>
#include <QFont>
#include <QPalette>

namespace Fusion {
namespace {
void apply(const QJsonObject &value) {
  const bool follow = value["theme"].toString("follow") == "follow";
  qApp->setProperty("xetalThemeDesign", follow ? QVariant{} : value["design"].toVariant());
  qApp->setProperty("xetalThemeIconTheme", follow ? QVariant{} : value["iconTheme"].toVariant());
  QPalette palette;
  const auto colors = value["colors"].toObject();
  const auto roles = QMetaEnum::fromType<QPalette::ColorRole>();
  for (auto it = colors.begin(); it != colors.end(); ++it) {
    const int role = roles.keyToValue(it.key().toUtf8());
    if (role >= 0)
      palette.setColor(QPalette::All, QPalette::ColorRole(role), QColor(it.value().toString()));
  }
  for (auto role : {QPalette::Text, QPalette::WindowText, QPalette::ButtonText})
    palette.setColor(QPalette::Disabled, role, QColor(colors["Disabled"].toString()));
  qApp->setPalette(palette);
  qApp->setProperty("fusionAccent", QColor(colors["Accent"].toString()));
  qApp->setFont(QFont(value["font"].toString("Noto Sans"), 10));
  QStringList iconPaths;
  for (const auto &path : value["iconSearchPaths"].toArray()) iconPaths << path.toString();
  QIcon::setThemeSearchPaths(iconPaths);
  QIcon::setFallbackThemeName(value["iconFallbackTheme"].toString("hicolor"));
  QIcon::setThemeName(value["iconTheme"].toString());
  qApp->setStyleSheet(value["stylesheet"].toString());
}
}

Appearance::Appearance(const QString &settingsPath, QObject *parent)
    : QObject(parent), preferences(settingsPath) {
  debounce.setSingleShot(true);
  debounce.setInterval(100);
  timeout.setSingleShot(true);
  timeout.setInterval(10000);
  connect(&debounce, &QTimer::timeout, this, &Appearance::reload);
  connect(&timeout, &QTimer::timeout, this, [this] { renderer.kill(); });
  const auto themeDirectory = root() + "/theme";
  if (QFileInfo::exists(themeDirectory)) watcher.addPath(themeDirectory);
  const auto preferencesPath = preferences.settings.fileName();
  const auto settingsDirectory = QFileInfo(preferencesPath).absolutePath();
  QDir().mkpath(settingsDirectory);
  watcher.addPath(settingsDirectory);
  if (QFileInfo::exists(preferencesPath)) watcher.addPath(preferencesPath);
  auto preferenceChanged = [this, preferencesPath] {
    if (QFileInfo::exists(preferencesPath) && !watcher.files().contains(preferencesPath))
      watcher.addPath(preferencesPath);
    preferences.settings.sync();
    if (preferences.settings.value("appearance/theme", "follow").toString() != requestedTheme)
      debounce.start();
  };
  connect(&watcher, &QFileSystemWatcher::directoryChanged, this,
          [this, preferenceChanged, themeDirectory](const QString &path) {
            if (path == themeDirectory) debounce.start();
            else preferenceChanged();
          });
  connect(&watcher, &QFileSystemWatcher::fileChanged, this, preferenceChanged);
  connect(&renderer, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
    if (error == QProcess::FailedToStart) { timeout.stop(); complete(); }
  });
  connect(&renderer, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status) {
    timeout.stop();
    const auto value = QJsonDocument::fromJson(renderer.readAllStandardOutput()).object();
    renderer.readAllStandardError();
    preferences.settings.sync();
    if (preferences.settings.value("appearance/theme", "follow").toString() != requestedTheme) {
      debounce.start();
      return;
    }
    if (!code && status == QProcess::NormalExit && value["stylesheet"].isString()) {
      apply(value);
      emit changed(value);
    }
    // A missing/damaged theme must not prevent access to file properties.
    complete();
  });
  QTimer::singleShot(0, this, &Appearance::reload);
}
Appearance::~Appearance() {
  disconnect(&renderer, nullptr, this, nullptr);
  if (renderer.state() != QProcess::NotRunning) {
    renderer.kill();
    renderer.waitForFinished(1000);
  }
}
void Appearance::reload() {
  if (renderer.state() != QProcess::NotRunning) { debounce.start(); return; }
  preferences.settings.sync();
  requestedTheme = preferences.settings.value("appearance/theme", "follow").toString();
  renderer.start("python3", {root() + "/file_manager/appearance.py", "--theme", requestedTheme});
  timeout.start();
}
void Appearance::complete() {
  if (initialComplete) return;
  initialComplete = true;
  emit initialized();
}
} // namespace Fusion
