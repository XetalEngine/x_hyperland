#pragma once
#include "src/config.h"
#include "src/launcher.h"
#include <QString>
#include <QStringList>

namespace XetalProton::Desktop {
QString root();
QString bridge();
QString storage();
QString manifest(const std::string &id);
QStringList schemes(const std::string &value);
QString validate(const Shortcut &shortcut);
LaunchSpec managedLaunch(LaunchSpec spec, const Shortcut &shortcut);
}
