#pragma once
#include <QUrl>
class QWidget;
class KJob;

namespace Fusion {
KJob *pasteFiles(const QUrl &destination, QWidget *window);
}
