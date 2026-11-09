#include "transfer_issues.h"
#include "native_transfer.h"
#include "core.h"
#include <QApplication>
#include <QCheckBox>
#include <QClipboard>
#include <QFileDialog>
#include <QFileInfo>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QSaveFile>
#include <QScreen>
#include <QSortFilterProxyModel>
#include <QTableView>
#include <QTimer>
#include <QVBoxLayout>
#include <QMessageBox>
#include <QWindow>
#include <memory>

namespace {
QString stage(const QVariantMap &row) {
  const auto value = row.value("stage").toString();
  return value == "directory_done" ? "Folder attributes" : value == "verify" ? "Verifying copies" :
      value == "precheck" ? "Checking originals" : value == "remove" ? "Removing originals" :
      value == "sync" ? "Saving to disk" : "Copying";
}
QString status(const QVariantMap &row) {
  const auto value = row.value("status").toString();
  return value == "pending" ? "Needs a choice" : value == "retry" ? "Retry queued" :
      value == "authorizing" ? "Awaiting authorization" :
      value == "working" ? "Retrying" : value == "resolved" ? "Resolved" : value == "skipped" ? "Skipped / original kept" : value;
}
QString details(const QVariantMap &row) {
  return row.value("detail").toString() + "\n\nFrom: " + row.value("source").toString() +
      "\nTo: " + row.value("destination").toString() + "\nStage: " + stage(row) + "\nStatus: " + status(row);
}
}

QVariant Fusion::TransferIssuesModel::data(const QModelIndex &index, int role) const {
  if (!index.isValid() || index.row() >= rows.size()) return {};
  const auto &row = rows[index.row()];
  if (role == Qt::ToolTipRole) return details(row);
  if (role == Qt::UserRole) return row.value("id");
  if (role != Qt::DisplayRole) return {};
  switch (index.column()) {
  case 0: return QFileInfo(row.value("source").toString()).fileName();
  case 1: return row.value("detail");
  case 2: return status(row);
  case 3: return row.value("source");
  case 4: return row.value("destination");
  case 5: return stage(row);
  }
  return {};
}
QVariant Fusion::TransferIssuesModel::headerData(int section, Qt::Orientation orientation, int role) const {
  if (orientation != Qt::Horizontal || role != Qt::DisplayRole) return {};
  return QStringList{"Item", "Issue", "Status", "Source", "Destination", "Stage"}.value(section);
}
void Fusion::TransferIssuesModel::update(const QVariantMap &value) {
  const auto id = value.value("id").toLongLong();
  if (!positions.contains(id)) {
    const int row = rows.size(); beginInsertRows({}, row, row);
    positions.insert(id, row); rows.append(value); endInsertRows();
  } else {
    const auto row = positions.value(id); rows[row] = value;
    emit dataChanged(index(row, 0), index(row, columnCount()-1));
  }
}

