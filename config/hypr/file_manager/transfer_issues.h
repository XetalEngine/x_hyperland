#pragma once
#include <QAbstractTableModel>
#include <QDialog>
#include <QPointer>
#include <QVariantMap>

class QLabel;
class QTableView;
class QSortFilterProxyModel;
class QPlainTextEdit;
class QCheckBox;
class QPushButton;

namespace Fusion {
class NativeTransfer;
class TransferView;
class TransferIssuesModel : public QAbstractTableModel {
public:
  explicit TransferIssuesModel(QObject *parent) : QAbstractTableModel(parent) {}
  int rowCount(const QModelIndex &parent = {}) const override { return parent.isValid() ? 0 : rows.size(); }
  int columnCount(const QModelIndex &parent = {}) const override { return parent.isValid() ? 0 : 6; }
  QVariant data(const QModelIndex &index, int role) const override;
  QVariant headerData(int section, Qt::Orientation orientation, int role) const override;
  void update(const QVariantMap &value);
  qlonglong count(const QString &state) const { return counts.value(state); }
  QVector<QVariantMap> rows;
private:
  QHash<qlonglong, int> positions;
  QHash<QString, qlonglong> counts;
};

// A nonmodal queue belongs to the transfer, not to whichever file failed first.
// Closing it only hides it; the progress card's Review button brings it back.
class TransferIssues : public QDialog {
  Q_OBJECT
public:
  explicit TransferIssues(NativeTransfer *job, QWidget *owner = nullptr, TransferView *view = nullptr);
  void reveal();
private:
  QPointer<NativeTransfer> job;
  QPointer<TransferView> view;
  bool bridgeChecked = false, embedded = false;
  TransferIssuesModel *model;
  QSortFilterProxyModel *proxy;
  QTableView *table;
  QLabel *heading, *summary, *accessStatus, *actionHint;
  QPlainTextEdit *detail;
  QCheckBox *similar;
  QPushButton *retry, *skip, *replace, *authorize, *cancel;
  bool shown = false, done = false;
  bool countsKnown = false;
  int finishCode = 0;
  qlonglong copied = 0, skipped = 0, renamed = 0, automatic = 0;
  QString phase, journal, accessState, accessError;
  void refresh();
  void publish(const QVariantMap &row);
  void decide(const QString &choice);
  void saveReport(const QString &path, QPushButton *button);
};
}
