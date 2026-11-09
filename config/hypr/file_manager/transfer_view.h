#pragma once
#include <KJob>
#include <QPointer>
#include <QVariantMap>
#include <functional>

namespace Fusion {
// One JobView for the entire operation, including its questions. Native local
// transfers and remote KIO operations share this presentation and controls.
class TransferView : public QObject {
  Q_OBJECT
public:
  using Answer = std::function<void(const QVariantMap &)>;
  TransferView(KJob *job, const QVariantMap &initial);
  void ask(const QVariantMap &question, Answer answer, std::function<void()> fallback);
  void update(const QVariantMap &data);
signals:
  void reviewRequested();

private slots:
  void cancel();
  void suspend();
  void resume();
  void review();

private:
  QPointer<KJob> job;
  QString path, owner;
  QVariantMap values, question;
  Answer answer;
  std::function<void()> fallback;
  bool ready = false, finished = false, unavailable = false;
  int error = 0;
  QString errorText;
  void flush();
  void sendQuestion();
  void finish(int code, const QString &text);
  void terminate();
};
}
