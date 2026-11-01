#pragma once
#include <KFileItem>
#include <QtWidgets>
class KJob;

namespace Fusion {
class ApplicationDialog : public QDialog {
  Q_OBJECT
public:
  explicit ApplicationDialog(const KFileItemList &items, QWidget *parent = nullptr);
  QJsonObject request() const;
private:
  QProcess loader;
  QLineEdit *search, *command;
  QListWidget *apps;
  QCheckBox *remember, *terminal;
  QLabel *status;
  QPushButton *open;
  QJsonArray entries;
  QString revision, mime;
  void filter();
  void updateChoice();
};
KJob *launchApplication(QJsonObject request, QWidget *parent);
}
