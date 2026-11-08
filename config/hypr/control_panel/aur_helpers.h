#pragma once
#include <QStandardPaths>
#include <QString>

namespace HyperPanel {
inline bool aurHelperInstalled(const QString &name) {
  return (name == "yay" || name == "paru") && !QStandardPaths::findExecutable(name).isEmpty();
}
}
