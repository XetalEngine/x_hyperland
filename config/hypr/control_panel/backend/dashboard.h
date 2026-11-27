// Overview checks are asynchronous, bounded, and never prompt for privileges.
#include "../overview_page.h"

void MainWindow::refreshDashboard() {
    if (!overviewPage) {
        // Keep the original buttons and their navigation connections alive in a
        // hidden container. The new page replaces only their presentation.
        auto *legacy = new QWidget(ui->welcomeSubTab);
        legacy->setObjectName("legacyOverview");
        legacy->setLayout(ui->welcomeSubTab->layout());
        legacy->hide();
        auto *layout = new QVBoxLayout(ui->welcomeSubTab);
        layout->setContentsMargins(0, 0, 0, 0);
        overviewPage = new FusionOverview::Page(ui->welcomeSubTab);
        layout->addWidget(overviewPage);
        connect(overviewPage->refresh, &QPushButton::clicked, this, &MainWindow::refreshDashboard);
        const auto link = [this](QPushButton *button, const QString &tool, QPushButton *legacyButton) {
            connect(button, &QPushButton::clicked, this, [this, tool, legacyButton] {
                if (auto *panel = findChild<PanelController *>()) panel->open(tool);
                else legacyButton->click();
            });
        };
        link(overviewPage->drives, "drives", ui->dashDrivesButton);
        link(overviewPage->manageServices, "services", ui->dashServicesButton);
        link(overviewPage->reviewUpdates, "updates", ui->dashUpdatesButton);
        link(overviewPage->safetyIso, "iso", ui->dashIsoButton);
        link(overviewPage->logs, "logs", ui->dashSystemButton);
        // The vendored standalone updater is not used by Hyper Fusion.
        dashUpdateBtn = new QPushButton(legacy);
        dashUpdateBtn->hide();
    }
    if (overviewPending) return;
    overviewPending = 5;
    overviewPage->setBusy(true);
    const auto launch = [this](const QString &program, const QStringList &arguments, auto apply, int timeout = 30000) {
        auto *proc = new QProcess(this);
        auto environment = QProcessEnvironment::systemEnvironment();
        environment.insert("LC_ALL", "C");
        proc->setProcessEnvironment(environment);
        const auto finish = [this, proc, apply](int code, bool normal) {
            if (proc->property("overviewFinished").toBool()) return;
            proc->setProperty("overviewFinished", true);
            apply(QString::fromUtf8(proc->readAllStandardOutput()), code, normal);
            if (--overviewPending == 0) overviewPage->setBusy(false);
            proc->deleteLater();
        };
        connect(proc, &QProcess::finished, this, [finish](int code, QProcess::ExitStatus status) { finish(code, status == QProcess::NormalExit); });
        connect(proc, &QProcess::errorOccurred, this, [finish](QProcess::ProcessError error) { if (error == QProcess::FailedToStart) finish(-1, false); });
        QTimer::singleShot(timeout, proc, [proc] { if (proc->state() != QProcess::NotRunning) proc->kill(); });
        proc->start(program, arguments);
    };
    launch("bash", {"-c", R"SH(
        echo "CPU: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ //')"
        echo "GPU: $(lspci 2>/dev/null | grep -E ' (VGA compatible controller|3D controller|Display controller): ' | head -1 | sed -E 's/^[^ ]+ [^:]+: //; s/ \(rev.*//')"
        echo "KERNEL: $(uname -r)"
        echo "UPTIME: $(uptime -p | sed 's/^up //')"
        free -b | awk '/^Mem:/{printf "RAMPCT: %d\n", $3*100/$2}'
        free -h | awk '/^Mem:/{printf "RAM: %s %s\n", $3, $2}'
    )SH"}, [this](const QString &out, int code, bool normal) { overviewPage->systemResult(out, normal && code == 0); });
    launch("bash", {"-o", "pipefail", "-c", "df -h --output=target,used,size,pcent / /home 2>/dev/null | tail -n +2 | sort -u"},
        [this](const QString &out, int code, bool normal) { overviewPage->storageResult(out, normal && code == 0); });
    launch("bash", {"-c", R"SH(
        running=$(systemctl list-units --type=service --state=running --no-legend --plain 2>/dev/null) || exit 1
        failed=$(systemctl --failed --no-legend --plain 2>/dev/null) || exit 1
        printf '%s\n' "$running" | awk 'NF{n++} END{print "RUNNING: " n+0}'
        printf '%s\n' "$failed" | awk 'NF{print "FAILED: " $1}'
    )SH"}, [this](const QString &out, int code, bool normal) { overviewPage->servicesResult(out, normal && code == 0); });
    launch("checkupdates", {}, [this](const QString &out, int code, bool normal) { overviewPage->updatesResult(out, code, normal); }, 60000);
    launch("bash", {"-c", R"SH(
        if ! sudo -n true 2>/dev/null; then echo NOAUTH; exit 0; fi
        command -v smartctl >/dev/null || exit 1
        for d in $(lsblk -dpno NAME,TYPE | awk '$2=="disk"{print $1}'); do
            h=$(sudo -n smartctl -H "$d" 2>/dev/null | grep -Ei 'overall-health|SMART Health Status')
            case "$h" in *PASSED*|*OK*) v='Passed';; *FAILED*) v='FAILING';; *) v='Status unavailable';; esac
            s=$(sudo -n smartctl -a "$d" 2>/dev/null | grep 'Available Spare:' | awk '{print $3}')
            if [ -n "$s" ] && [ "${s%\%}" -lt 80 ] 2>/dev/null && [ "$v" = 'Passed' ]; then v="Low spare capacity: $s"; fi
            printf '%s: %s\n' "$(basename "$d")" "$v"
        done
    )SH"}, [this](const QString &out, int code, bool normal) { overviewPage->healthResult(out, normal && code == 0); });
    QDir isoDir(QDir::homePath() + "/iso/xiso/output");
    const auto isos = isoDir.entryInfoList({"*.iso"}, QDir::Files, QDir::Time);
    if (isos.isEmpty()) overviewPage->recoveryResult({}, {}, 0);
    else {
        const auto &newest = isos.first();
        overviewPage->recoveryResult(newest.fileName(), formatSize(newest.size()), newest.lastModified().daysTo(QDateTime::currentDateTime()));
    }
}

