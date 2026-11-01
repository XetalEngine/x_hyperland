// Shared QFileDialog previews for external Qt 5/6 applications in this session.
#pragma once
#include <QApplication>
#include <QStyle>
#include "file_places.hpp"
#include <QDateTime>
#include <QDirIterator>
#include <QFileDialog>
#include <QFileInfo>
#include <QFutureWatcher>
#include <QGridLayout>
#include <QImageReader>
#include <QLabel>
#include <QLineEdit>
#include <QMimeDatabase>
#include <QPlainTextEdit>
#include <QScreen>
#include <QScrollArea>
#include <QTimer>
#include <QVBoxLayout>
#include <QtConcurrent/QtConcurrentRun>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace XetalPreview {
constexpr auto marker = "xetalFilePreview";
struct Data {
    QString name, message, text;
    QString type = "File", dimensions = "—", size = "—", modified = "—", created = "—";
    QImage image;
};
inline QString date(const QDateTime &value) {
    return value.isValid() ? value.toLocalTime().toString("MMM dd, yyyy · HH:mm") : "Not recorded";
}
inline Data inspect(const QString &path) {
    Data result;
    if (path.isEmpty()) { result.message = "Select a file or folder"; return result; }
    QFileInfo info(path); result.name = info.fileName();
    if (!info.exists()) { result.message = "New file · no preview yet"; return result; }
    result.modified = date(info.lastModified()); result.created = date(info.birthTime());
    if (info.isDir()) {
        result.type = "Folder";
        QDirIterator items(path, QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden);
        QStringList entries;
        while (items.hasNext() && entries.size() < 40) {
            items.next(); entries << items.fileName() + (items.fileInfo().isDir() ? "/" : "");
        }
        entries.sort(Qt::CaseInsensitive); result.text = entries.join('\n');
        result.message = items.hasNext() ? "First 40 entries" : entries.isEmpty() ? "Empty folder" : "Folder contents";
        return result;
    }
    if (!info.isFile()) { result.message = "No preview for this device or special file"; return result; }
    const int fd = ::open(QFile::encodeName(path).constData(), O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) { result.message = "This file could not be read."; return result; }
    struct stat status{};
    if (::fstat(fd, &status) || !S_ISREG(status.st_mode)) {
        ::close(fd); result.message = "Preview unavailable"; return result;
    }
    QFile file;
    if (!file.open(fd, QIODevice::ReadOnly, QFileDevice::AutoCloseHandle)) {
        ::close(fd); result.message = "This file could not be read."; return result;
    }
    result.size = QLocale().formattedDataSize(status.st_size);
    result.type = QMimeDatabase().mimeTypeForFile(path, QMimeDatabase::MatchExtension).comment();
    QImageReader reader(&file); reader.setAutoTransform(true);
    if (reader.canRead()) {
        const auto size = reader.size();
        result.dimensions = QString("%1 × %2 px").arg(size.width()).arg(size.height());
        result.type = QString::fromLatin1(reader.format()).toUpper();
        if (!size.isValid() || qint64(size.width()) * size.height() > 48000000 || status.st_size > 128*1024*1024) {
            result.message = "Image too large to preview"; return result;
        }
        reader.setScaledSize(size.scaled(480, 340, Qt::KeepAspectRatio)); result.image = reader.read();
        if (result.image.isNull()) result.message = "Image preview unavailable";
        return result;
    }
    file.seek(0); const auto bytes = file.read(65536);
    const auto text = QString::fromUtf8(bytes);
    bool binary = text.contains(QChar::ReplacementCharacter);
    for (auto c : text) if (c.unicode() < 32 && c != '\n' && c != '\r' && c != '\t') binary = true;
    if (binary) result.message = "No preview available for this file type";
    else {
        result.text = text;
        result.message = status.st_size > bytes.size() ? "First 64 KiB" : bytes.isEmpty() ? "Empty file" : "";
    }
    return result;
}

