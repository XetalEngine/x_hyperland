#pragma once
#include "transfer_access.h"
#include <QUrl>
#include <QPoint>
#include <Qt>
class QDropEvent;
class QMimeData;
class QWidget;
class KJob;

namespace Fusion {
bool acceptsFileDrop(const QMimeData *mime);
Qt::DropAction fileDropAction(const QMimeData *mime, Qt::KeyboardModifiers modifiers,
                             Qt::DropActions possible);
KJob *pasteFiles(const QUrl &destination, QWidget *window);
KJob *transferFiles(const QList<QUrl> &sources, const QUrl &destination,
                    TransferOperation operation, QWidget *window);
KJob *dropFiles(const QDropEvent *event, const QUrl &destination,
                QWidget *window, const QPoint &menuPosition);
}
