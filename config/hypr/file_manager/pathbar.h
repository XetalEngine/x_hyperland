#pragma once
#include <KUrlComboBox>
#include <QtWidgets>
class KUrlCompletion;

// A location bar whose history includes our virtual This PC view without
// trying to stat it through a filesystem worker.
class PathBar : public QWidget {
  Q_OBJECT
public:
  explicit PathBar(QWidget *parent = nullptr);
  QUrl locationUrl() const;
  void setLocationUrl(const QUrl &url);
  void setSelectedFileUrl(const QUrl &url);
  QUrl displayedUrl() const;
  bool goBack();
  bool goForward();
  bool goUp();
  int historyIndex() const { return position; }
  int historySize() const { return history.size(); }
  bool isUrlEditable() const;
  void setUrlEditable(bool value);
  KUrlComboBox *editor() const { return input; }
  QVariantMap visitState() const { return states.value(position); }
  void setVisitState(const QVariantMap &state) { states[position] = state; }
  QVariantMap session() const;
  void restoreSession(const QVariantMap &session);
signals:
  void aboutToNavigate();
  void urlChanged(const QUrl &url);
  void editingCancelled();
  void historyChanged();
  void tabRequested(const QUrl &url);
  void fileActivated(const QUrl &url);

protected:
  bool eventFilter(QObject *, QEvent *) override;

private:
  QList<QUrl> history;
  QList<QVariantMap> states{QVariantMap{}};
  QUrl selectedFile;
  int position = 0;
  KUrlComboBox *input = nullptr;
  KUrlCompletion *completion;
  void render();
  void submit();
};