void MainWindow::on_dashRefreshButton_clicked() { refreshDashboard(); }

// ---- Self-updater: git-based, source-build aware ----------------------------

// The repo the running binary came from: walk up from the executable until a
// git checkout of this project is found (root binary or a build/ subdir).
static const char *XETAL_REPO_URL = "https://github.com/XetalEngine/CachyOsTools.git";
static const char *XETAL_API_URL  = "https://api.github.com/repos/XetalEngine/CachyOsTools/commits/main";

// A git checkout we can `git pull` (developer machines)
static QString xetalRepoDir() {
    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 5; ++i) {
        if (dir.exists(".git") && dir.exists("CMakeLists.txt") && dir.exists("build.sh"))
            return dir.absolutePath();
        if (!dir.cdUp()) break;
    }
    return QString();
}

// A plain copy of the app (what ships on the ISO): source tree without .git.
// These get updated by cloning fresh from GitHub rather than pulling.
static QString xetalPlainInstallDir() {
    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 3; ++i) {
        if (dir.exists("CMakeLists.txt") && dir.exists("CachyOsTools"))
            return dir.absolutePath();
        if (!dir.cdUp()) break;
    }
    return QString();
}

// Records the commit a plain install was updated to, so later checks are exact
static QString xetalInstalledSha(const QString &installDir) {
    QFile f(installDir + "/.xetal-version");
    if (!f.open(QIODevice::ReadOnly | QIODevice::Text)) return QString();
    return QString::fromUtf8(f.readAll()).trimmed();
}

