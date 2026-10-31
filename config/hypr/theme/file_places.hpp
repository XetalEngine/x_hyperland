#pragma once
#include <QFileDialog>
#include <QFileInfo>
#include <QStyle>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QListView>
#include <QMessageBox>
#include <QProcess>
#include <QScrollBar>
#include <QSplitter>
#include <QTimer>
#include <QTreeWidget>

namespace XetalPlaces {
inline QString helper() {
    return QFileInfo(qEnvironmentVariable("XETAL_THEME_CONFIG")).absolutePath() + "/places.py";
}
class Sidebar final : public QTreeWidget {
    QFileDialog *dialog;
    QProcess listing, opening;
    QTimer refresh;
    QByteArray previous;
    void load() {
        if (dialog->isVisible() && listing.state() == QProcess::NotRunning)
            listing.start("python3", {helper()});
    }
    void populate(const QByteArray &bytes) {
        const auto document = QJsonDocument::fromJson(bytes);
        if (!document.isArray() || bytes == previous) return;
        previous = bytes;
        const auto selected = currentItem() ? currentItem()->data(0, Qt::UserRole).toMap() : QVariantMap();
        const int scroll = verticalScrollBar()->value();
        clear();
        const auto entries = document.array();
        QStringList groups;
        for (const auto value : entries) {
            const auto group = value.toObject()["group"].toString();
            if (!groups.contains(group)) groups << group;
        }
        for (const auto &group : groups) {
            auto *heading = new QTreeWidgetItem(this, {group});
            heading->setFlags(Qt::NoItemFlags);
            auto font = heading->font(0); font.setBold(true); heading->setFont(0, font);
            for (const auto value : entries) {
                const auto entry = value.toObject();
                if (entry["group"].toString() != group) continue;
                auto *item = new QTreeWidgetItem(this, {entry["name"].toString()});
                const auto data = entry.toVariantMap();
                item->setData(0, Qt::UserRole, data);
                item->setIcon(0, QIcon::fromTheme(entry["icon"].toString(), dialog->style()->standardIcon(QStyle::SP_DirIcon)));
                const auto url = entry["url"].toString();
                item->setToolTip(0, url.isEmpty() ? tr("Click to unlock or mount %1").arg(entry["device"].toString()) : url);
                if (data == selected) setCurrentItem(item);
            }
        }
        verticalScrollBar()->setValue(scroll);
    }
    void activate(QTreeWidgetItem *item) {
        const auto data = item->data(0, Qt::UserRole).toMap();
        if (data.isEmpty() || opening.state() != QProcess::NotRunning) return;
        const QUrl url(data.value("url").toString());
        if (url.isLocalFile()) { dialog->setDirectoryUrl(url); return; }
        const auto device = data.value("device").toString();
        setEnabled(false);
        opening.start("python3", {helper(), device.isEmpty() ? "--open" : "--device", device.isEmpty() ? url.toString() : device});
    }
public:
    explicit Sidebar(QFileDialog *parent) : QTreeWidget(parent), dialog(parent) {
        setObjectName("xetalPlacesSidebar"); setHeaderHidden(true); setRootIsDecorated(false);
        setIndentation(0); setUniformRowHeights(true); setIconSize(QSize(22,22));
        setMinimumWidth(200); setMaximumWidth(320);
        setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        setSelectionMode(QAbstractItemView::SingleSelection); setEditTriggers(QAbstractItemView::NoEditTriggers);
        setStyleSheet("QTreeWidget#xetalPlacesSidebar::item { min-height:28px; padding:3px 6px; }");
        connect(this, &QTreeWidget::itemClicked, this, [this](QTreeWidgetItem *item, int) { activate(item); });
        connect(this, &QTreeWidget::itemActivated, this, [this](QTreeWidgetItem *item, int) { activate(item); });
        connect(&listing, qOverload<int,QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus) {
            const auto bytes = listing.readAllStandardOutput();
            if (!code) populate(bytes);
        });
        connect(&opening, qOverload<int,QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus) {
            setEnabled(true);
            const auto result = QJsonDocument::fromJson(opening.readAllStandardOutput()).object();
            if (!dialog->isVisible()) return;
            if (code || result.contains("error") || result.isEmpty()) {
                QMessageBox::warning(dialog, tr("Could not open location"), result.value("error").toString(tr("The location helper could not complete. Try again.")));
            } else if (result.contains("dolphin")) {
                const auto script = QFileInfo(helper()).absolutePath() + "/../scripts/dolphin.sh";
                QProcess::startDetached(script, {result["dolphin"].toString()});
            } else if (!result["path"].toString().isEmpty()) dialog->setDirectory(result["path"].toString());
            else dialog->setDirectoryUrl(QUrl(result["url"].toString()));
            load();
        });
        connect(&opening, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
            setEnabled(true);
            if (error == QProcess::FailedToStart) QMessageBox::warning(dialog, tr("Could not open location"), opening.errorString());
        });
        connect(dialog, &QFileDialog::finished, this, [this] { opening.kill(); listing.kill(); });
        refresh.setInterval(4000); connect(&refresh, &QTimer::timeout, this, [this] { load(); }); refresh.start();
        QTimer::singleShot(0, this, [this] { load(); });
    }
    ~Sidebar() override { listing.kill(); listing.waitForFinished(1000); opening.kill(); opening.waitForFinished(1000); }
};
inline void attach(QFileDialog *dialog) {
    if (dialog->property("xetalFilePlaces").toBool() || !QFileInfo::exists(helper())) return;
    auto *old = dialog->findChild<QListView *>("sidebar");
    auto *splitter = old ? qobject_cast<QSplitter *>(old->parentWidget()) : nullptr;
    if (!splitter) return;
    dialog->setProperty("xetalFilePlaces", true);
    auto *places = new Sidebar(dialog);
    splitter->insertWidget(0, places); old->hide();
    splitter->setCollapsible(0, false); splitter->setStretchFactor(0, 0);
    splitter->setSizes({230,0,600});
}
}
