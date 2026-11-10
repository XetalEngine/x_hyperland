#pragma once
#include <QtWidgets>
#include <cmath>

class FavoriteButton final : public QAbstractButton {
public:
  explicit FavoriteButton(QWidget *parent) : QAbstractButton(parent) {
    setObjectName("panelFavorite");
    setCheckable(true);
    setFixedSize(34, 34);
    setFocusPolicy(Qt::StrongFocus);
    setCursor(Qt::PointingHandCursor);
    setEnabled(false);
  }

protected:
  void paintEvent(QPaintEvent *) override {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    const auto accent = palette().color(QPalette::Link);
    if (!isEnabled()) painter.setOpacity(.45);
    if (underMouse() || hasFocus() || isChecked()) {
      auto background = accent;
      background.setAlpha(isDown() ? 65 : underMouse() ? 42 : 24);
      painter.setBrush(background);
      painter.setPen(hasFocus() ? QPen(accent, 1.5) : QPen(Qt::NoPen));
      painter.drawRoundedRect(QRectF(rect()).adjusted(1, 1, -1, -1), 7, 7);
    }
    QPainterPath star;
    constexpr double pi = 3.14159265358979323846;
    for (int i = 0; i < 10; ++i) {
      const double angle = -pi/2 + i*pi/5;
      const double radius = i%2 ? 4.2 : 9.4;
      const QPointF point(width()/2.0 + radius*std::cos(angle),
                          height()/2.0 + .8 + radius*std::sin(angle));
      if (!i) star.moveTo(point); else star.lineTo(point);
    }
    star.closeSubpath();
    painter.setPen(QPen(isChecked() || underMouse() || hasFocus() ? accent
                       : palette().color(QPalette::PlaceholderText), 1.5,
                       Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    painter.setBrush(isChecked() ? QBrush(accent) : QBrush(Qt::NoBrush));
    painter.drawPath(star);
  }
};

class ToolButton final : public QPushButton {
  QString title, detail, iconName;
  FavoriteButton *favorite;

public:
  ToolButton(const QJsonObject &data, QWidget *parent)
      : QPushButton(parent), title(data["title"].toString()),
        detail(data["description"].toString()), iconName(data["icon"].toString()),
        favorite(new FavoriteButton(this)) {
    setText(title);
    setAccessibleName(title);
    setToolTip(detail);
    setMinimumHeight(72);
    setCursor(Qt::PointingHandCursor);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setObjectName("panelTool");
    setProperty("toolId", data["id"].toString());
    favorite->setProperty("toolId", data["id"].toString());
    setIcon(QIcon::fromTheme(iconName, style()->standardIcon(QStyle::SP_ComputerIcon)));
    setFavoriteState(false, false, false);
  }
  FavoriteButton *favoriteButton() const { return favorite; }
  void setFavoriteState(bool checked, bool available, bool pending, const QString &error = {}) {
    if (!pending) favorite->setChecked(checked);
    favorite->setEnabled(available && !pending);
    const QString action = favorite->isChecked() ? "Remove %1 from Apps Favorites" : "Add %1 to Apps Favorites";
    favorite->setAccessibleName(action.arg(title));
    favorite->setToolTip(pending ? "Saving to Favorites…" : !error.isEmpty() ? error
                        : !available ? "Loading Favorites…" : action.arg(title));
    favorite->update();
  }

protected:
  bool hitButton(const QPoint &position) const override {
    // A second click while the star is saving must never open the page below it.
    return QPushButton::hitButton(position) && !favorite->geometry().contains(position);
  }
  void resizeEvent(QResizeEvent *event) override {
    QPushButton::resizeEvent(event);
    favorite->move(width() - favorite->width() - 12, (height() - favorite->height())/2);
  }
  void paintEvent(QPaintEvent *) override {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    auto fill = palette().color(QPalette::AlternateBase);
    auto border = palette().color(QPalette::Midlight);
    const bool onStar = favorite->geometry().contains(mapFromGlobal(QCursor::pos()));
    if ((underMouse() && !onStar) || hasFocus() || isDown()) {
      fill = palette().color(QPalette::Highlight);
      border = palette().color(QPalette::Link);
    }
    p.setBrush(fill);
    p.setPen(QPen(border, hasFocus() ? 1.5 : 1));
    const auto corner = qApp->property("xetalPanelCardRadius");
    const auto radius = corner.isValid() ? corner.toInt() : 10;
    p.drawRoundedRect(QRectF(rect()).adjusted(1, 1, -1, -1), radius, radius);
    QIcon::fromTheme(iconName, icon()).paint(&p, QRect(13, 14, 42, 42));
    auto f = font();
    f.setBold(true);
    p.setFont(f);
    p.setPen(palette().color(QPalette::Text));
    const int textWidth = qMax(0, favorite->x() - 12 - 69);
    p.drawText(QRect(69, 12, textWidth, 25), Qt::AlignVCenter,
               p.fontMetrics().elidedText(title, Qt::ElideRight, textWidth));
    f.setBold(false);
    f.setPointSizeF(qMax(8., f.pointSizeF() - 1));
    p.setFont(f);
    p.setPen(palette().color(QPalette::PlaceholderText));
    p.drawText(QRect(69, 38, textWidth, 22), Qt::AlignVCenter,
               p.fontMetrics().elidedText(detail, Qt::ElideRight, textWidth));
  }
};
