#pragma once
#include "transfer_access.h"
#include <QUrl>
#include <QPoint>
#include <Qt>
#include <functional>
class QDropEvent;
class QMimeData;
class QWidget;
class KJob;

namespace Fusion {
bool acceptsFileDrop(const QMimeData *mime);
Qt::DropAction fileDropOperation(const QMimeData *mime, Qt::KeyboardModifiers modifiers,
                                Qt::DropActions possible);
Qt::DropAction fileDropAction(const QMimeData *mime, Qt::KeyboardModifiers modifiers,
                             Qt::DropActions possible);
bool fileDropDestination(const QUrl &destination);
QList<QUrl> clipboardFiles(const QMimeData *mime);
bool canPasteFiles(const QMimeData *mime);
KJob *pasteFiles(const QUrl &destination, QWidget *window);
KJob *undoTransfer(QWidget *window);
KJob *transferFiles(const QList<QUrl> &sources, const QUrl &destination,
                    TransferOperation operation, QWidget *window,
                    std::function<void(const QUrl &)> destinationChanged = {});
KJob *dropFiles(const QDropEvent *event, const QUrl &destination,
                QWidget *window, const QPoint &menuPosition);
}
