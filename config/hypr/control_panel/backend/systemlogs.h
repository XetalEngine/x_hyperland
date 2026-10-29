#include "log_reader.h"
#include <memory>
#include <QScrollBar>

void MainWindow::setupLogFiles() {
    logFileList.clear();
    
    // System logs
    logFileList.append({"/var/log/messages", "General system messages", "System Logs", false, 0});
    logFileList.append({"/var/log/syslog", "System log messages", "System Logs", false, 0});
    logFileList.append({"/var/log/kern.log", "Kernel log messages", "System Logs", false, 0});
    logFileList.append({"/var/log/auth.log", "Authentication and authorization logs", "System Logs", false, 0});
    logFileList.append({"/var/log/dmesg", "Kernel ring buffer messages", "System Logs", false, 0});
    logFileList.append({"/var/log/daemon.log", "System daemon logs", "System Logs", false, 0});
    logFileList.append({"/var/log/user.log", "User-level messages", "System Logs", false, 0});
    
    // Boot and startup logs
    logFileList.append({"/var/log/boot.log", "Boot process messages", "Boot Logs", false, 0});
    logFileList.append({"/var/log/wtmp", "User login/logout records", "Boot Logs", false, 0});
    logFileList.append({"/var/log/btmp", "Failed login attempts", "Boot Logs", false, 0});
    logFileList.append({"/var/log/lastlog", "Last login information", "Boot Logs", false, 0});
    
    // Package management logs
    logFileList.append({"/var/log/pacman.log", "Pacman package manager logs", "Package Logs", false, 0});
    logFileList.append({"/var/log/paru.log", "Paru AUR helper logs", "Package Logs", false, 0});
    
    // X11 and display logs
    logFileList.append({"/var/log/Xorg.0.log", "X11 server logs", "Display Logs", false, 0});
    logFileList.append({"/var/log/Xorg.0.log.old", "Previous X11 server logs", "Display Logs", false, 0});
    
    // Network logs
    logFileList.append({"/var/log/network.log", "Network service logs", "Network Logs", false, 0});
    logFileList.append({"/var/log/ufw.log", "Uncomplicated Firewall logs", "Network Logs", false, 0});
    
    // Application logs
    logFileList.append({"/var/log/cups/error_log", "CUPS printing system errors", "Application Logs", false, 0});
    logFileList.append({"/var/log/cups/access_log", "CUPS printing system access", "Application Logs", false, 0});
    logFileList.append({"/var/log/lightdm/lightdm.log", "LightDM display manager logs", "Application Logs", false, 0});
    logFileList.append({"/var/log/sddm.log", "SDDM display manager logs", "Application Logs", false, 0});
    
    // Systemd journal logs (special handling)
    logFileList.append({"/var/log/journal/", "Systemd journal logs", "Systemd Logs", false, 0});
    
    // System information commands
    logFileList.append({"inxi", "Complete system information (hardware, drivers, etc.)", "System Info", false, 0});
    logFileList.append({"inxi -G", "Graphics/GPU information", "System Info", false, 0});
    logFileList.append({"inxi -C", "CPU information", "System Info", false, 0});
    logFileList.append({"inxi -M", "Machine information", "System Info", false, 0});
    logFileList.append({"inxi -D", "Disk/Storage information", "System Info", false, 0});
    logFileList.append({"inxi -N", "Network information", "System Info", false, 0});
    logFileList.append({"inxi -A", "Audio information", "System Info", false, 0});
    
    // GPU and graphics logs
    logFileList.append({"/var/log/gpu-manager.log", "GPU manager logs", "GPU Logs", false, 0});
    logFileList.append({"/var/log/nvidia-installer.log", "NVIDIA driver installation logs", "GPU Logs", false, 0});
    logFileList.append({"/var/log/amd-installer.log", "AMD driver installation logs", "GPU Logs", false, 0});
    
    // Security logs
    logFileList.append({"/var/log/audit/audit.log", "Audit system logs", "Security Logs", false, 0});
    logFileList.append({"/var/log/secure", "Security-related messages", "Security Logs", false, 0});
    
    // Check which logs actually exist
    for (LogFileEntry &entry : logFileList) {
        if (entry.filePath.startsWith("inxi")) {
            // For inxi commands, check if inxi is available
            QProcess checkProcess;
            checkProcess.start("which", QStringList() << "inxi");
            checkProcess.waitForFinished();
            entry.exists = (checkProcess.exitCode() == 0);
            entry.size = 0; // Commands don't have a file size
        } else {
            QFileInfo fileInfo(entry.filePath);
            entry.exists = fileInfo.exists();
            if (entry.exists) {
                entry.size = fileInfo.size();
            }
        }
    }
}

void MainWindow::populateLogComboBox() {
    const auto previous = ui->logFileComboBox->currentData();
    {
        QSignalBlocker guard(ui->logFileComboBox);
        ui->logFileComboBox->clear();
        for (const LogFileEntry &entry : logFileList)
            if (entry.exists)
                ui->logFileComboBox->addItem(QString("%1 (%2)").arg(entry.filePath, entry.description), entry.filePath);
        const int index = ui->logFileComboBox->findData(previous);
        ui->logFileComboBox->setCurrentIndex(index >= 0 ? index : 0);
    }
    loadLogContent();
}

