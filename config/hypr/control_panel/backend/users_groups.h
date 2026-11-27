
#include <QListWidget>
#include <QPainter>
#include <QFileSystemWatcher>
#include <pwd.h>
#include <unistd.h>
#include "../account_avatar.h"
#include "../account_picker.h"
#include "../accounts_page.h"
#include "../native.h"
// Dashboard -> Users & Groups sub-tab: account management the Windows
// lusrmgr.msc way. Group membership is where Arch permission problems live.
// The signed-in account shares Hyper Fusion's profile picture. Other accounts
// use their own account images, without inheriting the current user's theme.

void MainWindow::setupUsersGroupsTab() {
    QVBoxLayout *layout = new QVBoxLayout(ui->usersGroupsSubTab);

    auto *page = new FusionAccounts::Page(HyperPanel::root(), ui->usersGroupsSubTab);
    layout->setContentsMargins(0,0,0,0); layout->addWidget(page);
    ugUsersTable = page->table;
    auto *refreshBtn=page->refresh; auto *addBtn=page->add; auto *delBtn=page->remove;
    auto *passBtn=page->password; auto *shellBtn=page->shell; auto *groupsBtn=page->groups; auto *iconBtn=page->icon;

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

    connect(iconBtn, &QPushButton::clicked, this, [this, page, selectedUser]() {
        const QString name=selectedUser(); const int row=ugUsersTable->currentRow();
        if(name.isEmpty() || row<0)return;
        const auto home=ugUsersTable->item(row,2)->text();
        const bool current=ugUsersTable->item(row,1)->text().toUInt()==getuid();
        FusionAccounts::Picker picker(HyperPanel::root(),FusionAccounts::avatarPath(name,home,HyperPanel::root(),current),this);
        if(picker.exec()!=QDialog::Accepted)return;
        page->icon->setEnabled(false);page->status->setText(tr("Saving account picture…"));
        auto *process=new QProcess(this);
        connect(process,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this,page,process](int code,QProcess::ExitStatus exit){
            const auto result=QJsonDocument::fromJson(process->readAllStandardOutput()).object();
            const bool ok=exit==QProcess::NormalExit && code==0 && result.value("ok").toBool();
            auto message=result.value("message").toString();
            if(message.isEmpty())message=tr("The picture was not saved. Authentication may have been cancelled.");
            page->status->setText(message);page->icon->setEnabled(true);
            if(ok)refreshUsersGroups();else QMessageBox::warning(this,tr("Account picture"),message);
            process->deleteLater();
        });
        connect(process,&QProcess::errorOccurred,this,[page,process](QProcess::ProcessError error){
            if(error==QProcess::FailedToStart){page->icon->setEnabled(true);page->status->setText(QObject::tr("Could not start the account-picture helper."));process->deleteLater();}
        });
        process->start("python3",{HyperPanel::root()+"/account_avatars/model.py","apply",name,picker.selectedId()});
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
                    if (current) ugUsersTable->item(row,0)->setToolTip(tr("Your signed-in account"));
                    if (f[0] == selectedName || (selectedName.isEmpty() && current)) ugUsersTable->selectRow(row);
                    if (f[4].split(' ').contains("wheel"))
                        ugUsersTable->item(row, 0)->setForeground(QColor("#27ae60"));
                }
                if (auto *page=dynamic_cast<FusionAccounts::Page *>(ui->usersGroupsSubTab->findChild<QWidget *>("fusionAccountsPage")))
                    page->rebuilt();
                proc->deleteLater();
            });
    proc->start("bash", QStringList() << "-c"
        << "getent passwd | awk -F: '$3==0 || ($3>=1000 && $3<65000)' | while IFS=: read -r u _ uid _ _ home shell; do "
           "printf '%s:%s:%s:%s:%s\\n' \"$u\" \"$uid\" \"$home\" \"$shell\" \"$(id -nG \"$u\" 2>/dev/null)\"; done");
}
