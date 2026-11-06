#pragma once
#include <QFile>
#include <QTimer>
#include <functional>

namespace TerminalExit {
inline QByteArray identity(qint64 pid) {
    QFile file("/proc/" + QString::number(pid) + "/stat");
    if (!file.open(QIODevice::ReadOnly)) return {};
    const auto stat = file.readAll();
    const auto fields = stat.mid(stat.lastIndexOf(')') + 2).split(' ');
    if (fields.size() < 20 || fields[0] == "Z" || fields[0] == "X") return {};
    return fields[19]; // Process start time: also detects reuse of the PID.
}

// Observe detached terminals without owning/killing them when the panel closes.
inline void watch(QObject *context, qint64 pid, std::function<void()> closed) {
    const auto started = identity(pid);
    if (started.isEmpty()) {
        QTimer::singleShot(0, context, closed);
        return;
    }
    auto *timer = new QTimer(context);
    QObject::connect(timer, &QTimer::timeout, context, [timer, pid, started, closed] {
        if (identity(pid) == started) return;
        timer->stop();
        timer->deleteLater();
        closed();
    });
    timer->start(250);
}
} // namespace TerminalExit
