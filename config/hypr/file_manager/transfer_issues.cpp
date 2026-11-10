#include "transfer_issues.h"
#include "native_transfer.h"
#include "transfer_view.h"
#include "core.h"
#include <QApplication>
#include <QCheckBox>
#include <QClipboard>
#include <QFileDialog>
#include <QFileInfo>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QLocale>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QSaveFile>
#include <QScreen>
#include <QSortFilterProxyModel>
#include <QStyle>
#include <QTableView>
#include <QTimer>
#include <QVBoxLayout>
#include <QMessageBox>
#include <QWindow>
#include <KIO/Global>
#include <memory>

namespace {
QString stage(const QVariantMap &row) {
  const auto value = row.value("stage").toString();
  return value == "directory_done" ? "Folder attributes" : value == "verify" ? "Verifying copies" :
      value == "precheck" ? "Checking originals" : value == "remove" ? "Removing originals" :
      value == "sync" ? "Saving to disk" : value == "rescan" ? "Reading folder" : "Copying";
}
QString status(const QVariantMap &row) {
  const auto value = row.value("status").toString();
  return value == "pending" ? "Needs a choice" : value == "retry" ? "Retry queued" :
      value == "authorizing" ? "Awaiting authorization" :
      value == "working" ? "Retrying" : value == "resolved" ? row.value("resolution", "Step completed").toString() :
      value == "skipped" ? "Skipped / original kept" : value == "unresolved" ? "Unresolved / original kept" : value;
}
QString details(const QVariantMap &row) {
  const bool resolved = row.value("status") == "resolved";
  return status(row) + "\n" + (resolved ? "Original issue: " : "Issue: ") + row.value("detail").toString() +
      "\n\nFrom: " + row.value("source").toString() + "\nTo: " + row.value("destination").toString() +
      "\nStage: " + stage(row);
}
bool canRetry(const QVariantMap &row) {
  // Also recognize a queue from a worker started before this update.
  const auto kind = row.value("category").toString().section(':', -1);
  return row.value("retry_allowed", true).toBool() &&
      !QStringList{"socket", "named pipe", "device", "special file"}.contains(kind);
}
QString number(qlonglong value) { return QLocale().toString(value); }
QString items(qlonglong value) { return number(value) + (value == 1 ? " item" : " items"); }
QString files(qlonglong value) { return number(value) + (value == 1 ? " file" : " files"); }
}

QVariant Fusion::TransferIssuesModel::data(const QModelIndex &index, int role) const {
  if (!index.isValid() || index.row() >= rows.size()) return {};
  const auto &row = rows[index.row()];
  if (role == Qt::ToolTipRole) return details(row);
  if (role == Qt::UserRole) return row.value("id");
  if (role == Qt::DecorationRole && index.column() == 2 && row.value("status") == "resolved")
    return QApplication::style()->standardIcon(QStyle::SP_DialogApplyButton);
  if (role == Qt::FontRole && index.column() == 2 && row.value("status") == "resolved") {
    QFont font; font.setBold(true); return font;
  }
  if (role != Qt::DisplayRole) return {};
  switch (index.column()) {
  case 0: return QFileInfo(row.value("source").toString()).fileName();
  case 1: return row.value("status") == "resolved" ? QVariant("Completed after retry") : row.value("detail");
  case 2: return status(row);
  case 3: return row.value("source");
  case 4: return row.value("destination");
  case 5: return stage(row);
  }
  return {};
}
QVariant Fusion::TransferIssuesModel::headerData(int section, Qt::Orientation orientation, int role) const {
  if (orientation != Qt::Horizontal || role != Qt::DisplayRole) return {};
  return QStringList{"Item", "Result / issue", "Status", "Source", "Destination", "Stage"}.value(section);
}
void Fusion::TransferIssuesModel::update(const QVariantMap &value) {
  const auto id = value.value("id").toLongLong();
  if (!positions.contains(id)) {
    const int row = rows.size(); beginInsertRows({}, row, row);
    positions.insert(id, row); rows.append(value); ++counts[value.value("status").toString()]; endInsertRows();
  } else {
    const auto row = positions.value(id);
    --counts[rows[row].value("status").toString()]; ++counts[value.value("status").toString()]; rows[row] = value;
    emit dataChanged(index(row, 0), index(row, columnCount()-1));
  }
}

