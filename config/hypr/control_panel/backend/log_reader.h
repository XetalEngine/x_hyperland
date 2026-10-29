#pragma once
#include <QByteArray>
#include <QRegularExpression>
#include <QStringList>

namespace LogReader {
struct Command {
    QString program;
    QStringList arguments;
    bool follow = false;
};

inline bool accountingFile(const QString &path) {
    return path == "/var/log/wtmp" || path == "/var/log/btmp" || path == "/var/log/lastlog";
}

inline Command command(const QString &source, int count, bool follow, int boot = 1) {
    const QString lines = QString::number(qBound(1, count, 100000));
    if (source == "inxi" || source.startsWith("inxi ")) {
        auto args = source.split(' ', Qt::SkipEmptyParts);
        args.removeFirst();
        args << "-c" << "0";
        return {"inxi", args, false};
    }
    if (source == "/var/log/wtmp" || source == "/var/log/btmp")
        return {source.endsWith("btmp") ? "lastb" : "last", {"-w", "-n", lines, "-f", source}, false};
    if (source == "/var/log/lastlog") return {"lastlog", {}, false};
    if (source.startsWith("/var/log/journal")) {
        QStringList args{"--no-pager", "--output=short-iso", "-n", lines};
        if (boot <= 0) args << "-b" << QString::number(boot);
        if (follow) args << "-f";
        return {"journalctl", args, follow};
    }
    QStringList args{"-n", lines};
    if (follow) args << "-F";
    args << "--" << source;
    return {"tail", args, follow};
}

inline QString plain(QString text) {
    // OSC (including hyperlinks), ANSI CSI, then IRC formatting used by inxi
    // when it detects a pipe instead of a terminal. Retain whitespace/layout.
    static const QRegularExpression osc(QStringLiteral("\x1b\\][^\x07\x1b]*(?:\x07|\x1b\\\\)"));
    static const QRegularExpression csi(QStringLiteral("\x1b\\[[0-?]*[ -/]*[@-~]"));
    static const QRegularExpression irc(QStringLiteral("\x03[0-9]{0,2}(?:,[0-9]{1,2})?"));
    static const QRegularExpression controls(QStringLiteral("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"));
    text.replace(osc, "");
    text.replace(csi, "");
    text.replace(irc, "");
    text.replace("\r\n", "\n");
    text.replace('\r', '\n');
    text.remove(controls);
    return text;
}

// Decode only complete lines, so split UTF-8 characters and escape sequences
// survive arbitrary QProcess reads. Also bound pathological no-newline output.
class Stream {
    QByteArray pending;
    QString filter;
public:
    explicit Stream(const QString &filter = {}) : filter(filter) {}
    QString take(const QByteArray &bytes, bool final = false) {
        pending += bytes;
        const int end = final ? pending.size() : pending.lastIndexOf('\n') + 1;
        if (end == 0 && pending.size() < 1024 * 1024) return {};
        auto text = plain(QString::fromUtf8(pending.left(end == 0 ? pending.size() : end)));
        pending.remove(0, end == 0 ? pending.size() : end);
        if (filter.isEmpty()) return text;
        QString result;
        const auto lines = text.split('\n');
        for (int i = 0; i < lines.size(); ++i)
            if (lines[i].contains(filter, Qt::CaseInsensitive))
                result += lines[i] + (i < lines.size() - 1 ? "\n" : "");
        return result;
    }
};
} // namespace LogReader
