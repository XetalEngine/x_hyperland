#pragma once
#include <QtWidgets>

namespace FusionOverview {
// Presentation and parsing only. Navigation is connected to the existing tools
// by MainWindow; opening the overview never authorizes or changes the system.
class Page final : public QWidget {
public:
  explicit Page(QWidget *parent = nullptr) : QWidget(parent) {
    setObjectName("fusionOverviewPage");
    setStyleSheet(R"(
      QWidget#fusionOverviewPage { background:palette(window); }
      QWidget#overviewContent, QScrollArea#overviewScroll { background:transparent; border:none; }
      QFrame[overviewCard=true] { background:palette(alternate-base); border:1px solid palette(mid); border-radius:16px; }
      QFrame#overviewSystem { border-left:4px solid palette(highlight); }
      QWidget#fusionOverviewPage QLabel { background:transparent; border:none; padding:0; color:palette(window-text); }
      QWidget#fusionOverviewPage QLabel[overviewMuted=true] { color:palette(placeholder-text); }
      QWidget#fusionOverviewPage QLabel[overviewTitle=true] { font-size:18px; font-weight:600; }
      QWidget#fusionOverviewPage QLabel[overviewMetric=true] { font-size:32px; font-weight:700; color:palette(link); }
      QWidget#fusionOverviewPage QLabel#overviewHeading { font-size:26px; font-weight:700; }
      QWidget#fusionOverviewPage QLabel#overviewCpu { font-size:20px; font-weight:600; }
      QWidget#fusionOverviewPage QLabel#overviewEyebrow { font-size:11px; font-weight:700; letter-spacing:2px; color:palette(link); }
      QWidget#fusionOverviewPage QPushButton { padding:7px 12px; border-radius:8px; }
      QWidget#fusionOverviewPage QProgressBar { background:palette(base); border:none; border-radius:4px; min-height:8px; max-height:8px; }
      QWidget#fusionOverviewPage QProgressBar::chunk { background:palette(highlight); border-radius:4px; }
    )");
    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(18, 16, 18, 16); outer->setSpacing(18);
    auto *header = new QHBoxLayout;
    auto *titles = new QVBoxLayout; titles->setSpacing(6);
    titles->addWidget(text(tr("System Overview"), "overviewHeading"));
    titles->addWidget(text(tr("Your computer, at a glance."), {}, true));
    header->addLayout(titles, 1);
    refresh = action(tr("Refresh"), "view-refresh", "overviewRefresh");
    header->addWidget(refresh); outer->addLayout(header);
    scroll = new QScrollArea;
    scroll->setObjectName("overviewScroll"); scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame); scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    content = new QWidget; content->setObjectName("overviewContent"); scroll->setWidget(content); outer->addWidget(scroll, 1);
    auto *body = new QVBoxLayout(content); body->setContentsMargins(0, 0, 8, 0); body->setSpacing(16);

    auto *hero = card("overviewSystem");
    heroLayout = new QBoxLayout(QBoxLayout::LeftToRight, hero); heroLayout->setContentsMargins(24, 22, 24, 22); heroLayout->setSpacing(28);
    auto *hardware = new QVBoxLayout; hardware->setSpacing(8);
    hardware->addWidget(text(tr("YOUR SYSTEM"), "overviewEyebrow"));
    cpu = text(tr("Reading system details…"), "overviewCpu"); hardware->addWidget(cpu);
    gpu = text({}, "overviewGpu", true); hardware->addWidget(gpu);
    systemMeta = text({}, "overviewSystemMeta", true); hardware->addWidget(systemMeta);
    logs = action(tr("View system logs"), "text-x-log", "overviewLogs");
    hardware->addWidget(logs, 0, Qt::AlignLeft);
    heroLayout->addLayout(hardware, 2);
    auto *memory = new QVBoxLayout; memory->setSpacing(8);
    auto *memoryTop = new QHBoxLayout; memoryTop->addWidget(text(tr("Memory")), 1);
    ramPercent = text("—", "overviewRamPercent"); ramPercent->setProperty("overviewMetric", true); memoryTop->addWidget(ramPercent);
    memory->addLayout(memoryTop); ramBar = meter("overviewRamBar"); memory->addWidget(ramBar);
    ramDetail = text(tr("Checking usage…"), "overviewRamDetail", true); memory->addWidget(ramDetail); memory->addStretch();
    heroLayout->addLayout(memory, 1); body->addWidget(hero);