Fusion::TransferIssues::TransferIssues(NativeTransfer *operation, QWidget *owner) : job(operation) {
  setObjectName("transferIssues"); setWindowTitle("Transfer queue — Fusion Files");
  setWindowRole("fusion-transfer-queue");
  setWindowModality(Qt::NonModal); setAttribute(Qt::WA_ShowWithoutActivating);
  // A native transient relationship makes this a dialog to the compositor,
  // with its own size memory. QObject ownership stays independent: closing
  // the browser must not destroy an active transfer's queue.
  if (owner) {
    owner->winId(); winId();
    windowHandle()->setTransientParent(owner->windowHandle());
  }
  const auto area = (owner ? owner->screen() : screen())->availableGeometry();
  resize(QSize(980, 540).boundedTo(area.size() - QSize(40, 40)));
  auto *layout = new QVBoxLayout(this); layout->setContentsMargins(16, 14, 16, 14); layout->setSpacing(8);
  auto *heading = new QLabel("Items needing attention", this);
  auto font = heading->font(); font.setPointSize(font.pointSize()+4); font.setBold(true); heading->setFont(font);
  layout->addWidget(heading);
  summary = new QLabel(this); summary->setWordWrap(true); summary->setTextFormat(Qt::PlainText); layout->addWidget(summary);
  auto *filter = new QLineEdit(this); filter->setPlaceholderText("Filter the queue by file, path, issue or status…");
  filter->setClearButtonEnabled(true); layout->addWidget(filter);
  model = new TransferIssuesModel(this); proxy = new QSortFilterProxyModel(this);
  proxy->setSourceModel(model); proxy->setFilterKeyColumn(-1); proxy->setFilterCaseSensitivity(Qt::CaseInsensitive);
  table = new QTableView(this); table->setObjectName("transferIssuesTable"); table->setModel(proxy);
  table->setSelectionBehavior(QAbstractItemView::SelectRows); table->setSelectionMode(QAbstractItemView::ExtendedSelection);
  table->setEditTriggers(QAbstractItemView::NoEditTriggers); table->setAlternatingRowColors(true);
  table->setWordWrap(false); table->setSortingEnabled(true); table->sortByColumn(-1, Qt::AscendingOrder);
  table->verticalHeader()->hide(); table->verticalHeader()->setDefaultSectionSize(30);
  table->horizontalHeader()->setStretchLastSection(true);
  const int widths[] = {130, 210, 155, 160, 160, 100};
  for (int col = 0; col < 6; ++col) table->setColumnWidth(col, widths[col]);
  layout->addWidget(table, 1);
  detail = new QPlainTextEdit(this); detail->setReadOnly(true); detail->setMaximumHeight(96);
  detail->setPlaceholderText("Select a row to see the full error and paths. You can select several rows at once."); layout->addWidget(detail);
  similar = new QCheckBox("Apply to all queued items with the same issue (Skip also applies to later matches)", this);
  similar->setObjectName("similarTransferIssues"); layout->addWidget(similar);
  accessStatus = new QLabel(this); accessStatus->setObjectName("transferAdministratorStatus");
  accessStatus->setWordWrap(true); accessStatus->setTextFormat(Qt::PlainText); layout->addWidget(accessStatus);
  auto *buttons = new QHBoxLayout; layout->addLayout(buttons);
  auto action = [&](const QString &text, const QString &choice) {
    auto *button = new QPushButton(text, this); button->setObjectName("transferIssue_" + choice); button->setAutoDefault(false);
    buttons->addWidget(button); connect(button, &QPushButton::clicked, this, [this, choice] { decide(choice); }); return button;
  };
  retry = action("Retry", "retry"); skip = action("Skip", "skip"); replace = action("Replace…", "replace");
  authorize = action("Use administrator access…", "authorize");
  buttons->addStretch();
  auto *save = new QPushButton("Save report…", this); save->setObjectName("saveTransferReport"); buttons->addWidget(save);
  cancel = new QPushButton("Cancel transfer", this); cancel->setObjectName("cancelQueuedTransfer"); buttons->addWidget(cancel);
  auto *hide = new QPushButton("Hide", this); buttons->addWidget(hide);
  connect(hide, &QPushButton::clicked, this, [this] { if (done) close(); else this->hide(); });
  connect(cancel, &QPushButton::clicked, this, [this] { if (job) job->kill(KJob::EmitResult); });
  connect(filter, &QLineEdit::textChanged, proxy, &QSortFilterProxyModel::setFilterFixedString);
  connect(table->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this] { refresh(); });
  connect(save, &QPushButton::clicked, this, [this, save] {
    const auto path = QFileDialog::getSaveFileName(this, "Save transfer report", "transfer-report.txt", "Text files (*.txt)");
    if (path.isEmpty()) return;
    saveReport(path, save);
  });
  // Batch visual updates, while the model keeps every row and exact status.
  auto *refreshTimer = new QTimer(this); refreshTimer->setSingleShot(true); refreshTimer->setInterval(100);
  connect(refreshTimer, &QTimer::timeout, this, [this] { refresh(); });
  connect(job, &NativeTransfer::issue, this, [this, refreshTimer](const QVariantMap &value) {
    if (job) journal = job->journal();
    model->update(value);
    if (model->rows.size() == 1 && table->selectionModel()->selectedRows().isEmpty()) table->selectRow(0);
    if (!refreshTimer->isActive()) refreshTimer->start();
    if (!shown) { shown = true; show(); }
  });
  connect(job, &NativeTransfer::progress, this, [this](const QVariantMap &value) {
    if (value.contains("pendingIssues")) pending = value.value("pendingIssues").toLongLong();
    if (value.contains("autoSkippedIssues")) automatic = value.value("autoSkippedIssues").toLongLong();
    if (value.contains("phase")) phase = value.value("phase").toString();
    if (value.contains("administratorAccess")) accessState = value.value("administratorAccess").toString();
    if (value.contains("administratorError")) accessError = value.value("administratorError").toString();
    refresh();
  });
  connect(job, &KJob::finished, this, [this, hide] {
    for (int row=0; row<model->rows.size(); ++row) {
      auto value = model->rows[row];
      const auto state = value.value("status").toString();
      if (state == "pending" || state == "authorizing" || state == "retry" || state == "working") {
        value["status"] = "Unresolved / original kept"; model->update(value);
      }
    }
    done = true; refresh(); hide->setText("Close"); setAttribute(Qt::WA_DeleteOnClose);
    if (model->rows.isEmpty()) deleteLater(); else show();
  });
  refresh();
}

