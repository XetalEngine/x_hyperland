// Chimes for Qt 5/6 applications using this private platform theme only.
#pragma once
#include <QApplication>
#include <QEvent>
#include <QFileInfo>
#include <QMessageBox>
#include <QProcess>

namespace XetalSounds {
class Filter final : public QObject {
    QString player;
public:
    Filter(QObject *parent, const QString &root) : QObject(parent), player(root+"/sounds/play.py") {}
    bool eventFilter(QObject *object, QEvent *event) override {
        if (event->type()!=QEvent::Show) return false;
        auto box=qobject_cast<QMessageBox *>(object);
        if (!box) return false;
        QString kind;
        switch (box->icon()) {
            case QMessageBox::Critical: kind="error"; break;
            case QMessageBox::Warning: kind="warning"; break;
            case QMessageBox::Information: kind="info"; break;
            case QMessageBox::Question: kind="question"; break;
            default: return false;
        }
        QProcess::startDetached("python3", {player,kind});
        return false;
    }
};
inline void install(const QString &root) {
    auto app=qobject_cast<QApplication *>(QCoreApplication::instance());
    if (!app || app->property("xetalSoundBridge").toBool() || !QFileInfo::exists(root+"/sounds/play.py")) return;
    app->setProperty("xetalSoundBridge",true);
    app->installEventFilter(new Filter(app,root));
}
}
