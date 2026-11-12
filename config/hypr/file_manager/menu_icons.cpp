#include "menu_icons.h"
#include "core.h"
#include <QApplication>
#include <QBuffer>
#include <QFile>
#include <QIconEngine>
#include <QImageReader>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPainter>
#include <QPalette>

namespace {
class MenuIcon : public QIconEngine {
public:
  explicit MenuIcon(const QString &body) : body(body) {}
  QIconEngine *clone() const override { return new MenuIcon(body); }
  void paint(QPainter *painter, const QRect &rect, QIcon::Mode mode, QIcon::State) override {
    const auto palette = qApp->palette();
    QColor color = qApp->property("fusionAccent").value<QColor>();
    if (!color.isValid()) color = palette.color(QPalette::WindowText);
    if (mode == QIcon::Selected || mode == QIcon::Active)
      color = palette.color(QPalette::HighlightedText);
    else if (mode == QIcon::Disabled)
      color = palette.color(QPalette::Disabled, QPalette::WindowText);
    auto svg = QString("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%1' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'>%2</svg>")
        .arg(color.name(), body).toUtf8();
    // Use the SVG image plugin already shipped for the desktop's icon themes.
    QBuffer buffer(&svg); buffer.open(QIODevice::ReadOnly);
    QImageReader reader(&buffer, "svg");
    reader.setScaledSize(rect.size() * painter->device()->devicePixelRatioF());
    painter->drawImage(rect, reader.read());
  }
  QPixmap pixmap(const QSize &size, QIcon::Mode mode, QIcon::State state) override {
    return scaledPixmap(size, mode, state, 1);
  }
  QPixmap scaledPixmap(const QSize &size, QIcon::Mode mode, QIcon::State state, qreal scale) override {
    QPixmap result(size * scale);
    result.setDevicePixelRatio(scale); result.fill(Qt::transparent);
    QPainter painter(&result); paint(&painter, QRect(QPoint(), size), mode, state);
    return result;
  }
private:
  QString body;
};
}

QIcon Fusion::menuIcon(const QString &name) {
  static const QJsonObject symbols = [] {
    QFile file(Fusion::root()+"/theme/menu_icons.json");
    return file.open(QIODevice::ReadOnly) ? QJsonDocument::fromJson(file.readAll()).object() : QJsonObject{};
  }();
  const auto body = symbols.value(name).toString();
  if (!body.isEmpty()) return QIcon(new MenuIcon(body));
  const auto original = Fusion::icon(name);
  if (!original.isNull()) return original;
  const auto fallback = symbols.value("application-x-executable").toString();
  return fallback.isEmpty() ? original : QIcon(new MenuIcon(fallback));
}
