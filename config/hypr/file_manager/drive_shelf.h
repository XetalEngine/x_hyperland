#pragma once
#include "core.h"
#include "drives.h"

class VolumeCard : public QFrame {
  Q_OBJECT
public:
  explicit VolumeCard(QWidget *parent = nullptr);
  Volume volume() const { return current; }
  void setVolume(const Volume &volume);
  void setSelected(bool selected);
  void setListMode(bool list);
signals:
  void selected();
  void openRequested();
  void mountRequested();
  void stepRequested(int step);
protected:
  void mousePressEvent(QMouseEvent *) override;
  void mouseDoubleClickEvent(QMouseEvent *) override;
  void keyPressEvent(QKeyEvent *) override;
  void focusInEvent(QFocusEvent *) override;
  void focusOutEvent(QFocusEvent *) override;
  void enterEvent(QEnterEvent *) override;
  void leaveEvent(QEvent *) override;
  void resizeEvent(QResizeEvent *) override;
  void changeEvent(QEvent *) override;
  bool eventFilter(QObject *, QEvent *) override;
private:
  Volume current;
  QLabel *art = nullptr, *name, *description, *space, *status;
  QProgressBar *usage;
  QPushButton *mount;
  QWidget *metrics;
  QHBoxLayout *row;
  QVBoxLayout *identity;
  bool listMode = false, compact = false;
  void updateMount();
  void updateLayout();
};

class DriveShelf : public QWidget {
  Q_OBJECT
public:
  DriveShelf(Fusion::Preferences *preferences, Drives *drives, QWidget *parent = nullptr);
  void refresh();
  Volume selectedVolume() const;
  void selectDevice(const QString &device, bool focus = false);
  QVariantMap place() const;
  void restorePlace(const QVariantMap &state);
signals:
  void operationRequested(const Volume &volume, const QString &operation);
  void volumeContextRequested(const Volume &volume, const QPoint &position);
  void backgroundContextRequested(const QPoint &position);
protected:
  bool eventFilter(QObject *, QEvent *) override;
  void changeEvent(QEvent *) override;
private:
  Fusion::Preferences *preferences;
  Drives *drives;
  QScrollArea *scroll;
  QWidget *body = nullptr;
  QGridLayout *grid;
  QLabel *empty;
  QToolButton *shelfButton = nullptr, *listButton = nullptr;
  struct Group {
    QFrame *frame;
    QLabel *art, *name, *description;
    QCheckBox *automatic;
    QVBoxLayout *dataLayout, *systemLayout;
    QWidget *systemBody;
    QToolButton *disclosure;
  };
  QMap<QString, Group> groups;
  QMap<QString, VolumeCard *> cards;
  QStringList order;
  QString selected;
  int columns = 0;
  bool layoutQueued = false, topologyChanged = false;
  QString expansionKey(const QString &drive) const;
  void queueLayout();
  void relayout();
  void step(VolumeCard *from, int delta);
};
