
#include <QListWidget>
#include <QPainter>
#include <QFileSystemWatcher>
#include <pwd.h>
#include <unistd.h>
#include "../account_avatar.h"
#include "../native.h"
// Dashboard -> Users & Groups sub-tab: account management the Windows
// lusrmgr.msc way. Group membership is where Arch permission problems live.
// The signed-in account shares Hyper Fusion's profile picture. Other accounts
// use their own account images, without inheriting the current user's theme.

void MainWindow::setupUsersGroupsTab() {
    QVBoxLayout *layout = new QVBoxLayout(ui->usersGroupsSubTab);

    auto *profile = new QHBoxLayout;
    auto *avatar = new FusionAccounts::Avatar(ui->usersGroupsSubTab);
    avatar->setObjectName("usersCurrentAvatar");
    profile->addWidget(avatar);
    auto *identity = new QVBoxLayout;
    auto *name = new QLabel(ui->usersGroupsSubTab);
    name->setObjectName("usersCurrentName"); name->setTextFormat(Qt::PlainText);
    auto font = name->font(); font.setPointSize(font.pointSize()+5); font.setBold(true); name->setFont(font);
    identity->addWidget(name);
    auto *description = new QLabel(ui->usersGroupsSubTab);
    description->setObjectName("usersCurrentDescription"); description->setTextFormat(Qt::PlainText);
    identity->addWidget(description); profile->addLayout(identity); profile->addStretch();
    layout->addLayout(profile);

    QHBoxLayout *bar = new QHBoxLayout();
    QLabel *hint = new QLabel(tr("Local accounts and their group memberships (wheel = sudo)."), ui->usersGroupsSubTab);
    hint->setStyleSheet("color:#888;");
    QPushButton *refreshBtn = new QPushButton(tr("🔄 Refresh"), ui->usersGroupsSubTab);
    QPushButton *addBtn = new QPushButton(tr("➕ Add User"), ui->usersGroupsSubTab);
    QPushButton *delBtn = new QPushButton(tr("🗑️ Delete User"), ui->usersGroupsSubTab);
    QPushButton *passBtn = new QPushButton(tr("🔑 Change Password"), ui->usersGroupsSubTab);
    QPushButton *shellBtn = new QPushButton(tr("🐚 Change Shell"), ui->usersGroupsSubTab);
    QPushButton *groupsBtn = new QPushButton(tr("👥 Edit Groups"), ui->usersGroupsSubTab);
    QPushButton *iconBtn = new QPushButton(tr("🖼️ Change Icon"), ui->usersGroupsSubTab);
    layout->addWidget(hint);
    bar->addStretch();
    for (QPushButton *b : {refreshBtn, addBtn, delBtn, passBtn, shellBtn, groupsBtn, iconBtn}) bar->addWidget(b);
    layout->addLayout(bar);

    ugUsersTable = new QTableWidget(ui->usersGroupsSubTab);
    ugUsersTable->setColumnCount(5);
    ugUsersTable->setHorizontalHeaderLabels(QStringList() << tr("User") << tr("UID") << tr("Home") << tr("Shell") << tr("Groups"));
    ugUsersTable->horizontalHeader()->setStretchLastSection(true);
    for (int column = 0; column < 4; ++column)
        ugUsersTable->horizontalHeader()->setSectionResizeMode(column, QHeaderView::ResizeToContents);
    ugUsersTable->setWordWrap(false);
    ugUsersTable->setIconSize(QSize(48, 48));
    ugUsersTable->verticalHeader()->setDefaultSectionSize(60);
    ugUsersTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    ugUsersTable->setSelectionMode(QAbstractItemView::SingleSelection);
    ugUsersTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    ugUsersTable->setAlternatingRowColors(true);
    ugUsersTable->verticalHeader()->setVisible(false);
    layout->addWidget(ugUsersTable);

    connect(refreshBtn, &QPushButton::clicked, this, &MainWindow::refreshUsersGroups);
    auto *profileWatcher = new QFileSystemWatcher({HyperPanel::root()+"/theme"}, this);
    connect(profileWatcher, &QFileSystemWatcher::directoryChanged, this, [this] {
        if (ui->usersGroupsSubTab->isVisible()) refreshUsersGroups();
    });

    auto selectedUser = [this]() -> QString {
        int row = ugUsersTable->currentRow();
        return (row >= 0 && ugUsersTable->item(row, 0)) ? ugUsersTable->item(row, 0)->text() : QString();
    };

    connect(addBtn, &QPushButton::clicked, this, [this]() {
        bool ok;
        QString name = QInputDialog::getText(this, tr("Add User"), tr("Username (lowercase, no spaces):"),
                                             QLineEdit::Normal, "", &ok).trimmed();
        if (!ok || name.isEmpty()) return;
        if (!QRegularExpression("^[a-z_][a-z0-9_-]*$").match(name).hasMatch()) {
            QMessageBox::warning(this, tr("Invalid Name"), tr("Use lowercase letters, digits, - and _ only."));
            return;
        }
        bool sudoer = QMessageBox::question(this, tr("Sudo Access"),
                          tr("Should '%1' be an administrator (wheel group)?").arg(name)) == QMessageBox::Yes;
        QString cmd = QString("sudo useradd -m %1 '%2' && echo 'Set a password for %2:' && sudo passwd '%2' && "
                              "echo 'User %2 created.'; read -p 'Press Enter...'")
                          .arg(sudoer ? "-G wheel" : "", name);
        runSudoCommandInTerminal(cmd);
    });

    connect(delBtn, &QPushButton::clicked, this, [this, selectedUser]() {
        QString name = selectedUser();
        if (name.isEmpty()) { QMessageBox::information(this, tr("No Selection"), tr("Select a user first.")); return; }
        if (name == qEnvironmentVariable("USER")) {
            QMessageBox::warning(this, tr("Refused"), tr("You cannot delete the account you are logged in with."));
            return;
        }
        if (name == "root") {
            QMessageBox::warning(this, tr("Refused"), tr("Deleting root would be a very short story."));
            return;
        }
        if (QMessageBox::warning(this, tr("Delete User"),
                tr("Delete '%1' AND its home directory? This cannot be undone.").arg(name),
                QMessageBox::Yes | QMessageBox::No) != QMessageBox::Yes) return;
        runSudoCommandInTerminal(QString("sudo userdel -r '%1' && echo 'Deleted %1.' || echo 'Failed (user logged in?)'; read -p 'Press Enter...'").arg(name));
    });

    connect(passBtn, &QPushButton::clicked, this, [this, selectedUser]() {
        QString name = selectedUser();
        if (name.isEmpty()) { QMessageBox::information(this, tr("No Selection"), tr("Select a user first.")); return; }
        runSudoCommandInTerminal(QString("sudo passwd '%1'; read -p 'Press Enter...'").arg(name));
    });

    connect(shellBtn, &QPushButton::clicked, this, [this, selectedUser]() {
        QString name = selectedUser();
        if (name.isEmpty()) { QMessageBox::information(this, tr("No Selection"), tr("Select a user first.")); return; }
        QFile shells("/etc/shells");
        QStringList options;
        if (shells.open(QIODevice::ReadOnly | QIODevice::Text)) {
            for (const QString &l : QString::fromUtf8(shells.readAll()).split('\n', Qt::SkipEmptyParts))
                if (l.startsWith('/')) options << l.trimmed();
        }
        if (options.isEmpty()) options << "/bin/bash" << "/bin/zsh";
        bool ok;
        QString shell = QInputDialog::getItem(this, tr("Change Shell"), tr("Login shell for %1:").arg(name),
                                              options, 0, false, &ok);
        if (!ok) return;
        runSudoCommandInTerminal(QString("sudo usermod -s '%1' '%2' && echo 'Shell changed.'; read -p 'Press Enter...'").arg(shell, name));
    });

    connect(groupsBtn, &QPushButton::clicked, this, [this, selectedUser]() {
        QString name = selectedUser();
        if (name.isEmpty()) { QMessageBox::information(this, tr("No Selection"), tr("Select a user first.")); return; }

        // Current supplementary groups + all system groups
        QProcess p;
        p.start("id", QStringList() << "-nG" << name);
        p.waitForFinished(2000);
        QStringList current = QString::fromUtf8(p.readAllStandardOutput()).trimmed().split(' ', Qt::SkipEmptyParts);
        p.start("bash", QStringList() << "-c" << "getent group | cut -d: -f1 | sort");
        p.waitForFinished(2000);
        QStringList all = QString::fromUtf8(p.readAllStandardOutput()).split('\n', Qt::SkipEmptyParts);

        QDialog dlg(this);
        dlg.setWindowTitle(tr("Groups for %1").arg(name));
        dlg.resize(380, 520);
        QVBoxLayout *dl = new QVBoxLayout(&dlg);
        dl->addWidget(new QLabel(tr("Checked = member. Important: wheel (sudo), libvirt, docker, input, video."), &dlg));
        QListWidget *list = new QListWidget(&dlg);
        for (const QString &g : all) {
            if (g == name) continue;                       // primary group stays untouched
            QListWidgetItem *item = new QListWidgetItem(g, list);
            item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
            item->setCheckState(current.contains(g) ? Qt::Checked : Qt::Unchecked);
        }
        dl->addWidget(list);
        QHBoxLayout *btns = new QHBoxLayout();
        QPushButton *apply = new QPushButton(tr("Apply"), &dlg);
        QPushButton *cancel = new QPushButton(tr("Cancel"), &dlg);
        btns->addStretch(); btns->addWidget(apply); btns->addWidget(cancel);
        dl->addLayout(btns);
        connect(apply, &QPushButton::clicked, &dlg, &QDialog::accept);
        connect(cancel, &QPushButton::clicked, &dlg, &QDialog::reject);
        if (dlg.exec() != QDialog::Accepted) return;

        QStringList wanted;
        for (int i = 0; i < list->count(); ++i)
            if (list->item(i)->checkState() == Qt::Checked) wanted << list->item(i)->text();
        runSudoCommandInTerminal(QString("sudo usermod -G '%1' '%2' && echo 'Groups updated. Log out/in to apply.'; read -p 'Press Enter...'")
                                     .arg(wanted.join(','), name));
    });

    connect(iconBtn, &QPushButton::clicked, this, [this, selectedUser]() {
        QString name = selectedUser();
        if (name.isEmpty()) { QMessageBox::information(this, tr("No Selection"), tr("Select a user first.")); return; }
        if (ugUsersTable->item(ugUsersTable->currentRow(), 1)->text().toUInt() == getuid()) {
            // Use the same profile picker as Apps and the desktop, so changing
            // the image cannot silently write an unused legacy account icon.
            QProcess::startDetached("python3", {HyperPanel::root()+"/control_center/app.py", "--tab", "theme"});
            return;
        }
        QString file = QFileDialog::getOpenFileName(this, tr("Choose Avatar for %1").arg(name),
                                                    QDir::homePath(), tr("Images (*.png *.jpg *.jpeg *.bmp *.webp)"));
        if (file.isEmpty()) return;
        QImage img(file);
        if (img.isNull()) { QMessageBox::warning(this, tr("Invalid Image"), tr("Could not read that image file.")); return; }
        // Square 256px crop — the format SDDM/KDE expect from AccountsService
        QImage scaled = img.scaled(256, 256, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
        scaled = scaled.copy((scaled.width() - 256) / 2, (scaled.height() - 256) / 2, 256, 256);
        QString tmp = QDir::temp().filePath("cachyostools-avatar.png");
        if (!scaled.save(tmp, "PNG")) { QMessageBox::warning(this, tr("Failed"), tr("Could not prepare the avatar image.")); return; }
        // AccountsService icon + config (login screen) and ~/.face.icon (legacy consumers)
        QString home = "/home/" + name;
        for (int row = 0; row < ugUsersTable->rowCount(); ++row)
            if (ugUsersTable->item(row, 0)->text() == name) home = ugUsersTable->item(row, 2)->text();
        runSudoCommandInTerminal(QString(
            "sudo mkdir -p /var/lib/AccountsService/icons /var/lib/AccountsService/users && "
            "sudo cp '%1' '/var/lib/AccountsService/icons/%2' && "
            "F='/var/lib/AccountsService/users/%2'; sudo touch \"$F\"; "
            "grep -q '^\\[User\\]' \"$F\" || echo '[User]' | sudo tee -a \"$F\" >/dev/null; "
            "sudo sed -i '/^Icon=/d' \"$F\"; "
            "echo 'Icon=/var/lib/AccountsService/icons/%2' | sudo tee -a \"$F\" >/dev/null; "
            "sudo cp '%1' '%3/.face.icon' 2>/dev/null && sudo chown '%2:' '%3/.face.icon' 2>/dev/null; "
            "echo 'Avatar updated for %2 — visible on the next login screen. Click Refresh in the app.'; read -p 'Press Enter...'")
            .arg(tmp, name, home));
    });
}

// Avatar: AccountsService icon, else ~/.face.icon, else a colored-initial badge
static QIcon ugAvatarFor(const QString &user, const QString &home, bool current) {
    QPixmap px;
    px.load(FusionAccounts::avatarPath(user, home, HyperPanel::root(), current));
    if (!px.isNull()) {
        return QIcon(FusionAccounts::cropped(px, 48));
    }
    static const QList<QColor> palette = {
        QColor("#27ae60"), QColor("#2980b9"), QColor("#8e44ad"),
        QColor("#e67e22"), QColor("#c0392b"), QColor("#16a085")
    };
    px = QPixmap(32, 32);
    px.fill(Qt::transparent);
    QPainter painter(&px);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setBrush(palette[qHash(user) % palette.size()]);
    painter.setPen(Qt::NoPen);
    painter.drawEllipse(0, 0, 32, 32);
    painter.setPen(Qt::white);
    QFont f = painter.font(); f.setBold(true); f.setPixelSize(16); painter.setFont(f);
    painter.drawText(px.rect(), Qt::AlignCenter, user.left(1).toUpper());
    return QIcon(px);
}

void MainWindow::refreshUsersGroups() {
    QProcess *proc = new QProcess(this);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            [this, proc](int, QProcess::ExitStatus) {
                const auto *selectedItem = ugUsersTable->item(ugUsersTable->currentRow(), 0);
                const auto selectedName = selectedItem ? selectedItem->text() : QString();
                ugUsersTable->setRowCount(0);
                const QStringList lines = QString::fromUtf8(proc->readAllStandardOutput()).split('\n', Qt::SkipEmptyParts);
                for (const QString &line : lines) {
                    // user:uid:home:shell:group1 group2 ...
                    const QStringList f = line.split(':');
                    if (f.size() < 5) continue;
                    int row = ugUsersTable->rowCount();
                    ugUsersTable->insertRow(row);
                    for (int c = 0; c < 5; ++c)
                        ugUsersTable->setItem(row, c, new QTableWidgetItem(f[c]));
                    const bool current = f[1].toUInt() == getuid();
                    ugUsersTable->item(row, 0)->setIcon(ugAvatarFor(f[0], f[2], current));
                    if (current) {
                        auto *avatar = dynamic_cast<FusionAccounts::Avatar *>(ui->usersGroupsSubTab->findChild<QWidget *>("usersCurrentAvatar"));
                        if (avatar) avatar->setSource(FusionAccounts::avatarPath(f[0], f[2], HyperPanel::root(), true));
                        const auto *account = getpwuid(getuid());
                        const auto fullName = account ? QString::fromLocal8Bit(account->pw_gecos).section(',',0,0) : QString();
                        ui->usersGroupsSubTab->findChild<QLabel *>("usersCurrentName")->setText(fullName.isEmpty() ? f[0] : fullName+" · "+f[0]);
                        ui->usersGroupsSubTab->findChild<QLabel *>("usersCurrentDescription")->setText(
                            tr("Signed in · %1 · %2").arg(f[4].split(' ').contains("wheel") ? tr("Administrator") : tr("Standard account"), f[2]));
                        ugUsersTable->item(row,0)->setToolTip(tr("Your Hyper Fusion profile picture. Change it in Fusion Settings → Appearance."));
                    }
                    if (f[0] == selectedName || (selectedName.isEmpty() && current)) ugUsersTable->selectRow(row);
                    if (f[4].split(' ').contains("wheel"))
                        ugUsersTable->item(row, 0)->setForeground(QColor("#27ae60"));
                }
                ugUsersTable->resizeColumnsToContents();
                proc->deleteLater();
            });
    proc->start("bash", QStringList() << "-c"
        << "getent passwd | awk -F: '$3==0 || ($3>=1000 && $3<65000)' | while IFS=: read -r u _ uid _ _ home shell; do "
           "printf '%s:%s:%s:%s:%s\\n' \"$u\" \"$uid\" \"$home\" \"$shell\" \"$(id -nG \"$u\" 2>/dev/null)\"; done");
}
