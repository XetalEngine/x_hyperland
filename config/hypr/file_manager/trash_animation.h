#pragma once
#include <QtWidgets>
namespace Fusion {
struct TrashIcon { QUrl url; QPixmap image; QRectF start; };
void animateTrash(QWidget *window, const QList<TrashIcon> &icons, const QPointF &destination);
}