Fusion::TransferIssues::TransferIssues(NativeTransfer *operation, QWidget *owner, TransferView *progress)
    : job(operation), view(progress), bridgeChecked(!progress) {
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
  heading = new QLabel("Items needing attention", this); heading->setObjectName("transferQueueHeading");
  auto font = heading->font(); font.setPointSize(font.pointSize()+4); font.setBold(true); heading->setFont(font);
  layout->addWidget(heading);
  summary = new QLabel(this); summary->setObjectName("transferQueueSummary");
  summary->setWordWrap(true); summary->setTextFormat(Qt::PlainText); layout->addWidget(summary);
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
  const int widths[] = {130, 180, 190, 150, 150, 100};
  for (int col = 0; col < 6; ++col) table->setColumnWidth(col, widths[col]);
  layout->addWidget(table, 1);
  detail = new QPlainTextEdit(this); detail->setObjectName("transferIssueDetails"); detail->setReadOnly(true); detail->setMaximumHeight(96);
  detail->setPlaceholderText("Select a row to see the full error and paths. You can select several rows at once."); layout->addWidget(detail);
  similar = new QCheckBox("Apply to all queued items with the same issue (Skip also applies to later matches)", this);
  similar->setObjectName("similarTransferIssues"); layout->addWidget(similar);
  actionHint = new QLabel(this); actionHint->setObjectName("transferIssueHint");
  actionHint->setWordWrap(true); actionHint->setTextFormat(Qt::PlainText); layout->addWidget(actionHint);
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
  connect(similar, &QCheckBox::toggled, this, [this] { refresh(); });
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
    publish(value);
    if (model->rows.size() == 1 && table->selectionModel()->selectedRows().isEmpty()) table->selectRow(0);
    if (!refreshTimer->isActive()) refreshTimer->start();
    if (!shown && bridgeChecked && !embedded) { shown = true; show(); }
  });
  connect(job, &NativeTransfer::progress, this, [this](const QVariantMap &value) {
    if (value.contains("processedFiles")) { copied = value.value("processedFiles").toLongLong(); countsKnown = true; }
    if (value.contains("skippedFiles")) skipped = value.value("skippedFiles").toLongLong();
    if (value.contains("renamedItems")) renamed = value.value("renamedItems").toLongLong();
    if (value.contains("autoSkippedIssues")) automatic = value.value("autoSkippedIssues").toLongLong();
    if (value.contains("phase")) phase = value.value("phase").toString();
    if (value.contains("administratorAccess")) accessState = value.value("administratorAccess").toString();
    if (value.contains("administratorError")) accessError = value.value("administratorError").toString();
    refresh();
  });
  connect(job, &KJob::finished, this, [this, hide](KJob *finishedJob) {
    finishCode = finishedJob->error();
    for (int row=0; row<model->rows.size(); ++row) {
      auto value = model->rows[row];
      const auto state = value.value("status").toString();
      if (state == "pending" || state == "authorizing" || state == "retry" || state == "working") {
        value["status"] = "unresolved"; model->update(value); publish(value);
      } else if (state == "resolved" && value.value("resolution") == "Copied; move pending") {
        value["resolution"] = "Copied; original kept"; model->update(value); publish(value);
      }
    }
    done = true; refresh(); hide->setText("Close"); setAttribute(Qt::WA_DeleteOnClose);
    if (model->rows.isEmpty() || embedded) deleteLater(); else if (bridgeChecked) show();
  });
  if (view) {
    connect(view, &TransferView::queueReady, this, [this](bool available) {
      bridgeChecked = true; embedded = available;
      if (available) { this->hide(); if (done) deleteLater(); }
      else if (!model->rows.isEmpty()) { shown = true; show(); }
    });
    connect(view, &TransferView::queueDecision, operation, &NativeTransfer::resolve);
    view->enableQueue();
  }
  refresh();
}

