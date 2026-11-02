#pragma once
#include "transfer_access.h"
#include <QUrl>
#include <QPoint>
class QDropEvent;
class QWidget;
class KJob;

namespace Fusion {
KJob *pasteFiles(const QUrl &destination, QWidget *window);
KJob *transferFiles(const QList<QUrl> &sources, const QUrl &destination,
                    TransferOperation operation, QWidget *window);
KJob *dropFiles(const QDropEvent *event, const QUrl &destination,
                QWidget *window, const QPoint &menuPosition);
}
