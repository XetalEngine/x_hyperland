#pragma once
#include "core.h"

namespace Fusion {
// Files windows, file pickers and desktop Properties share one appearance
// loader, including a theme pinned in Files preferences and live changes.
class Appearance : public QObject {
  Q_OBJECT
public:
  explicit Appearance(const QString &settingsPath = {}, QObject *parent = nullptr);
  ~Appearance() override;
  void reload();
signals:
  void changed(const QJsonObject &value);
  void initialized();
private:
  Preferences preferences;
  QFileSystemWatcher watcher;
  QProcess renderer;
  QTimer debounce, timeout;
  QString requestedTheme;
  bool initialComplete = false;
  void complete();
};
} // namespace Fusion
