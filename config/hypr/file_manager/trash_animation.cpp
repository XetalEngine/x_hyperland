#include "trash_animation.h"
#include <cmath>
namespace {
class TrashFlight : public QWidget {
public:
  TrashFlight(QWidget *window, QList<Fusion::TrashIcon> icons, QPointF target)
      : QWidget(window), icons(std::move(icons)), target(target) {
    setObjectName("trashFlight");
    setAttribute(Qt::WA_TransparentForMouseEvents);
    setAttribute(Qt::WA_NoSystemBackground);
    setStyleSheet("background:transparent; border:none;");
    setGeometry(window->rect());
    accent = qApp->property("fusionAccent").value<QColor>();
    if (!accent.isValid()) accent = palette().highlight().color();
    animation.setDuration(720);
    animation.setStartValue(0.0);
    animation.setEndValue(1.0);
    connect(&animation, &QVariantAnimation::valueChanged, this, [this](const QVariant &value) { progress = value.toReal(); update(); });
    connect(&animation, &QVariantAnimation::finished, this, &QObject::deleteLater);
    show(); raise(); animation.start();
  }
protected:
  void paintEvent(QPaintEvent *) override {
    QPainter painter(this);
    painter.setRenderHints(QPainter::Antialiasing | QPainter::SmoothPixmapTransform);
    for (int i = 0; i < icons.size(); ++i) {
      const auto &icon = icons[i];
      const qreal t = qBound(0.0, (progress - i * .025) / (1 - i * .025), 1.0);
      const qreal eased = t * t * (3 - 2 * t);
      const QPointF origin = icon.start.center();
      QPainterPath curve(origin);
      const qreal lift = qMin(140.0, qAbs(origin.x() - target.x()) * .22 + 50);
      curve.cubicTo(origin + QPointF(-30, -lift), target + QPointF(60, -lift), target);
      auto glow = accent; glow.setAlphaF(.22 * (1 - t));
      painter.setPen(QPen(glow, 2));
      QPainterPath trail(curve.pointAtPercent(qMax(0.0, eased - .18)));
      for (int sample = 1; sample <= 10; ++sample)
        trail.lineTo(curve.pointAtPercent(qMax(0.0, eased - .18) + qMin(eased, .18) * sample / 10));
      painter.drawPath(trail);
      const auto point = curve.pointAtPercent(eased);
      const qreal size = qMax(8.0, icon.start.width() * (1 - .84 * eased));
      painter.save();
      painter.translate(point);
      painter.rotate(-18 * std::sin(t * 3.141592653589793));
      painter.setOpacity(t < .8 ? 1 : (1 - t) * 5);
      painter.drawPixmap(QRectF(-size / 2, -size / 2, size, size), icon.image, icon.image.rect());
      painter.restore();
    }
    if (progress > .7) {
      const qreal pulse = (progress - .7) / .3;
      auto color = accent; color.setAlphaF(.7 * (1 - pulse));
      painter.setPen(QPen(color, 2)); painter.setBrush(Qt::NoBrush);
      painter.drawEllipse(target, 14 + 18 * pulse, 14 + 18 * pulse);
    }
  }
private:
  QList<Fusion::TrashIcon> icons;
  QPointF target;
  QColor accent;
  QVariantAnimation animation;
  qreal progress = 0;
};
}
void Fusion::animateTrash(QWidget *window, const QList<TrashIcon> &icons, const QPointF &destination) {
  if (window && window->isVisible() && !icons.isEmpty()) new TrashFlight(window, icons, destination);
}