void MainWindow::loadLogContent() {
    const QString source = ui->logFileComboBox->currentData().toString();
    if (source.isEmpty()) return;
    const bool journal = source.startsWith("/var/log/journal");
    ui->followLogButton->setChecked(false);
    ui->followLogButton->setText(tr("▶ Follow Journal"));
    const auto plan = LogReader::command(source, ui->logLinesSpinBox->value(), true);
    ui->tailLogCheckBox->setEnabled(plan.follow);
    ui->clearLogButton->setEnabled(plan.program == "tail");
    startLogReader(source, plan.follow && ui->tailLogCheckBox->isChecked(), journal ? -ui->bootSelectCombo->currentIndex() : 1);
}

void MainWindow::startLogReader(const QString &source, bool follow, int boot) {
    if (logProcess) {
        auto *old = logProcess;
        logProcess = nullptr;
        old->disconnect(this);
        if (old->state() != QProcess::NotRunning) old->kill();
        old->deleteLater();
    }
    const auto plan = LogReader::command(source, ui->logLinesSpinBox->value(), follow, boot);
    auto *view = ui->logContentTextEdit;
    view->clear();
    view->document()->setMaximumBlockCount(5000);
    ui->logStatusLabel->setText(tr("Loading…"));
    if (QStandardPaths::findExecutable(plan.program).isEmpty()) {
        view->setPlainText(tr("The %1 reader is not installed. This report cannot be decoded as plain text.").arg(plan.program));
        ui->logStatusLabel->setText(tr("Reader unavailable"));
        return;
    }
    auto *proc = new QProcess(this);
    logProcess = proc;
    auto environment = QProcessEnvironment::systemEnvironment();
    environment.insert("NO_COLOR", "1");
    environment.insert("TERM", "dumb");
    environment.insert("SYSTEMD_COLORS", "0");
    environment.insert("SYSTEMD_URLIFY", "0");
    proc->setProcessEnvironment(environment);
    auto stream = std::make_shared<LogReader::Stream>(ui->logFilterEdit->text());
    auto append = [view](const QString &text) {
        if (text.isEmpty()) return;
        auto *bar = view->verticalScrollBar();
        const bool atBottom = bar->value() >= bar->maximum() - 2;
        const int previous = bar->value();
        QTextCursor cursor(view->document());
        cursor.movePosition(QTextCursor::End);
        const auto lines = text.split('\n');
        for (int i = 0; i < lines.size(); ++i) {
            QTextCharFormat format;
            const QString lower = lines[i].toLower();
            const QColor color = lower.contains("error") || lower.contains("failed") || lower.contains("fatal")
                ? QColor("#e74c3c") : lower.contains("warn") ? QColor("#f39c12") : view->palette().color(QPalette::Text);
            format.setForeground(color);
            cursor.insertText(lines[i] + (i < lines.size() - 1 ? "\n" : ""), format);
        }
        bar->setValue(atBottom ? bar->maximum() : previous);
    };
    connect(proc, &QProcess::readyReadStandardOutput, this, [this, proc, stream, append, plan] {
        if (logProcess != proc) return;
        append(stream->take(proc->readAllStandardOutput()));
        ui->logStatusLabel->setText(plan.follow ? tr("Following live · up to 5,000 lines") : tr("Reading…"));
    });
    connect(proc, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this, proc, stream, append](int code, QProcess::ExitStatus status) {
        if (logProcess != proc) return;
        append(stream->take(proc->readAllStandardOutput(), true));
        const auto error = LogReader::plain(QString::fromUtf8(proc->readAllStandardError())).trimmed();
        if (!error.isEmpty()) append("\n" + error + "\n");
        const bool ok = code == 0 && status == QProcess::NormalExit;
        if (ui->logContentTextEdit->toPlainText().isEmpty())
            ui->logContentTextEdit->setPlainText(ok ? tr("No matching records.") : tr("The reader exited without a report."));
        ui->logStatusLabel->setText(ok ? tr("Report loaded") : tr("Reader exited with status %1 — see details above").arg(code));
        logProcess = nullptr;
        proc->deleteLater();
        ui->followLogButton->setChecked(false);
        ui->followLogButton->setText(tr("▶ Follow Journal"));
    });
    connect(proc, &QProcess::errorOccurred, this, [this, proc](QProcess::ProcessError error) {
        if (logProcess != proc || error != QProcess::FailedToStart) return;
        ui->logContentTextEdit->setPlainText(proc->errorString());
        ui->logStatusLabel->setText(tr("Could not start reader"));
        logProcess = nullptr;
        proc->deleteLater();
    });
    proc->start(plan.program, plan.arguments);
}