void Fusion::TransferIssues::reveal() { show(); raise(); activateWindow(); }
void Fusion::TransferIssues::refresh() {
  auto caption = done ? QString("Transfer ended. Completed copies are kept; skipped or unresolved originals remain in place.") :
      phase == "Waiting for queued items" ? QString("All other work is finished. %1 queued items still need a choice. Originals remain safe.").arg(pending) :
      QString("The transfer continues while this queue is open. %1 items need attention. Retries run after the current pass; skipped originals stay in place.").arg(pending);
  if (automatic) caption += QString("\n%1 additional matching items skipped automatically. Save report includes every path.").arg(automatic);
  summary->setText(caption);
  accessStatus->setText(accessState == "authorizing" ?
      "Complete the system authentication prompt. Other files keep copying; protected items will retry after this pass." :
      accessState == "authorized" ? "Administrator access is active for this transfer. No further password is needed for this session." :
      accessState == "failed" ? "Administrator access was not granted. " + accessError : QString());
  accessStatus->setVisible(!done && !accessStatus->text().isEmpty());
  bool selected = false, canReplace = true, canAuthorize = true;
  const auto indexes = table->selectionModel()->selectedRows();
  for (const auto &index : indexes) {
    const auto &row = model->rows[proxy->mapToSource(index).row()];
    if (row.value("status") != "pending") continue;
    selected = true; canReplace &= row.value("replace_allowed").toBool();
    canAuthorize &= row.value("category").toString().endsWith(":permission");
  }
  retry->setEnabled(selected && !done); skip->setEnabled(selected && !done);
  replace->setEnabled(selected && canReplace && !done); authorize->setEnabled(selected && canAuthorize && !done);
  cancel->setEnabled(!done && job); similar->setEnabled(!done);
  if (!indexes.isEmpty()) {
    const auto text = details(model->rows[proxy->mapToSource(indexes.first()).row()]);
    if (detail->toPlainText() != text) detail->setPlainText(text);
  }
}
void Fusion::TransferIssues::decide(const QString &choice) {
  if (!job || done) return;
  QVariantList ids;
  QVariantMap versions;
  for (const auto &index : table->selectionModel()->selectedRows()) {
    const auto &row = model->rows[proxy->mapToSource(index).row()];
    if (row.value("status") == "pending") {
      ids.append(row.value("id")); versions[row.value("id").toString()] = row.value("version");
    }
  }
  if (ids.isEmpty()) return;
  if (choice == "replace" && QMessageBox::question(this, "Replace destination files?",
      similar->isChecked() ? "Replace the destination files for all currently queued conflicts of this type?" :
                             "Replace the destination files for the selected conflicts?",
      QMessageBox::Yes | QMessageBox::No, QMessageBox::No) != QMessageBox::Yes) return;
  job->resolve({{"ids", ids}, {"versions", versions}, {"choice", choice}, {"all", similar->isChecked()}});
}
void Fusion::TransferIssues::saveReport(const QString &path, QPushButton *button) {
  auto file = std::make_shared<QSaveFile>(path);
  if (!file->open(QIODevice::WriteOnly)) { QMessageBox::warning(this,"Could not save report",file->errorString()); return; }
  auto *process = new QProcess(this);
  const auto control = QPointer<QPushButton>(button);
  if (control) { control->setEnabled(false); control->setText("Saving…"); }
  auto failed = std::make_shared<bool>(false);
  auto read = [process, file, failed] {
    const auto chunk = process->readAllStandardOutput();
    if (file->write(chunk) != chunk.size()) { *failed = true; process->kill(); }
  };
  connect(process, &QProcess::readyReadStandardOutput, this, read);
  auto finish = [this, process, file, failed, control, read](bool success) {
    read();
    if (!success || *failed || !file->commit()) {
      file->cancelWriting();
      const auto message = *failed ? file->errorString() : QString::fromUtf8(process->readAllStandardError());
      QMessageBox::warning(this,"Could not save report",message.isEmpty()?"The report could not be saved.":message);
    }
    if (control) { control->setEnabled(true); control->setText("Save report…"); }
    process->deleteLater();
  };
  connect(process, &QProcess::finished, this, [finish](int code,QProcess::ExitStatus status){ finish(code==0 && status==QProcess::NormalExit); });
  connect(process, &QProcess::errorOccurred, this, [finish](QProcess::ProcessError error){ if(error==QProcess::FailedToStart) finish(false); });
  process->start("/usr/bin/python3", {"-I", Fusion::root()+"/file_manager/transfer_pending.py", "--report", journal});
}