class Pane final : public QScrollArea {
    QLabel *preview, *name;
    QPlainTextEdit *excerpt;
    QList<QLabel *> values;
    QTimer timer;
    QFutureWatcher<Data> worker;
    QString latest;
    quint64 generation = 0, running = 0;
    QImage image;
    void start() {
        if (worker.isRunning()) return;
        running = generation;
        const auto path = latest;
        worker.setFuture(QtConcurrent::run([path] { return inspect(path); }));
    }
    void renderImage() {
        if (!image.isNull()) preview->setPixmap(QPixmap::fromImage(image).scaled(
            qMax(1, viewport()->width()-32), 200, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    }
protected:
    void resizeEvent(QResizeEvent *event) override { QScrollArea::resizeEvent(event); renderImage(); }
public:
    explicit Pane(QWidget *parent) : QScrollArea(parent) {
        setObjectName("xetalFilePreviewPane"); setWidgetResizable(true);
        setMinimumWidth(240); setMaximumWidth(300); setFrameShape(QFrame::StyledPanel);
        setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        auto content = new QWidget; auto layout = new QVBoxLayout(content);
        layout->setContentsMargins(12,12,12,12); layout->setSpacing(10); setWidget(content);
        auto title = new QLabel("PREVIEW"); title->setObjectName("eyebrow"); layout->addWidget(title);
        preview = new QLabel("Select a file or folder"); preview->setObjectName("xetalPreviewImage");
        preview->setAlignment(Qt::AlignCenter); preview->setWordWrap(true);
        preview->setMinimumHeight(160); preview->setMaximumHeight(210);
        preview->setStyleSheet("background:palette(base); border-radius:8px; padding:4px;"); layout->addWidget(preview);
        name = new QLabel; name->setObjectName("xetalPreviewName"); name->setWordWrap(true);
        name->setTextFormat(Qt::PlainText); name->setTextInteractionFlags(Qt::TextSelectableByMouse); layout->addWidget(name);
        excerpt = new QPlainTextEdit; excerpt->setObjectName("xetalPreviewText"); excerpt->setReadOnly(true);
        excerpt->setMinimumHeight(160); excerpt->setMaximumHeight(220); excerpt->hide(); layout->addWidget(excerpt);
        for (auto caption : {"Type", "Dimensions", "Size", "Modified", "Created"}) {
            auto label = new QLabel(caption); label->setObjectName("muted"); layout->addWidget(label);
            auto value = new QLabel("—"); value->setWordWrap(true); value->setTextFormat(Qt::PlainText);
            value->setTextInteractionFlags(Qt::TextSelectableByMouse); layout->addWidget(value); values << value;
        }
        layout->addStretch(); timer.setSingleShot(true); timer.setInterval(100);
        connect(&timer, &QTimer::timeout, this, [this] { start(); });
        connect(&worker, &QFutureWatcher<Data>::finished, this, [this] {
            if (running != generation) { if (!latest.isEmpty()) timer.start(); return; }
            const auto data = worker.result(); name->setText(data.name); image = data.image;
            preview->setText(data.message); renderImage(); excerpt->setPlainText(data.text); excerpt->setVisible(!data.text.isEmpty());
            const QStringList fields{data.type, data.dimensions, data.size, data.modified, data.created};
            for (int i = 0; i < fields.size(); ++i) values[i]->setText(fields[i]);
        });
        if (auto *dialog = qobject_cast<QFileDialog *>(parent)) {
            connect(dialog, &QFileDialog::currentChanged, this, [this](const QString &path) { select(path); });
            connect(dialog, &QFileDialog::directoryEntered, this, [this](const QString &path) { select(path); });
            connect(dialog, &QFileDialog::finished, this, [this] { ++generation; latest.clear(); timer.stop(); });
            if (auto edit = dialog->findChild<QLineEdit *>("fileNameEdit"))
                connect(edit, &QLineEdit::textEdited, this, [this, dialog] { select(dialog->selectedFiles().value(0)); });
            select(dialog->selectedFiles().value(0));
        } else select({});
    }
    void select(const QString &path) {
        latest = path; ++generation; image = QImage(); preview->clear();
        preview->setText(path.isEmpty() ? "Select a file or folder" : "Loading preview…");
        name->setText(QFileInfo(path).fileName()); excerpt->hide();
        for (auto value : values) value->setText("—");
        timer.start();
    }
};
inline void attach(QFileDialog *dialog) {
    XetalPlaces::attach(dialog);
    if (dialog->property(marker).toBool()) return;
    auto grid = qobject_cast<QGridLayout *>(dialog->layout()); if (!grid) return;
    dialog->setProperty(marker, true);
    auto pane = new Pane(dialog); grid->addWidget(pane, 0, grid->columnCount(), grid->rowCount(), 1);
    const auto screen = dialog->screen();
    const auto available = screen ? screen->availableGeometry().size() : QSize(1100,720);
    dialog->resize(qMin(qMax(900, dialog->width()+260), available.width()-32),
                   qMin(qMax(580, dialog->height()), available.height()-32));
}
class Dialogs final : public QObject {
public:
    using QObject::QObject;
    bool eventFilter(QObject *object, QEvent *event) override {
        if (event->type() == QEvent::Show) if (auto dialog = qobject_cast<QFileDialog *>(object)) attach(dialog);
        return false;
    }
};
inline void install() {
    auto app = qobject_cast<QApplication *>(QCoreApplication::instance());
    if (!app || app->property("xetalNativeFilePreviews").toBool()) return;
    app->setProperty("xetalNativeFilePreviews", true); app->installEventFilter(new Dialogs(app));
    // A first modal file dialog can already be visible when the startup timer runs.
    for (auto widget : app->topLevelWidgets())
        if (auto dialog = qobject_cast<QFileDialog *>(widget); dialog && dialog->isVisible()) attach(dialog);
}
} // namespace XetalPreview
