#include "drop_feedback.h"
#include <QAbstractItemView>
#include <QApplication>
#include <QListView>
#include <QPainter>
#include <QScrollBar>
#include <cmath>

Fusion::DropTargetFeedback::DropTargetFeedback(QAbstractItemView *view)
    : QWidget(view->viewport()), view(view) {
  setObjectName("folderDropFeedback");
  setAttribute(Qt::WA_TransparentForMouseEvents);
  setAttribute(Qt::WA_NoSystemBackground);
  setFocusPolicy(Qt::NoFocus);
  hide();
  view->viewport()->installEventFilter(this);
  animation.setInterval(33);
  connect(&animation, &QTimer::timeout, this, [this] {
    if (!target.isValid() || !this->view->isVisible()) { clear(); return; }
    update();
  });
  // Never keep a marker on a stale row after navigation, filtering or scrolling.
  connect(view->model(), &QAbstractItemModel::modelAboutToBeReset, this, &DropTargetFeedback::clear);
  connect(view->model(), &QAbstractItemModel::rowsAboutToBeRemoved, this, &DropTargetFeedback::clear);
  connect(view->model(), &QAbstractItemModel::layoutAboutToBeChanged, this, &DropTargetFeedback::clear);
  connect(view->verticalScrollBar(), &QScrollBar::valueChanged, this, &DropTargetFeedback::clear);
  connect(view->horizontalScrollBar(), &QScrollBar::valueChanged, this, &DropTargetFeedback::clear);
}

void Fusion::DropTargetFeedback::present(const QModelIndex &index, Qt::DropAction next) {
  if (!index.isValid() || next == Qt::IgnoreAction) { clear(); return; }
  const auto name = index.siblingAtColumn(0);
  if (target != name || !isVisible()) elapsed.restart();
  target = name; operation = next;
  const auto verb = next == Qt::CopyAction ? tr("Copy") : next == Qt::LinkAction ? tr("Create shortcuts") : tr("Move");
  setAccessibleName(tr("%1 into %2").arg(verb, name.data().toString()));
  setGeometry(view->viewport()->rect());
  show(); raise();
  if (!animation.isActive()) animation.start();
  update();
}

void Fusion::DropTargetFeedback::clear() {
  animation.stop();
  target = QPersistentModelIndex(); operation = Qt::IgnoreAction;
  setAccessibleName({});
  hide();
}

bool Fusion::DropTargetFeedback::eventFilter(QObject *object, QEvent *event) {
  if (object == view->viewport()) {
    switch (event->type()) {
    case QEvent::DragLeave: case QEvent::Drop: case QEvent::Hide: case QEvent::Resize:
      clear(); break;
    default: break;
    }
  }
  return QWidget::eventFilter(object, event);
}

void Fusion::DropTargetFeedback::paintEvent(QPaintEvent *) {
  if (!target.isValid() || width() < 36 || height() < 36) return;
  QRectF cell = view->visualRect(target);
  if (cell.height() < 8) return;
  auto *list = qobject_cast<QListView *>(view);
  const bool grid = list && list->viewMode() == QListView::IconMode;
  QRectF highlight = cell.adjusted(2, 2, -2, -2);
  if (!list) { highlight.setLeft(2); highlight.setRight(width() - 3); }
  if (!highlight.intersects(rect())) return;
  const qreal size = qMin(qreal(view->iconSize().isValid() ? view->iconSize().height() : 20), cell.height() - 4);
  const QRectF icon = grid ? QRectF(cell.center().x() - size / 2, cell.top() + 3, size, size)
                          : QRectF(cell.left() + 3, cell.center().y() - size / 2, size, size);
  const qreal wave = (1 + std::sin(elapsed.elapsed() * 6.28318530718 / 1150.0)) / 2;
  QColor accent = qApp->property("fusionAccent").value<QColor>();
  if (!accent.isValid()) accent = view->palette().color(QPalette::Highlight);
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  const qreal radius = qMin(qreal(10), highlight.height() / 3);
  auto tint = accent; tint.setAlphaF(.13 + .09 * wave);
  auto glow = accent; glow.setAlphaF(.12 + .14 * wave);
  painter.setPen(QPen(glow, 5)); painter.setBrush(tint);
  painter.drawRoundedRect(highlight, radius, radius);
  auto edge = accent; edge.setAlphaF(.72 + .28 * wave);
  painter.setPen(QPen(edge, 1.6)); painter.setBrush(Qt::NoBrush);
  painter.drawRoundedRect(highlight, radius, radius);

  // Keep the destination icon readable beneath a small, gently bobbing badge.
  const qreal diameter = grid ? qBound(qreal(20), size * .42, qreal(32))
                              : qMin(qreal(20), cell.height() - 4);
  QPointF center(icon.right() - diameter * .12, icon.top() + diameter * .36 - wave * (grid ? 2 : .6));
  center.setX(qBound(diameter / 2 + 2, center.x(), width() - diameter / 2 - 2));
  center.setY(qBound(diameter / 2 + 2, center.y(), height() - diameter / 2 - 2));
  const QRectF badge(center.x() - diameter / 2, center.y() - diameter / 2, diameter, diameter);
  auto shadow = view->palette().color(QPalette::Shadow); shadow.setAlpha(100);
  painter.setPen(Qt::NoPen); painter.setBrush(shadow);
  painter.drawEllipse(badge.translated(0, 1.5));
  painter.setPen(QPen(accent.lighter(130), 1.2)); painter.setBrush(accent);
  painter.drawEllipse(badge);
  // Contrast follows the accent instead of assuming every theme is dark.
  const qreal brightness = .2126 * accent.redF() + .7152 * accent.greenF() + .0722 * accent.blueF();
  painter.setPen(QPen(brightness > .6 ? QColor("#101820") : QColor(Qt::white),
                      qMax(qreal(1.5), diameter / 13), Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
  painter.setBrush(Qt::NoBrush);
  painter.translate(center); painter.scale(diameter / 24, diameter / 24);
  if (operation == Qt::CopyAction) {
    painter.drawRoundedRect(QRectF(-6, -6, 9, 11), 1.3, 1.3);
    painter.drawLine(QPointF(-3, -8), QPointF(6, -8));
    painter.drawLine(QPointF(6, -8), QPointF(6, 1));
    painter.drawLine(QPointF(4, 5), QPointF(10, 5));
    painter.drawLine(QPointF(7, 2), QPointF(7, 8));
  } else if (operation == Qt::LinkAction) {
    painter.rotate(-40);
    painter.drawRoundedRect(QRectF(-8, -4, 9, 8), 3.5, 3.5);
    painter.drawRoundedRect(QRectF(-1, -4, 9, 8), 3.5, 3.5);
  } else {
    painter.drawLine(QPointF(0, -7), QPointF(0, 4));
    painter.drawPolyline(QPolygonF{QPointF(-4, 0), QPointF(0, 4), QPointF(4, 0)});
    painter.drawPolyline(QPolygonF{QPointF(-7, 4), QPointF(-7, 8), QPointF(7, 8), QPointF(7, 4)});
  }
}