    grid = new QGridLayout; grid->setSpacing(16); body->addLayout(grid); body->addStretch();
    storageCard = card("overviewStorage"); auto *storage = cardLayout(storageCard, tr("Storage"), "drive-harddisk");
    storage->addWidget(text(tr("Room for what matters"), {}, true));
    volumes = new QVBoxLayout; volumes->setSpacing(18); storage->addLayout(volumes);
    storageMessage = text(tr("Checking disk space…"), "overviewStorageMessage", true); storage->addWidget(storageMessage);
    storage->addStretch(1);
    auto *divider = new QFrame; divider->setFrameShape(QFrame::HLine); divider->setStyleSheet("background:palette(mid);border:none;"); divider->setFixedHeight(1);
    storage->addWidget(divider); storage->addSpacing(2);
    storage->addWidget(text(tr("Drive health"), "overviewHealthTitle"));
    health = text(tr("Checking available health information…"), "overviewHealth", true); storage->addWidget(health);
    drives = action(tr("Manage drives"), "drive-harddisk", "overviewDrives"); storage->addWidget(drives, 0, Qt::AlignLeft);

    servicesCard = card("overviewServices"); auto *services = cardLayout(servicesCard, tr("Services"), "system-run");
    serviceValue = metric("—", "overviewServiceValue"); services->addWidget(serviceValue);
    serviceState = text(tr("Checking services…"), "overviewServiceState"); services->addWidget(serviceState);
    serviceDetail = text({}, "overviewServiceDetail", true); services->addWidget(serviceDetail); services->addStretch();
    manageServices = action(tr("Manage services"), "go-next", "overviewManageServices"); services->addWidget(manageServices, 0, Qt::AlignLeft);

    updatesCard = card("overviewUpdates"); auto *updates = cardLayout(updatesCard, tr("Updates"), "system-software-update");
    updateValue = metric("—", "overviewUpdateValue"); updates->addWidget(updateValue);
    updateState = text(tr("Checking packages…"), "overviewUpdateState"); updates->addWidget(updateState);
    updateDetail = text({}, "overviewUpdateDetail", true); updates->addWidget(updateDetail); updates->addStretch();
    reviewUpdates = action(tr("Review updates"), "go-next", "overviewReviewUpdates"); updates->addWidget(reviewUpdates, 0, Qt::AlignLeft);

    recoveryCard = card("overviewRecovery"); auto *recovery = cardLayout(recoveryCard, tr("Recovery"), "media-optical");
    recoveryState = text(tr("Looking for safety ISOs…"), "overviewRecoveryState"); recoveryState->setProperty("overviewTitle", true); recovery->addWidget(recoveryState);
    recoveryDetail = text({}, "overviewRecoveryDetail", true); recovery->addWidget(recoveryDetail); recovery->addStretch();
    safetyIso = action(tr("Open System ISO"), "go-next", "overviewSafetyIso"); recovery->addWidget(safetyIso, 0, Qt::AlignLeft);
    updated = text(tr("Loading system information…"), "overviewLastUpdated", true); outer->addWidget(updated);
    scroll->viewport()->installEventFilter(this);
    arrange(1100);
  }

