#pragma once
#include <QElapsedTimer>
#include <QPersistentModelIndex>
#include <QTimer>
#include <QWidget>

class QAbstractItemView;

namespace Fusion {
// A mouse-transparent viewport layer: the dragged selection stays selected.
class DropTargetFeedback : public QWidget {
public:
  explicit DropTargetFeedback(QAbstractItemView *view);
  void present(const QModelIndex &index, Qt::DropAction operation);
  void clear();
protected:
  bool eventFilter(QObject *object, QEvent *event) override;
  void paintEvent(QPaintEvent *) override;
private:
  QAbstractItemView *view;
  QPersistentModelIndex target;
  Qt::DropAction operation = Qt::IgnoreAction;
  QElapsedTimer elapsed;
  QTimer animation;
};
}
