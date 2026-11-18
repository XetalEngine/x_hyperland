#pragma once
#include <QList>
#include <QRegularExpression>
#include <QString>

namespace AurSearch {
struct Package {
    QString name, version, repository, votes, description;
    bool installed = false;
    QString target() const { return repository + '/' + name; }
};

inline QList<Package> parse(QString output) {
    output.remove(QRegularExpression("\x1b\\[[0-9;]*[A-Za-z]"));
    const QRegularExpression header("^([A-Za-z0-9_@.+-]+)/([A-Za-z0-9_@+][A-Za-z0-9_@.+-]*)\\s+(\\S+)(.*)$");
    const QRegularExpression votes("\\((?:Votes:\\s*)?([+]?\\d+)(?:[\\s,]|\\))");
    const QRegularExpression installed("(?:\\[|\\()installed(?:\\s|:|\\]|\\))", QRegularExpression::CaseInsensitiveOption);
    QList<Package> result;
    for (const auto &line : output.split('\n')) {
        const auto match = header.match(line);
        if (match.hasMatch()) {
            const auto extra = match.captured(4);
            auto count = votes.match(extra).captured(1); count.remove('+');
            // Repository packages show download/installed sizes here, not votes.
            if (match.captured(1) != "aur") count.clear();
            result.append({match.captured(2), match.captured(3), match.captured(1), count, {}, installed.match(extra).hasMatch()});
        } else if (!result.isEmpty() && !line.isEmpty() && line.front().isSpace()) {
            if (!result.last().description.isEmpty()) result.last().description += ' ';
            result.last().description += line.trimmed();
        }
    }
    return result;
}

// Field: 0 = name or description, 1 = name, 2 = description.
inline bool matches(const Package &package, const QString &query, int field, bool exact) {
    const auto match = [&](const QString &text) {
        return exact ? text.compare(query, Qt::CaseInsensitive) == 0 : text.contains(query, Qt::CaseInsensitive);
    };
    return (field != 2 && match(package.name)) || (field != 1 && match(package.description));
}
}