  void setBusy(bool busy) {
    refresh->setEnabled(!busy); refresh->setText(busy ? tr("Refreshing…") : tr("Refresh"));
    updated->setText(busy ? tr("Refreshing system information…") : tr("Last refreshed at %1 · Checks run when you open this page or refresh.").arg(QTime::currentTime().toString("HH:mm")));
  }
  void systemResult(const QString &output, bool ok) {
    QMap<QString, QString> values;
    if (ok) for (const auto &line : output.split('\n')) {
      const int colon = line.indexOf(':'); if (colon > 0) values[line.left(colon)] = line.mid(colon + 1).trimmed();
    }
    cpu->setText(values.value("CPU").isEmpty() ? tr("System details unavailable") : values["CPU"]);
    gpu->setText(values.value("GPU")); gpu->setVisible(!gpu->text().isEmpty());
    QStringList meta;
    if (!values.value("KERNEL").isEmpty()) meta << tr("Kernel %1").arg(values["KERNEL"]);
    if (!values.value("UPTIME").isEmpty()) meta << tr("Up %1").arg(values["UPTIME"]);
    systemMeta->setText(meta.join("  ·  "));
    bool valid = false; const int percent = values.value("RAMPCT").toInt(&valid);
    valid = valid && percent >= 0 && percent <= 100;
    ramPercent->setText(valid ? QString::number(percent) + "%" : "—"); ramBar->setVisible(valid);
    if (valid) ramBar->setValue(percent);
    const auto amounts = values.value("RAM").split(' ', Qt::SkipEmptyParts);
    ramDetail->setText(amounts.size() == 2 ? tr("%1 used of %2").arg(amounts[0], amounts[1]) : tr("Memory usage unavailable"));
  }
  void storageResult(const QString &output, bool ok) {
    while (auto *item = volumes->takeAt(0)) { delete item->widget(); delete item; }
    QSet<QString> seen;
    if (ok) for (const auto &line : output.split('\n', Qt::SkipEmptyParts)) {
      const auto parts = line.simplified().split(' '); if (parts.size() != 4 || seen.contains(parts[0])) continue;
      bool valid = false; QString value = parts[3]; value.remove('%'); const int percent = value.toInt(&valid);
      if (!valid || percent < 0 || percent > 100) continue;
      seen.insert(parts[0]); auto *volume = new QWidget; auto *layout = new QVBoxLayout(volume); layout->setContentsMargins(0, 0, 0, 0); layout->setSpacing(7);
      auto *row = new QHBoxLayout;
      row->addWidget(text(parts[0] == "/" ? tr("System · /") : parts[0] == "/home" ? tr("Home · /home") : parts[0]), 1);
      row->addWidget(text(QString::number(percent) + "%")); layout->addLayout(row);
      auto *bar = meter("overviewDiskUsage"); bar->setAccessibleName(tr("Disk usage for %1").arg(parts[0])); bar->setValue(percent); layout->addWidget(bar);
      layout->addWidget(text(tr("%1 used of %2").arg(parts[1], parts[2]), {}, true)); volumes->addWidget(volume);
    }
    storageMessage->setText(tr("Disk space information unavailable")); storageMessage->setVisible(seen.isEmpty());
  }
  void servicesResult(const QString &output, bool ok) {
    int running = -1; QStringList failed;
    if (ok) for (const auto &line : output.split('\n', Qt::SkipEmptyParts)) {
      if (line.startsWith("RUNNING:")) { bool valid = false; int value = line.mid(8).trimmed().toInt(&valid); if (valid && value >= 0) running = value; }
      else if (line.startsWith("FAILED:")) failed << line.mid(7).trimmed();
    }
    if (!ok || running < 0) {
      serviceValue->setText("—"); serviceState->setText(tr("Status unavailable")); serviceDetail->setText(tr("Open Services for details, or try Refresh.")); return;
    }
    serviceValue->setText(QString::number(failed.isEmpty() ? running : failed.size()));
    serviceState->setText(failed.isEmpty() ? tr("Services running") : tr("Failed units need attention"));
    serviceDetail->setText(failed.isEmpty() ? tr("No failed units reported.") : failed.mid(0, 3).join(", ") + (failed.size() > 3 ? tr(" +%1 more").arg(failed.size() - 3) : QString()));
  }
  void updatesResult(const QString &output, int exitCode, bool normal = true) {
    const auto lines = output.split('\n', Qt::SkipEmptyParts);
    if (!normal || (exitCode != 0 && exitCode != 2) || (exitCode == 2 && !lines.isEmpty())) {
      updateValue->setText("—"); updateState->setText(tr("Check unavailable"));
      updateDetail->setText(tr("Open Updates to check the connection and package tools.")); return;
    }
    updateValue->setText(QString::number(lines.size()));
    updateState->setText(lines.isEmpty() ? tr("Packages are up to date") : tr("Package updates available"));
    QStringList names; for (const auto &line : lines) names << line.section(' ', 0, 0);
    updateDetail->setText(lines.isEmpty() ? tr("No pending repository updates.") : names.mid(0, 3).join(", ") + (names.size() > 3 ? tr(" +%1 more").arg(names.size() - 3) : QString()));
  }
  void healthResult(const QString &output, bool ok) {
    const auto result = output.trimmed();
    if (result == "NOAUTH") health->setText(tr("Not checked yet. Open Drives and run Health Check, then refresh here."));
    else if (!ok || result.isEmpty()) health->setText(tr("Health information unavailable. Open Drives to run a health check."));
    else health->setText(result);
  }
  void recoveryResult(const QString &filename, const QString &size, qint64 days) {
    if (filename.isEmpty()) {
      recoveryState->setText(tr("Create your first safety ISO"));
      recoveryDetail->setText(tr("Keep a bootable copy of your system for recovery. Get started in System ISO."));
    } else {
      const auto age = days <= 0 ? tr("today") : days == 1 ? tr("yesterday") : tr("%1 days ago").arg(days);
      recoveryState->setText(tr("Last safety ISO · %1").arg(age));
      recoveryDetail->setText(filename + "\n" + size + (days > 30 ? tr(" · Consider creating a fresh copy.") : QString()));
    }
  }
  QPushButton *refresh, *logs, *drives, *manageServices, *reviewUpdates, *safetyIso;
protected:
  bool eventFilter(QObject *object, QEvent *event) override {
    if (object == scroll->viewport() && event->type() == QEvent::Resize)
      arrange(static_cast<QResizeEvent *>(event)->size().width());
    return QWidget::eventFilter(object, event);
  }
private:
  QLabel *text(const QString &value, const QString &name = {}, bool muted = false) {
    auto *label = new QLabel(value); label->setObjectName(name); label->setTextFormat(Qt::PlainText);
    label->setWordWrap(true); label->setMinimumWidth(0); label->setProperty("overviewMuted", muted);
    label->setTextInteractionFlags(Qt::TextSelectableByMouse); return label;
  }
  QLabel *metric(const QString &value, const QString &name) { auto *label = text(value, name); label->setProperty("overviewMetric", true); return label; }
  QPushButton *action(const QString &caption, const QString &icon, const QString &name) {
    auto *button = new QPushButton(QIcon::fromTheme(icon), caption); button->setObjectName(name); button->setAutoDefault(false); return button;
  }
  QProgressBar *meter(const QString &name) {
    auto *bar = new QProgressBar; bar->setObjectName(name); bar->setRange(0, 100); bar->setValue(0); bar->setTextVisible(false); bar->setFixedHeight(8); return bar;
  }
  QFrame *card(const QString &name) { auto *frame = new QFrame; frame->setObjectName(name); frame->setProperty("overviewCard", true); return frame; }
  QVBoxLayout *cardLayout(QFrame *frame, const QString &title, const QString &icon) {
    auto *layout = new QVBoxLayout(frame); layout->setContentsMargins(22, 20, 22, 20); layout->setSpacing(10);
    auto *row = new QHBoxLayout; row->setSpacing(10);
    auto *image = new QLabel; image->setPixmap(QIcon::fromTheme(icon).pixmap(24, 24)); image->setFixedSize(24, 24); row->addWidget(image);
    auto *caption = text(title); caption->setProperty("overviewTitle", true); row->addWidget(caption, 1); layout->addLayout(row); layout->addSpacing(4); return layout;
  }
  void arrange(int width) {
    const int columns = width >= 1000 ? 3 : width >= 680 ? 2 : 1;
    if (columns == currentColumns) return; currentColumns = columns;
    for (auto *frame : {storageCard, servicesCard, updatesCard, recoveryCard}) grid->removeWidget(frame);
    for (int i = 0; i < 4; ++i) { grid->setColumnStretch(i, 0); grid->setRowStretch(i, 0); }
    if (columns == 3) {
      grid->addWidget(storageCard, 0, 0, 2, 1); grid->addWidget(servicesCard, 0, 1); grid->addWidget(updatesCard, 0, 2); grid->addWidget(recoveryCard, 1, 1, 1, 2);
      grid->setColumnStretch(0, 5); grid->setColumnStretch(1, 4); grid->setColumnStretch(2, 4);
    } else if (columns == 2) {
      grid->addWidget(storageCard, 0, 0, 2, 1); grid->addWidget(servicesCard, 0, 1); grid->addWidget(updatesCard, 1, 1); grid->addWidget(recoveryCard, 2, 0, 1, 2);
      grid->setColumnStretch(0, 1); grid->setColumnStretch(1, 1);
    } else {
      grid->addWidget(storageCard, 0, 0); grid->addWidget(servicesCard, 1, 0); grid->addWidget(updatesCard, 2, 0); grid->addWidget(recoveryCard, 3, 0); grid->setColumnStretch(0, 1);
    }
    heroLayout->setDirection(columns == 1 ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);
    setProperty("overviewColumns", columns);
  }
  int currentColumns = 0;
  QWidget *content; QScrollArea *scroll; QBoxLayout *heroLayout; QGridLayout *grid; QVBoxLayout *volumes;
  QFrame *storageCard, *servicesCard, *updatesCard, *recoveryCard;
  QLabel *cpu, *gpu, *systemMeta, *ramPercent, *ramDetail, *storageMessage, *health, *serviceValue, *serviceState, *serviceDetail, *updateValue, *updateState, *updateDetail, *recoveryState, *recoveryDetail, *updated;
  QProgressBar *ramBar;
};
} // namespace FusionOverview
