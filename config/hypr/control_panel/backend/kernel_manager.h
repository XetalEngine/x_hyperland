
#include <QListWidget>
#include <QComboBox>
#include "../native.h"
#include "../kernel_catalog.h"
#include <QSysInfo>
// Dashboard -> Kernels sub-tab: every kernel that can actually boot this
// machine (module directories, package metadata and boot images — catches TKG builds
// and manually installed kernels too), install/remove, popular-kernel
// installer (repo / AUR / build-from-source), and the default GRUB entry.

void MainWindow::setupKernelManagerTab() {
    QVBoxLayout *layout = new QVBoxLayout(ui->kernelManagerSubTab);

    QHBoxLayout *bar = new QHBoxLayout();
    QLabel *hint = new QLabel(tr("Multiple kernels = safety. Keep an LTS fallback next to your daily driver."), ui->kernelManagerSubTab);
    hint->setStyleSheet("color:#888;");
    QPushButton *refreshBtn = new QPushButton(tr("🔄 Refresh"), ui->kernelManagerSubTab);
    QPushButton *popularBtn = new QPushButton(tr("🌟 Install Popular Kernel..."), ui->kernelManagerSubTab);
    QPushButton *removeBtn = new QPushButton(tr("🗑️ Remove Selected"), ui->kernelManagerSubTab);
    bar->addWidget(hint);
    bar->addStretch();
    bar->addWidget(refreshBtn);
    bar->addWidget(popularBtn);
    bar->addWidget(removeBtn);
    layout->addLayout(bar);
    auto *inventoryStatus = new QLabel(ui->kernelManagerSubTab);
    inventoryStatus->setObjectName("kernelInventoryStatus");
    inventoryStatus->setWordWrap(true);
    layout->addWidget(inventoryStatus);

    kmTable = new QTableWidget(ui->kernelManagerSubTab);
    kmTable->setColumnCount(5);
    kmTable->setHorizontalHeaderLabels(QStringList() << tr("Boot Image") << tr("Package") << tr("Version") << tr("Running") << tr("Headers"));
    kmTable->horizontalHeader()->setSectionResizeMode(QHeaderView::Interactive);
    kmTable->horizontalHeader()->setStretchLastSection(true);
    kmTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    kmTable->setSelectionMode(QAbstractItemView::SingleSelection);
    kmTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    kmTable->setAlternatingRowColors(true);
    kmTable->verticalHeader()->setVisible(false);
    layout->addWidget(kmTable);

    QLabel *grubHeader = new QLabel(tr("🥾 Boot entry (GRUB)"), ui->kernelManagerSubTab);
    QFont f = grubHeader->font(); f.setBold(true); grubHeader->setFont(f);
    layout->addWidget(grubHeader);

    kmGrubDefaultLabel = new QLabel(ui->kernelManagerSubTab);
    kmGrubDefaultLabel->setStyleSheet("color:#888;");
    layout->addWidget(kmGrubDefaultLabel);

    kmGrubList = new QListWidget(ui->kernelManagerSubTab);
    kmGrubList->setMaximumHeight(140);
    kmGrubList->setAlternatingRowColors(true);
    layout->addWidget(kmGrubList);

    QHBoxLayout *grubBar = new QHBoxLayout();
    QPushButton *setDefaultBtn = new QPushButton(tr("⭐ Set Selected as Default Boot Entry"), ui->kernelManagerSubTab);
    QPushButton *regenBtn = new QPushButton(tr("🔧 Regenerate GRUB Config"), ui->kernelManagerSubTab);
    grubBar->addStretch();
    grubBar->addWidget(setDefaultBtn);
    grubBar->addWidget(regenBtn);
    layout->addLayout(grubBar);

    connect(refreshBtn, &QPushButton::clicked, this, &MainWindow::refreshKernelManager);

    connect(popularBtn, &QPushButton::clicked, this, [this]() {
        KernelCatalog dlg(HyperPanel::root() + "/control_panel/kernel_inventory.py", this);
        if (dlg.exec() != QDialog::Accepted) return;
        const auto command = KernelCatalog::installCommand(dlg.selection());
        if (command.isEmpty()) return;
        runSudoCommandInTerminal("if (" + command + "); then echo 'Kernel installation finished. Refresh the kernel list; boot the new kernel to use it.'; "
                                "else echo 'Kernel installation failed. Review the errors above.'; fi; read -r -p 'Press Enter…'");
    });

    connect(removeBtn, &QPushButton::clicked, this, [this]() {
        int row = kmTable->currentRow();
        if (row < 0 || !kmTable->item(row, 0)) {
            QMessageBox::information(this, tr("No Selection"), tr("Select an installed kernel first."));
            return;
        }
        QString image = kmTable->item(row, 0)->text();
        QString pkg = kmTable->item(row, 1)->text();
        if (kmTable->item(row, 3)->data(Qt::UserRole).toBool()) {
            QMessageBox::warning(this, tr("Refused"), tr("'%1' is the kernel you are running right now. Boot another kernel first.").arg(image));
            return;
        }
        int installedCount = 0;
        for (int i = 0; i < kmTable->rowCount(); ++i) installedCount += kmTable->item(i, 0)->data(Qt::UserRole).toBool();
        if (installedCount <= 1) {
            QMessageBox::warning(this, tr("Refused"), tr("That is your only installed kernel."));
            return;
        }
        if (pkg == "-" || !QRegularExpression("^[a-zA-Z0-9][a-zA-Z0-9@._+\\-]*$").match(pkg).hasMatch()) {
            QMessageBox::information(this, tr("Not Package-Managed"),
                tr("This kernel could not be mapped to an installed pacman package. Automatic removal is unavailable."));
            return;
        }
        if (QMessageBox::warning(this, tr("Remove Kernel"),
                tr("Remove package '%1' (boot image '%2') and its headers?\n\n"
                   "pacman + the mkinitcpio hook clean up /boot and the modules; GRUB is regenerated automatically afterwards.").arg(pkg, image),
                QMessageBox::Yes | QMessageBox::No) != QMessageBox::Yes) return;
        runSudoCommandInTerminal(QString(
            "(sudo pacman -R %1 %1-headers 2>/dev/null || sudo pacman -R %1) && "
            "sudo grub-mkconfig -o /boot/grub/grub.cfg && "
            "echo && echo 'Kernel removed and GRUB menu updated.'; read -p 'Press Enter...'").arg(pkg));
    });

    connect(setDefaultBtn, &QPushButton::clicked, this, [this]() {
        QListWidgetItem *item = kmGrubList->currentItem();
        if (!item) {
            QMessageBox::information(this, tr("No Selection"), tr("Select a boot entry from the list first."));
            return;
        }
        QString entry = item->data(Qt::UserRole).toString();   // full "submenu>entry" path
        entry.replace('\'', ' ');
        if (QMessageBox::question(this, tr("Set Default Boot Entry"),
                tr("Boot this entry by default from now on?\n\n%1").arg(item->text())) != QMessageBox::Yes) return;
        runSudoCommandInTerminal(QString(
            "sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT=saved/' /etc/default/grub && "
            "sudo sed -i 's/^#*GRUB_SAVEDEFAULT=.*/GRUB_SAVEDEFAULT=false/' /etc/default/grub && "
            "sudo grub-mkconfig -o /boot/grub/grub.cfg && "
            "sudo grub-set-default '%1' && "
            "echo && echo 'Default boot entry saved.'; read -p 'Press Enter...'").arg(entry));
    });

    connect(regenBtn, &QPushButton::clicked, this, [this]() {
        runSudoCommandInTerminal("sudo grub-mkconfig -o /boot/grub/grub.cfg && echo 'GRUB config regenerated.'; read -p 'Press Enter...'");
    });
}

