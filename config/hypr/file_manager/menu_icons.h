#pragma once
#include <QIcon>
#include <QString>

namespace Fusion {
// Menu-only symbols. User image paths and application icons remain intact.
QIcon menuIcon(const QString &name);
// The same symbols in the theme's foreground color for inline UI artwork.
QIcon symbolicIcon(const QString &name);
}
