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
  explicit MenuIcon(const QString &body, bool accent = true) : body(body), accent(accent) {}
  QIconEngine *clone() const override { return new MenuIcon(body, accent); }
  void paint(QPainter *painter, const QRect &rect, QIcon::Mode mode, QIcon::State state) override {
    const auto palette = qApp->palette();
    QColor color = accent ? qApp->property("fusionAccent").value<QColor>() : palette.color(QPalette::WindowText);
    if (!color.isValid()) color = palette.color(QPalette::WindowText);
    if (mode == QIcon::Selected || mode == QIcon::Active || (!accent && state == QIcon::On))
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
  bool accent;
};
QIcon symbol(const QString &name, bool accent) {
  static const QJsonObject symbols = [] {
    QFile file(Fusion::root()+"/theme/menu_icons.json");
    return file.open(QIODevice::ReadOnly) ? QJsonDocument::fromJson(file.readAll()).object() : QJsonObject{};
  }();
  const auto body = symbols.value(name).toString();
  if (!body.isEmpty()) return QIcon(new MenuIcon(body, accent));
  const auto original = Fusion::icon(name);
  if (!original.isNull()) return original;
  const auto fallback = symbols.value("application-x-executable").toString();
  return fallback.isEmpty() ? original : QIcon(new MenuIcon(fallback, accent));
}
}
QIcon Fusion::menuIcon(const QString &name) { return symbol(name, true); }
QIcon Fusion::symbolicIcon(const QString &name) { return symbol(name, false); }