// Restart through ./run.sh in the project root, inside a terminal window.
// run.sh itself only exec()s the binary, so launching it bare would give no
// console; wrapping it in a terminal reproduces how the app is run by hand and
// keeps the app's stdout/qDebug output visible after an update.
static void xetalRestartApp() {
    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 4; ++i) {
        if (dir.exists("run.sh") && dir.exists("CMakeLists.txt")) {
            const QString root = dir.absolutePath();
            for (const QString &t : {HyperPanel::terminal(), QString("xterm"),
                                     QString("alacritty"), QString("kitty")}) {
                if (QStandardPaths::findExecutable(t).isEmpty()) continue;
                if (QProcess::startDetached(t, QStringList() << "-e" << "bash" << "-c"
                        << QString("cd '%1' && ./run.sh").arg(root)))
                    return;
            }
            // No terminal available: still prefer run.sh over the raw binary
            if (QProcess::startDetached("bash", QStringList() << dir.absoluteFilePath("run.sh"), root))
                return;
            break;
        }
        if (!dir.cdUp()) break;
    }
    QProcess::startDetached(QCoreApplication::applicationFilePath(), QStringList());
}

void MainWindow::checkForAppUpdates() {
    return; // Updates are managed by Hyper Fusion, including this backend.

    // Testing aid: CACHYOSTOOLS_FAKE_UPDATE=<n> pretends n commits are available
    const QString fake = qEnvironmentVariable("CACHYOSTOOLS_FAKE_UPDATE");
    if (!fake.isEmpty()) {
        dashUpdateBtn->setText(tr("⬆️ UPDATE — %1 new commit(s) available!").arg(fake.toInt()));
        dashUpdateBtn->show();
        return;
    }

    const QString repo = xetalRepoDir();
    if (repo.isEmpty()) { checkForAppUpdatesViaApi(); return; }   // plain copy (ISO installs)

    QProcess *proc = new QProcess(this);
    // Silent failure by design: no network / no remote just means no button
    QTimer *watchdog = new QTimer(proc);
    watchdog->setSingleShot(true);
    connect(watchdog, &QTimer::timeout, proc, &QProcess::kill);
    watchdog->start(20000);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            [this, proc](int exitCode, QProcess::ExitStatus) {
                const QStringList lines = QString::fromUtf8(proc->readAllStandardOutput()).split('\n', Qt::SkipEmptyParts);
                if (exitCode == 0 && !lines.isEmpty()) {
                    bool ok = false;
                    int behind = lines[0].trimmed().toInt(&ok);
                    if (ok && behind > 0) {
                        dashUpdateBtn->setText(tr("⬆️ UPDATE — %1 new commit(s) available!").arg(behind));
                        dashUpdateBtn->setToolTip(lines.size() > 1
                            ? tr("Latest change: %1\nClick to pull, rebuild and restart.").arg(lines[1].trimmed())
                            : tr("Click to pull, rebuild and restart."));
                        dashUpdateBtn->show();
                    } else {
                        dashUpdateBtn->hide();
                    }
                }
                proc->deleteLater();
            });
    proc->start("bash", QStringList() << "-c" << QString(
        "cd '%1' && git fetch -q origin 2>/dev/null && "
        "git rev-list --count HEAD..origin/main 2>/dev/null && "
        "git log -1 --format=%%s origin/main 2>/dev/null").arg(repo));
}

