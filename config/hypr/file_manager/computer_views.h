#pragma once
#include "core.h"
#include "drives.h"

class ComputerItem;

// Alternate presentations of the same drive inventory. All operations are
// routed back to DriveShelf; drawing a view never mounts or scans a volume.
class WindowsComputerView : public QScrollArea {
  Q_OBJECT
public:
  explicit WindowsComputerView(Fusion::Preferences *preferences, QWidget *parent = nullptr);
  void refresh(const QString &mode, const QList<Volume> &volumes,
               const QMap<QString, int> &categories);
  bool containsDevice(const QString &device) const;
  void selectDevice(const QString &device, bool focus = false);
signals:
  void volumeSelected(const QString &device);
  void operationRequested(const Volume &volume, const QString &operation);
  void volumeContextRequested(const Volume &volume, const QPoint &position);
  void backgroundContextRequested(const QPoint &position);
  void locationRequested(const QUrl &url);
  void controlPanelRequested();
protected:
  bool eventFilter(QObject *object, QEvent *event) override;
private:
  Fusion::Preferences *preferences;
  QWidget *body, *information, *content;
  QLabel *infoName, *infoDetails, *emptyMessage;
  struct Section {
    QWidget *body, *items;
    QAbstractButton *heading;
    QGridLayout *grid;
    QStringList keys;
    int columns = 1;
  };
  QMap<int, Section> sections;
  QMap<QString, ComputerItem *> items;
  QString mode, settingsMode, selected;
  bool themed = false;
  void applyAppearance();
  void relayout();
  void choose(const QString &key, bool notify);
  void activate(const QString &key);
  void step(const QString &key, int direction);
};
