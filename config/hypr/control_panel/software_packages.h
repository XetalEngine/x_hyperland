#pragma once
#include <QDateTime>
#include <QLocale>
#include <QRegularExpression>
#include <QStringList>
#include <limits>

namespace SoftwarePackages {
struct Package { QString name, version, description, date; qint64 bytes = 0; };
inline qint64 sizeBytes(const QString &text) {
    const auto parts = text.simplified().split(' ');
    if (parts.isEmpty()) return 0;
    bool ok = false; const double value = parts.first().toDouble(&ok);
    if (!ok || value < 0) return 0;
    const auto units = QStringList{"B", "KiB", "MiB", "GiB", "TiB"};
    int index = units.indexOf(parts.value(1, "B")); if (index < 0) return 0;
    double bytes = value; while (index--) bytes *= 1024.;
    return bytes <= double(std::numeric_limits<qint64>::max()) ? qint64(bytes) : 0;
}
inline QString sizeText(qint64 bytes) {
    static const QStringList units{"B", "KiB", "MiB", "GiB", "TiB"};
    double value = bytes; int at = 0;
    while (value >= 1024. && at < units.size() - 1) { value /= 1024.; ++at; }
    return QString::number(value, 'f', at ? 1 : 0) + ' ' + units[at];
}
inline QList<Package> parse(const QString &text) {
    QList<Package> packages; Package current; QString previous;
    const auto flush = [&] {
        if (QRegularExpression("^[A-Za-z0-9_@+][A-Za-z0-9_@.+-]*$").match(current.name).hasMatch()) packages.append(current);
        current = {}; previous.clear();
    };
    for (const auto &line : text.split('\n')) {
        if (line.trimmed().isEmpty()) { flush(); continue; }
        if (!line.isEmpty() && line.front().isSpace()) {
            if (previous == "Description") current.description += ' ' + line.trimmed();
            continue;
        }
        const int colon = line.indexOf(':'); if (colon < 0) continue;
        previous = line.left(colon).trimmed(); const auto value = line.mid(colon + 1).trimmed();
        if (previous == "Name") current.name = value;
        else if (previous == "Version") current.version = value;
        else if (previous == "Description") current.description = value;
        else if (previous == "Installed Size") current.bytes = sizeBytes(value);
        else if (previous == "Install Date") current.date = value;
    }
    flush(); return packages;
}
}
