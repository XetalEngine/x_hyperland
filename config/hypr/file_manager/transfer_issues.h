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
class TransferIssuesModel : public QAbstractTableModel {
public:
  explicit TransferIssuesModel(QObject *parent) : QAbstractTableModel(parent) {}
  int rowCount(const QModelIndex &parent = {}) const override { return parent.isValid() ? 0 : rows.size(); }
  int columnCount(const QModelIndex &parent = {}) const override { return parent.isValid() ? 0 : 6; }
  QVariant data(const QModelIndex &index, int role) const override;
  QVariant headerData(int section, Qt::Orientation orientation, int role) const override;
  void update(const QVariantMap &value);
  QVector<QVariantMap> rows;
private:
  QHash<qlonglong, int> positions;
};

// A nonmodal queue belongs to the transfer, not to whichever file failed first.
// Closing it only hides it; the progress card's Review button brings it back.
class TransferIssues : public QDialog {
  Q_OBJECT
public:
  explicit TransferIssues(NativeTransfer *job, QWidget *owner = nullptr);
  void reveal();
private:
  QPointer<NativeTransfer> job;
  TransferIssuesModel *model;
  QSortFilterProxyModel *proxy;
  QTableView *table;
  QLabel *summary, *accessStatus;
  QPlainTextEdit *detail;
  QCheckBox *similar;
  QPushButton *retry, *skip, *replace, *authorize, *cancel;
  bool shown = false, done = false;
  qlonglong pending = 0, automatic = 0;
  QString phase, journal, accessState, accessError;
  void refresh();
  void decide(const QString &choice);
  void saveReport(const QString &path, QPushButton *button);
};
}