void MainWindow::clearLogFile(const QString &filePath) {
    if (filePath.isEmpty()) return;
    
    // Check if it's an inxi command (not a file)
    if (filePath.startsWith("inxi")) {
        QMessageBox::warning(this, "Cannot Clear Command", 
            QString("'%1' is a system information command, not a log file. Cannot clear commands.\n\nPlease select an actual log file instead.").arg(filePath));
        return;
    }
    
    // Check if it's a directory (like /var/log/journal/)
    QFileInfo fileInfo(filePath);
    if (fileInfo.isDir()) {
        QMessageBox::warning(this, "Cannot Clear Directory", 
            QString("'%1' is a directory, not a file. Cannot clear directories.\n\nPlease select a specific log file instead.").arg(filePath));
        return;
    }
    
    QMessageBox::StandardButton reply = QMessageBox::question(this, "Clear Log File",
        QString("Are you sure you want to clear '%1'?\n\nThis action cannot be undone.").arg(filePath),
        QMessageBox::Yes | QMessageBox::No);
    
    if (reply == QMessageBox::Yes) {
        // Create a temporary script to handle the sudo command
        QString tempScript = QString("/tmp/clear_log_%1.sh").arg(QDateTime::currentDateTime().toString("yyyyMMdd_hhmmss"));
        QString scriptContent = QString("#!/bin/bash\nsudo sh -c 'echo \"\" > \"%1\"'\necho 'Log file cleared successfully!'\nread -p 'Press Enter to close...'\n").arg(filePath);
        
        QFile scriptFile(tempScript);
        if (scriptFile.open(QIODevice::WriteOnly | QIODevice::Text)) {
            QTextStream out(&scriptFile);
            out << scriptContent;
            scriptFile.close();
            
            // Make the script executable
            QProcess::startDetached("chmod", QStringList() << "+x" << tempScript);
            
            // Run the script in a terminal
            QStringList terminals = {HyperPanel::terminal(), "kitty", "alacritty", "xterm"};
            bool terminalFound = false;
            
            for (const QString &terminal : terminals) {
                if (QProcess::startDetached(terminal, QStringList() << "-e" << tempScript)) {
                    terminalFound = true;
                    break;
                }
            }
            
            if (!terminalFound) {
                QMessageBox::warning(this, tr("Terminal Not Found"), 
                    tr("Could not find a suitable terminal emulator. Please install one of: konsole, gnome-terminal, xterm, alacritty, or kitty"));
            }
            
            // Clean up the script after a delay
            QTimer::singleShot(10000, [tempScript]() {
                QFile::remove(tempScript);
            });
        }
        
        // Wait a moment for the operation to complete, then reload
        QTimer::singleShot(3000, this, &MainWindow::loadLogContent);
    }
}

void MainWindow::searchLogFiles() {
    // This could be extended to search across multiple log files
    loadLogContent();
}

void MainWindow::applyLogFilters() {
    loadLogContent();
}

// Log management slots
void MainWindow::on_refreshLogsButton_clicked() {
    setupLogFiles();
    populateLogComboBox();
}

void MainWindow::on_clearLogButton_clicked() {
    QString selectedLog = ui->logFileComboBox->currentData().toString();
    clearLogFile(selectedLog);
}

void MainWindow::on_applyFilterButton_clicked() {
    applyLogFilters();
}

void MainWindow::on_copyLogButton_clicked() {
    QString content = ui->logContentTextEdit->toPlainText();
    if (!content.isEmpty()) {
        QApplication::clipboard()->setText(content);
        ui->logStatusLabel->setText(tr("Copied to clipboard"));
    }
}

void MainWindow::on_saveLogButton_clicked() {
    QString content = ui->logContentTextEdit->toPlainText();
    if (content.isEmpty()) return;
    
    QString fileName = QFileDialog::getSaveFileName(this, "Save Log Content", 
        QString("log_%1.txt").arg(QDateTime::currentDateTime().toString("yyyyMMdd_hhmmss")),
        "Text Files (*.txt);;All Files (*)");
    
    if (!fileName.isEmpty()) {
        QFile file(fileName);
        if (file.open(QIODevice::WriteOnly | QIODevice::Text)) {
            QTextStream out(&file);
            out << content;
            file.close();
            ui->logStatusLabel->setText("Saved to " + fileName);
        } else {
            QMessageBox::warning(this, tr("Error"), tr("Could not save file."));
        }
    }
}

void MainWindow::on_logFileComboBox_currentTextChanged(const QString &text) {
    Q_UNUSED(text)
    loadLogContent();
}

// Helper to open a config file in nano in a terminal with sudo (shared by all tabs)
void MainWindow::openConfigInNano(const QString &filePath) {
    QString command = QString("sudo nano '%1'").arg(filePath);
    QStringList terminals = {HyperPanel::terminal(), "kitty", "alacritty", "xterm"};
    for (const QString &terminal : terminals) {
        if (QProcess::startDetached(terminal, QStringList() << "-e" << "bash" << "-c" << command)) {
            return;
        }
    }
    QMessageBox::warning(this, tr("Terminal Not Found"), tr("Could not find a suitable terminal emulator. Please install one of: konsole, gnome-terminal, xterm, alacritty, or kitty"));
}
