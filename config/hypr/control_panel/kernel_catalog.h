#pragma once
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QtWidgets>

class KernelCatalog : public QDialog {
public:
    explicit KernelCatalog(const QString &helper, QWidget *parent = nullptr) : QDialog(parent) {
        setWindowTitle(tr("Install Kernel")); resize(960, 600);
        auto *layout = new QVBoxLayout(this);
        auto *intro = new QLabel(tr("All kernels in your configured Arch, Manjaro or CachyOS repositories. "
                                   "Repository installs include matching headers when available. "
                                   "AUR and source builds are listed separately."), this);
        intro->setWordWrap(true); layout->addWidget(intro);
        search = new QLineEdit(this); search->setObjectName("kernelSearch");
        search->setPlaceholderText(tr("Search kernels, versions, repositories or descriptions…"));
        search->setClearButtonEnabled(true); layout->addWidget(search);
        table = new QTreeWidget(this); table->setObjectName("kernelCatalog");
        table->setColumnCount(5);
        table->setHeaderLabels({tr("Kernel"), tr("Available version"), tr("Repository / source"), tr("Installed"), tr("Description")});
        table->setRootIsDecorated(false); table->setAlternatingRowColors(true);
        table->setSelectionMode(QAbstractItemView::SingleSelection); table->setUniformRowHeights(true);
        for (int i = 0; i < 4; ++i) table->header()->setSectionResizeMode(i, QHeaderView::ResizeToContents);
        table->header()->setSectionResizeMode(4, QHeaderView::Stretch);
        layout->addWidget(table, 1);
        status = new QLabel(tr("Reading configured repositories…"), this); status->setWordWrap(true); layout->addWidget(status);
        auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel, this);
        install = buttons->addButton(tr("Install selected"), QDialogButtonBox::AcceptRole);
        install->setEnabled(false); layout->addWidget(buttons);
        connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
        connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
        connect(search, &QLineEdit::textChanged, this, [this] { filter(); });
        connect(table, &QTreeWidget::currentItemChanged, this, [this] { updateInstall(); });
        process = new QProcess(this);
        connect(process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus) {
            QJsonParseError error;
            const auto data = QJsonDocument::fromJson(process->readAllStandardOutput(), &error).object();
            if (code || error.error != QJsonParseError::NoError) {
                status->setText(tr("Could not read the kernel catalogue. ") + QString::fromUtf8(process->readAllStandardError()).trimmed());
                return;
            }
            populate(data);
        });
        connect(process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
            if (error == QProcess::FailedToStart) status->setText(tr("Could not start the kernel catalogue reader."));
        });
        process->start("python3", {helper, "catalog"});
        search->setFocus();
    }
    ~KernelCatalog() override {
        if (process->state() != QProcess::NotRunning) { process->kill(); process->waitForFinished(1000); }
    }
    QJsonObject selection() const {
        auto *item = table->currentItem();
        return item && !item->isHidden() ? item->data(0, Qt::UserRole).toJsonObject() : QJsonObject();
    }
    void populate(const QJsonObject &data) {
        table->clear();
        QSet<QString> names;
        auto add = [&](const QJsonObject &row) {
            auto *item = new QTreeWidgetItem(table, {row["package"].toString(), row["version"].toString(),
                row["repo"].toString(), row["installed"].toString(), row["description"].toString()});
            item->setData(0, Qt::UserRole, row); item->setToolTip(4, row["description"].toString());
        };
        for (const auto &entry : data["kernels"].toArray()) {
            const auto row = entry.toObject(); names.insert(row["package"].toString()); add(row);
        }
        // Optional community choices remain available without claiming they
        // belong to a repository that is not configured on this machine.
        for (const QString &name : {"linux-xanmod", "linux-mainline", "linux-tkg"}) {
            if (names.contains(name)) continue;
            const bool source = name == "linux-tkg";
            add({{"package", name}, {"method", source ? "tkg" : "aur"}, {"repo", source ? "GitHub · source build" : "AUR · community build"},
                 {"description", source ? "Interactive TKG build" : "Requires yay or paru; review the package build before installing"}});
        }
        QStringList missing;
        for (const auto &value : data["missing_repositories"].toArray()) missing << value.toString();
        note = missing.isEmpty() ? tr("From local repository databases. Install performs a full system upgrade with pacman.")
            : tr("Repository databases unavailable: %1. Run a full system update, then reopen this list.").arg(missing.join(", "));
        filter();
    }
    static QString installCommand(const QJsonObject &row) {
        const auto pkg = row["package"].toString(), method = row["method"].toString();
        const QRegularExpression safe("^[a-zA-Z0-9][a-zA-Z0-9@._+\\-]*$");
        if (!safe.match(pkg).hasMatch()) return {};
        if (method == "pacman") {
            const auto repo = row["repo"].toString(), headers = row["headers"].toString();
            if (!safe.match(repo).hasMatch() || (!headers.isEmpty() && !safe.match(headers).hasMatch())) return {};
            return "sudo pacman -Syu --needed -- '" + repo + "/" + pkg + "'" +
                (headers.isEmpty() ? QString() : " '" + repo + "/" + headers + "'");
        }
        if (method == "aur" && (pkg == "linux-xanmod" || pkg == "linux-mainline"))
            return QString("if command -v yay >/dev/null; then yay -S -- '%1' '%1-headers'; "
                           "elif command -v paru >/dev/null; then paru -S -- '%1' '%1-headers'; "
                           "else echo 'Install yay or paru first.'; false; fi").arg(pkg);
        if (method == "tkg" && pkg == "linux-tkg")
            return "kernel_build_dir=\"$HOME/.cache/cachyostools/linux-tkg\"; "
                   "if [ -d \"$kernel_build_dir/.git\" ]; then git -C \"$kernel_build_dir\" pull --ff-only; "
                   "else git clone https://github.com/Frogging-Family/linux-tkg.git \"$kernel_build_dir\"; fi && "
                   "cd \"$kernel_build_dir\" && makepkg -si";
        return {};
    }
private:
    QLineEdit *search;
    QTreeWidget *table;
    QLabel *status;
    QPushButton *install;
    QProcess *process;
    QString note;
    void updateInstall() { install->setEnabled(!installCommand(selection()).isEmpty()); }
    void filter() {
        const auto words = search->text().simplified().split(' ', Qt::SkipEmptyParts);
        int visible = 0;
        for (int i = 0; i < table->topLevelItemCount(); ++i) {
            auto *item = table->topLevelItem(i);
            QString text;
            for (int column = 0; column < table->columnCount(); ++column) text += item->text(column) + ' ';
            bool matches = true;
            for (const auto &word : words) if (!text.contains(word, Qt::CaseInsensitive)) matches = false;
            item->setHidden(!matches); visible += matches;
        }
        status->setText(tr("%1 kernels · %2").arg(visible).arg(note)); updateInstall();
    }
};
