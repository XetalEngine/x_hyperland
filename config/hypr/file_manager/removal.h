#pragma once
#include <KJob>
#include <KFileItem>
#include <QtCore>
#include <QPointer>
class QWidget;
namespace Fusion {
class RemovalJob : public KJob {
  Q_OBJECT
public:
  RemovalJob(const QList<QUrl> &urls, bool permanent, QWidget *window);
  RemovalJob(const KFileItemList &items, const QString &operation, QWidget *window);
  void start() override;
signals:
  void removed(const QList<QUrl> &urls);
private:
  QList<QUrl> urls;
  QString operation;
  bool finished = false;
  QPointer<QWidget> window;
  QJsonArray snapshots;
  QProcess process;
  void authenticate(int error, const QString &message);
  void complete(int error, const QString &message);
};
}
