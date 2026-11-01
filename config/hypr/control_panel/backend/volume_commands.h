#pragma once
#include <QStringList>

// Shared by Control Panel and Fusion Files. Arguments are passed directly to
// udisksctl; authentication is handled by the session's polkit agent.
namespace FusionVolumes {
inline QStringList mount(const QString &device, bool force = false) {
  QStringList args{"mount", "-b", device};
  if (force)
    args << "-o" << "force";
  return args;
}
inline QStringList unmount(const QString &device) {
  return {"unmount", "-b", device};
}
} // namespace FusionVolumes