// Plain (non-git) installs — the ISO case — ask GitHub directly what the newest
// commit is. Exact when a previous self-update left a .xetal-version marker,
// otherwise compares the commit date against this binary's build date.
void MainWindow::checkForAppUpdatesViaApi() {
    return; // Updates are managed by Hyper Fusion, including this backend.

    const QString install = xetalPlainInstallDir();
    if (install.isEmpty()) return;                    // not a recognizable install

    QProcess *proc = new QProcess(this);
    QTimer *watchdog = new QTimer(proc);
    watchdog->setSingleShot(true);
    connect(watchdog, &QTimer::timeout, proc, &QProcess::kill);
    watchdog->start(20000);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            [this, proc, install](int exitCode, QProcess::ExitStatus) {
                if (exitCode != 0) { proc->deleteLater(); return; }   // offline: stay silent
                const QJsonObject obj = QJsonDocument::fromJson(proc->readAllStandardOutput()).object();
                const QString sha = obj.value("sha").toString();
                const QJsonObject commit = obj.value("commit").toObject();
                const QString msg = commit.value("message").toString().section('\n', 0, 0);
                const QDateTime date = QDateTime::fromString(
                    commit.value("committer").toObject().value("date").toString(), Qt::ISODate);
                if (sha.isEmpty()) { proc->deleteLater(); return; }

                const QString localSha = xetalInstalledSha(install);
                bool behind;
                if (!localSha.isEmpty()) {
                    behind = !sha.startsWith(localSha) && !localSha.startsWith(sha);
                } else {
                    // No marker yet: the binary's build time is our best "installed at"
                    const QDateTime built = QFileInfo(QCoreApplication::applicationFilePath()).lastModified();
                    behind = date.isValid() && built.isValid() && date > built;
                }
                if (behind) {
                    dashUpdateBtn->setText(tr("⬆️ UPDATE AVAILABLE"));
                    dashUpdateBtn->setToolTip(tr("Latest change: %1\nClick to download, rebuild and restart.").arg(msg));
                    dashUpdateBtn->setProperty("targetSha", sha);
                    dashUpdateBtn->show();
                } else {
                    dashUpdateBtn->hide();
                }
                proc->deleteLater();
            });
    proc->start("curl", QStringList() << "-fsSL" << "--max-time" << "15"
                                      << "-H" << "Accept: application/vnd.github+json"
                                      << XETAL_API_URL);
}

void MainWindow::runAppUpdate() {
    QProcess::startDetached("python3",{HyperPanel::root()+"/theme/run.py","python3",HyperPanel::root()+"/updates/app.py"});return;

    const QString repo = xetalRepoDir();
    if (repo.isEmpty()) { runAppUpdateFromClone(); return; }   // plain copy install

    // Uncommitted changes would make git pull fail — tell the user up front
    QProcess st;
    st.start("git", QStringList() << "-C" << repo << "status" << "--porcelain");
    st.waitForFinished(3000);
    const bool dirty = !QString::fromUtf8(st.readAllStandardOutput()).trimmed().isEmpty();
    QString warning = dirty
        ? tr("\n\n⚠ The repo has local uncommitted changes — the pull will refuse to overwrite them. Commit or stash first if the update fails.")
        : QString();

    if (QMessageBox::question(this, tr("Update CachyOsTools"),
            tr("This will, in a visible terminal:\n\n"
               "1. Pull the newest version into:\n    %1\n"
               "2. Rebuild the app\n"
               "3. Offer to restart when done%2\n\nContinue?").arg(repo, warning)) != QMessageBox::Yes)
        return;

    const QString script = QString(
        "cd '%1' || exit 1; "
        "echo '== Pulling latest version...'; "
        "git pull --ff-only || { echo; echo '❌ Pull failed (local changes or diverged history).'; read -p 'Press Enter to close...'; exit 1; }; "
        "echo; echo '== Rebuilding...'; "
        "BD=$(ls -td build/*/ 2>/dev/null | head -1); "
        "if [ -n \"$BD\" ] && [ -f \"${BD}CMakeCache.txt\" ]; then "
        "  cmake --build \"$BD\" -j$(nproc) && cp -f \"${BD}CachyOsTools\" ./CachyOsTools; "
        "else ./build.sh; fi "
        "&& { echo; echo '== ✅ Update complete.'; } || echo '❌ Build failed - see output above.'; "
        "read -p 'Press Enter to close this window...'").arg(repo);

    // Run as a child process (not detached) so we know when the update finished
    QString term;
    for (const QString &t : {HyperPanel::terminal(), QString("xterm"), QString("alacritty"), QString("kitty")}) {
        if (!QStandardPaths::findExecutable(t).isEmpty()) { term = t; break; }
    }
    if (term.isEmpty()) {
        QMessageBox::warning(this, tr("Terminal Not Found"),
            tr("Could not find a suitable terminal emulator. Please install one of: konsole, gnome-terminal, xterm, alacritty, or kitty"));
        return;
    }
    QProcess *proc = new QProcess(this);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            [this, proc](int, QProcess::ExitStatus) {
                proc->deleteLater();
                if (QMessageBox::question(this, tr("Restart CachyOsTools?"),
                        tr("If the update succeeded, a restart loads the new version.\n\nRestart now?")) == QMessageBox::Yes) {
                    xetalRestartApp();
                    qApp->quit();
                }
            });
    proc->start(term, QStringList() << "-e" << "bash" << "-c" << script);
}

