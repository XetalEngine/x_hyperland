#pragma once
#include "drives.h"

class StorageChart;

class DrivePreview : public QScrollArea {
  Q_OBJECT
public:
  explicit DrivePreview(QWidget *parent = nullptr);
  void setVolume(const Volume &volume);
signals:
  void propertiesRequested(const Volume &volume);
protected:
  void changeEvent(QEvent *event) override;
private:
  Volume volume;
  QLabel *art = nullptr, *heading, *status, *hint, *empty;
  QWidget *details;
  StorageChart *chart;
  QMap<QString, QLabel *> metrics, fields;
  void updateIcon();
};

class DriveProperties : public QDialog {
  Q_OBJECT
public:
  DriveProperties(const Volume &volume, Drives *drives,
                  QWidget *parent = nullptr);

private:
  Volume volume;
  bool connected = true;
  StorageChart *chart;
  QLabel *heading, *status, *usageHint;
  QLabel *used, *usedBytes, *free, *freeBytes, *reserved, *reservedBytes;
  QLabel *capacity, *capacityBytes;
  QLabel *device, *physical, *filesystem, *mount, *access, *uuid;
  QWidget *reservedRow;
  QPushButton *open;
  void refresh();
  QString summary() const;
};