void MainWindow::refreshKernelManager() {
    QProcess *proc = new QProcess(this);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            [this, proc](int, QProcess::ExitStatus) {
                const QStringList sections = QString::fromUtf8(proc->readAllStandardOutput()).split("===GRUB===");

                const auto snapshot = QJsonDocument::fromJson(sections.value(0).toUtf8()).object();
                const auto running = snapshot["running"].toString(QSysInfo::kernelVersion());
                auto kernels = snapshot["kernels"].toArray();
                if (kernels.isEmpty()) kernels.append(QJsonObject{{"release", running}, {"running", true},
                    {"image", "Running kernel · boot files unavailable"}});
                kmTable->setRowCount(0);
                for (const auto &entry : kernels) {
                    const auto data = entry.toObject();
                    const int row = kmTable->rowCount(); kmTable->insertRow(row);
                    kmTable->setItem(row, 0, new QTableWidgetItem(data["image"].toString()));
                    kmTable->item(row, 0)->setData(Qt::UserRole, data["installed"].toBool());
                    const auto pkg = data["package"].toString();
                    kmTable->setItem(row, 1, new QTableWidgetItem(pkg.isEmpty() ? "-" : pkg));
                    kmTable->setItem(row, 2, new QTableWidgetItem(data["release"].toString(data["version"].toString())));
                    kmTable->item(row, 2)->setToolTip(tr("Package version: %1").arg(data["version"].toString()));
                    kmTable->setItem(row, 3, new QTableWidgetItem(data["running"].toBool() ? tr("✅ current (%1)").arg(running) : QString()));
                    kmTable->item(row, 3)->setData(Qt::UserRole, data["running"].toBool());
                    kmTable->setItem(row, 4, new QTableWidgetItem(data["headers"].toBool() ? tr("✅ installed") : tr("—")));
                }
                kmTable->resizeColumnsToContents();
                kmTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
                if (auto *status = ui->kernelManagerSubTab->findChild<QLabel *>("kernelInventoryStatus"))
                    status->setText(tr("Running kernel: %1 · %2 entries. Installing a kernel does not change the running kernel until you reboot into it.").arg(running).arg(kernels.size()) +
                        (snapshot.isEmpty() ? tr(" Inventory could not be read; refresh to retry.") : QString()));

                // --- GRUB: default setting + menu entries (top level and submenu)
                kmGrubList->clear();
                QString grubDefault = tr("(unknown)");
                QString submenu;
                for (const QString &line : sections.value(1).split('\n')) {
                    if (line.startsWith("DEFAULT:")) { grubDefault = line.section(':', 1).trimmed(); continue; }
                    QRegularExpressionMatch sm = QRegularExpression("^submenu '([^']+)'").match(line.trimmed());
                    if (sm.hasMatch() && !line.startsWith('\t') && !line.startsWith(' ')) { submenu = sm.captured(1); continue; }
                    QRegularExpressionMatch me = QRegularExpression("^\\s*menuentry '([^']+)'").match(line);
                    if (me.hasMatch()) {
                        bool nested = line.startsWith('\t') || line.startsWith("    ");
                        QString title = me.captured(1);
                        QString path = (nested && !submenu.isEmpty()) ? submenu + ">" + title : title;
                        QListWidgetItem *item = new QListWidgetItem((nested ? "   ↳ " : "") + title, kmGrubList);
                        item->setData(Qt::UserRole, path);
                    }
                }
                kmGrubDefaultLabel->setText(tr("GRUB_DEFAULT is currently: %1 — select an entry below and set it as default.").arg(grubDefault));
                proc->deleteLater();
            });
    proc->start("bash", QStringList() << "-c"
        << "python3 \"$1\" inventory; "
           "echo ===GRUB===; "
           "grep '^GRUB_DEFAULT=' /etc/default/grub 2>/dev/null | sed 's/^GRUB_DEFAULT=/DEFAULT:/'; "
           "cat /boot/grub/grub.cfg 2>/dev/null | grep -E \"^(submenu|[[:space:]]*menuentry)\" || sudo -n cat /boot/grub/grub.cfg 2>/dev/null | grep -E \"^(submenu|[[:space:]]*menuentry)\""
        << "kernel-inventory" << HyperPanel::root() + "/control_panel/kernel_inventory.py");
}