// Update a plain (non-git) install: clone the newest source into a temp dir,
// build it there, then replace the installed sources + binary in place.
// This is the path ISO users take, where there is no git checkout to pull.
void MainWindow::runAppUpdateFromClone() {
    QProcess::startDetached("python3",{HyperPanel::root()+"/theme/run.py","python3",HyperPanel::root()+"/updates/app.py"});return;

    const QString install = xetalPlainInstallDir();
    if (install.isEmpty()) {
        QMessageBox::information(this, tr("Cannot Self-Update"),
            tr("This copy of CachyOsTools is not a recognizable install directory,\n"
               "so it cannot update itself.\n\n"
               "Get the newest version with:\n"
               "  git clone %1").arg(XETAL_REPO_URL));
        return;
    }

    if (QMessageBox::question(this, tr("Update CachyOsTools"),
            tr("This will, in a visible terminal:\n\n"
               "1. Download the newest version from GitHub\n"
               "2. Build it (needs cmake, qt6-base and a compiler)\n"
               "3. Replace the copy in:\n    %1\n"
               "4. Offer to restart when done\n\n"
               "Your settings and saved profiles are untouched.\n\nContinue?").arg(install)) != QMessageBox::Yes)
        return;

    const QString script = QString(
        "set -o pipefail; "
        "TMP=$(mktemp -d) || exit 1; trap 'rm -rf \"$TMP\"' EXIT; "
        "echo '== Downloading the newest version...'; "
        "git clone --depth 1 %1 \"$TMP/src\" || { echo; echo '❌ Download failed (no network, or git not installed).'; read -p 'Press Enter to close...'; exit 1; }; "
        "echo; echo '== Building (this takes a minute)...'; "
        "cmake -S \"$TMP/src\" -B \"$TMP/build\" -DCMAKE_BUILD_TYPE=Release >/dev/null && "
        "cmake --build \"$TMP/build\" -j$(nproc) || { echo; echo '❌ Build failed - see output above.'; read -p 'Press Enter to close...'; exit 1; }; "
        "echo; echo '== Installing into %2 ...'; "
        // sources first, then the freshly built binary. --remove-destination because
        // the running binary cannot be overwritten in place ('Text file busy').
        "rsync -a --exclude .git --exclude build \"$TMP/src/\" '%2/' && "
        "cp --remove-destination \"$TMP/build/CachyOsTools\" '%2/CachyOsTools' && "
        "git -C \"$TMP/src\" rev-parse HEAD > '%2/.xetal-version' && "
        "{ echo; echo '== ✅ Update complete.'; } || { echo '❌ Install step failed.'; }; "
        "read -p 'Press Enter to close this window...'").arg(XETAL_REPO_URL, install);

    QString term;
    for (const QString &t : {HyperPanel::terminal(), QString("xterm"), QString("alacritty"), QString("kitty")}) {
        if (!QStandardPaths::findExecutable(t).isEmpty()) { term = t; break; }
    }
    if (term.isEmpty()) {
        QMessageBox::warning(this, tr("Terminal Not Found"),
            tr("Could not find a suitable terminal emulator. Please install one of: konsole, gnome-terminal, xterm, alacritty, or kitty"));
        return;
    }
    QProcess *proc = new QProcess(this);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            [this, proc](int, QProcess::ExitStatus) {
                proc->deleteLater();
                if (QMessageBox::question(this, tr("Restart CachyOsTools?"),
                        tr("If the update succeeded, a restart loads the new version.\n\nRestart now?")) == QMessageBox::Yes) {
                    xetalRestartApp();
                    qApp->quit();
                }
            });
    proc->start(term, QStringList() << "-e" << "bash" << "-c" << script);
}
