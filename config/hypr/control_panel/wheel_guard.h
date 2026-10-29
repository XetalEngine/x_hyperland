#pragma once
#include <QAbstractScrollArea>
#include <QAbstractSlider>
#include <QAbstractSpinBox>
#include <QApplication>
#include <QComboBox>
#include <QLineEdit>
#include <QScrollBar>
#include <QWheelEvent>

// Installed only in Hyper Fusion Control Panel, including its child dialogs.
class SettingsWheelGuard final : public QObject {
  bool forwarding = false;
  static QWidget *protectedControl(QWidget *widget) {
    while (widget) {
      if (qobject_cast<QAbstractScrollArea *>(widget) ||
          qobject_cast<QScrollBar *>(widget))
        return nullptr;
      if (qobject_cast<QAbstractSlider *>(widget) ||
          qobject_cast<QAbstractSpinBox *>(widget) ||
          qobject_cast<QComboBox *>(widget) || qobject_cast<QLineEdit *>(widget))
        return widget;
      if (widget->isWindow()) break;
      widget = widget->parentWidget();
    }
    return nullptr;
  }
protected:
  bool eventFilter(QObject *object, QEvent *event) override {
    if (event->type() != QEvent::Wheel || forwarding) return false;
    auto *control = protectedControl(qobject_cast<QWidget *>(object));
    if (!control) return false;
    auto *wheel = static_cast<QWheelEvent *>(event);
    forwarding = true;
    for (auto *parent = control->parentWidget(); parent; parent = parent->parentWidget()) {
      if (auto *area = qobject_cast<QAbstractScrollArea *>(parent)) {
        auto *viewport = area->viewport();
        QWheelEvent forwarded(viewport->mapFromGlobal(wheel->globalPosition().toPoint()),
                              wheel->globalPosition(), wheel->pixelDelta(), wheel->angleDelta(),
                              wheel->buttons(), wheel->modifiers(), wheel->phase(),
                              wheel->inverted(), wheel->source());
        forwarded.ignore();
        QApplication::sendEvent(viewport, &forwarded);
        if (forwarded.isAccepted()) break;
      }
      if (parent->isWindow()) break;
    }
    forwarding = false;
    event->accept();
    return true;
  }
public:
  explicit SettingsWheelGuard(QApplication *app) : QObject(app) {
    app->installEventFilter(this);
  }
};
