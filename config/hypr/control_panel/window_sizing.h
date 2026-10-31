#pragma once
#include <QApplication>
#include <QColorDialog>
#include <QDialog>
#include <QFileDialog>
#include <QFontDialog>
#include <QInputDialog>
#include <QMessageBox>
#include <QPointer>
#include <QProgressDialog>
#include <QScreen>
#include <QTimer>

namespace HyperPanel {
inline QSize defaultWindowSize(const QSize &available) {
    return QSize(1650, 910).boundedTo((available - QSize(24, 48)).expandedTo(QSize(1, 1)));
}
// Tool dialogs share the panel's starting size; prompts retain their content size.
class WindowSizing final : public QObject {
public:
    explicit WindowSizing(QObject *parent) : QObject(parent) {}
    bool eventFilter(QObject *object, QEvent *event) override {
        auto *dialog = qobject_cast<QDialog *>(object);
        if (event->type() != QEvent::Show || !dialog || dialog->property("xetalWindowSized").toBool()) return false;
        dialog->setProperty("xetalWindowSized", true);
        if (qobject_cast<QMessageBox *>(dialog) || qobject_cast<QInputDialog *>(dialog) ||
            qobject_cast<QProgressDialog *>(dialog) || qobject_cast<QColorDialog *>(dialog) ||
            qobject_cast<QFontDialog *>(dialog) || dialog->minimumSize() == dialog->maximumSize()) return false;
        QPointer<QDialog> guarded(dialog);
        QTimer::singleShot(0, dialog, [guarded] {
            if (!guarded || !guarded->screen()) return;
            const auto bounds = guarded->screen()->availableGeometry();
            guarded->resize(defaultWindowSize(bounds.size()).expandedTo(guarded->minimumSize()));
            guarded->move(bounds.center() - guarded->rect().center());
        });
        return false;
    }
};
}
