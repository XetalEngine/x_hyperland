#pragma once

#include <QJsonObject>
#include <QWidget>

class QGridLayout;
class QPushButton;

class DebInstallerPage final : public QWidget {
public:
  DebInstallerPage(const QString &profileRoot, QPushButton *install,
                   QPushButton *installYay, QPushButton *installParu,
                   QWidget *parent = nullptr);

protected:
  bool eventFilter(QObject *watched, QEvent *event) override;

private:
  QString root;
  QJsonObject contacts;
  QWidget *appGrid = nullptr;
  QWidget *appViewport = nullptr;
  QGridLayout *grid = nullptr;
  QList<QPushButton *> cards;
  int columns = 0;
  void arrangeCards();
  void feedback();
};