void Fusion::TransferIssues::publish(const QVariantMap &row) {
  if (!view) return;
  auto value = row;
  value["id"] = row.value("id").toLongLong();
  value["version"] = row.value("version").toLongLong();
  value["name"] = QFileInfo(row.value("source").toString()).fileName();
  value["statusText"] = status(row);
  value["resultText"] = row.value("status") == "resolved" ? QString("Completed after retry") : row.value("detail").toString();
  value["details"] = details(row);
  value["retry_allowed"] = canRetry(row);
  view->updateQueue(value);
}
void Fusion::TransferIssues::reveal() {
  if (embedded && view) { view->updateQueue({}, {{"reveal", true}}); return; }
  if (bridgeChecked) { show(); raise(); activateWindow(); }
}
void Fusion::TransferIssues::refresh() {
  const auto pending = model->count("pending"), retrying = model->count("retry") + model->count("working") + model->count("authorizing");
  const auto resolved = model->count("resolved"), skippedCount = qMax(skipped, model->count("skipped") + automatic);
  QString caption;
  if (done) {
    heading->setText(finishCode == KIO::ERR_USER_CANCELED ? "Transfer canceled" : finishCode ? "Transfer stopped" :
                     skippedCount ? "Completed with skipped items" : "Transfer complete");
    if (countsKnown) caption = files(copied) + " copied";
    if (renamed) caption += (caption.isEmpty() ? "" : " · ") + items(renamed) + " moved directly";
    if (resolved) caption += (caption.isEmpty() ? "" : " · ") + items(resolved) + " completed from the queue";
    if (skippedCount) caption += (caption.isEmpty() ? "" : " · ") + items(skippedCount) + " skipped";
    caption += "\nCompleted copies are kept. Skipped and unresolved originals remain in place.";
  } else {
    heading->setText(pending || retrying ? "Items needing attention" : "Finishing transfer");
    if (pending) caption = items(pending) + (pending == 1 ? " needs a choice. " : " need a choice. ");
    if (retrying) caption += items(retrying) + " queued for retry. ";
    if (resolved) caption += items(resolved) + " completed from the queue. ";
    caption += phase == "Waiting for queued items" ? "Choose an action to continue the remaining steps." :
        phase == "Saving folder attributes" ? "Saving folder attributes…" :
        pending || retrying ? "Other files keep copying; retries run after the current pass." :
        "Completing the remaining steps…";
  }
  if (automatic) caption += QString("\n%1 additional matching items skipped automatically. Save report includes every path.").arg(automatic);
  summary->setText(caption);
  accessStatus->setText(accessState == "authorizing" ?
      "Complete the system authentication prompt. Other files keep copying; protected items will retry after this pass." :
      accessState == "authorized" ? "Administrator access is active for this transfer. No further password is needed for this session." :
      accessState == "failed" ? "Administrator access was not granted. " + accessError : QString());
  accessStatus->setVisible(!done && !accessStatus->text().isEmpty());
  int selected = 0;
  bool canReplace = true, canAuthorize = true, retryable = true;
  const auto indexes = table->selectionModel()->selectedRows();
  for (const auto &index : indexes) {
    const auto &row = model->rows[proxy->mapToSource(index).row()];
    if (row.value("status") != "pending") continue;
    ++selected; canReplace &= row.value("replace_allowed").toBool(); retryable &= canRetry(row);
    canAuthorize &= row.value("category").toString().endsWith(":permission");
  }
  retry->setEnabled(selected && retryable && !done); skip->setEnabled(selected && !done);
  skip->setText(selected && similar->isChecked() ? "Skip similar" : selected > 1 ? "Skip selected" : "Skip item");
  replace->setEnabled(selected && canReplace && !done); authorize->setEnabled(selected && canAuthorize && !done);
  authorize->setText(accessState == "authorized" ? "Retry as administrator" : "Use administrator access…");
  actionHint->setText(!retryable ? "Runtime endpoints cannot be copied. Skip keeps the originals; completed copies are kept." :
      similar->isChecked() ? "Actions affect unfinished items with the same issue. Completed copies are kept." :
      "Actions affect only the selected unfinished items. Completed copies are kept.");
  actionHint->setVisible(selected && !done);
  cancel->setEnabled(!done && job); similar->setEnabled(!done);
  if (!indexes.isEmpty()) {
    const auto text = details(model->rows[proxy->mapToSource(indexes.first()).row()]);
    if (detail->toPlainText() != text) detail->setPlainText(text);
  } else detail->clear();
  if (view) view->updateQueue({}, {{"heading", heading->text()}, {"summary", summary->text()},
      {"done", done}, {"access", accessState}, {"accessText", done ? QString() : accessStatus->text()}, {"journal", journal}});
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
