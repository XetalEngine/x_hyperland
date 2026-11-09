#pragma once
#include <QtWidgets>

class SearchResults : public QAbstractTableModel {
  Q_OBJECT
public:
  explicit SearchResults(QObject *parent = nullptr)
      : QAbstractTableModel(parent) {}
  int rowCount(const QModelIndex &parent = {}) const override;
  int columnCount(const QModelIndex &parent = {}) const override;
  QVariant data(const QModelIndex &index,
                int role = Qt::DisplayRole) const override;
  QVariant headerData(int section, Qt::Orientation orientation,
                      int role) const override;
  void append(const QJsonArray &batch);
  void clear();
  QJsonObject result(int row) const;

private:
  QList<QJsonObject> rows;
};

class SearchPane : public QWidget {
  Q_OBJECT
public:
  explicit SearchPane(QWidget *parent = nullptr);
  ~SearchPane() override;
  QLineEdit *query;
  QTreeView *results;
  void setLocation(const QUrl &url);
  void focusQuery();
  void start();
  void cancel();
  bool running() const { return process != nullptr; }
  bool handleAction(const QString &id);
  QList<QUrl> selectedUrls() const;
signals:
  void closeRequested();
  void selectionChanged();
  void openRequested(const QUrl &url, bool directory);
  void revealRequested(const QUrl &url);

private:
  QJsonObject options;
  QCheckBox *advanced;
  QPushButton *settingsButton, *searchButton, *stopButton, *exportButton;
  QLabel *scope, *status, *hint, *empty;
  QProgressBar *progress;
  QStackedWidget *pages;
  QProcess *process = nullptr;
  QByteArray output;
  QStringList warnings;
  SearchResults *model;
  QSortFilterProxyModel *proxy;
  void advancedDialog();
  void updateMode();
  void event(const QJsonObject &message);
  void drain();
  void stopProcess();
  void openResult(bool preview = false);
  void revealResult();
  void copyResults(bool pathsOnly);
  void exportResults();
  QJsonObject currentResult() const;
};
