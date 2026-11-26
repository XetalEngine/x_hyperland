#pragma once
#include "aur_search.h"
#include <QProcess>
#include <QTimer>
#include <QWidget>

class QComboBox;
class QLabel;
class QLineEdit;
class QMenu;
class QPlainTextEdit;
class QPushButton;
class QStackedWidget;
class QTableWidget;

class AurPage final : public QWidget {
    Q_OBJECT
public:
    enum class Mode { Helpers, Repositories };
    AurPage(const QString &profileRoot, const QString &terminal, QWidget *parent = nullptr, Mode mode = Mode::Helpers);
    ~AurPage() override;
    void refresh();
    void focusSearch();
signals:
    void clearCacheRequested();
protected:
    void showEvent(QShowEvent *event) override;
private:
    QString root, terminal;
    Mode mode;
    QComboBox *helper, *field, *match;
    QLineEdit *query;
    QLabel *yayStatus, *paruStatus, *status, *resultTitle, *emptyTitle, *emptyHint;
    QPushButton *installYay, *installParu, *search, *install, *remove;
    QMenu *manage;
    QStackedWidget *results;
    QTableWidget *table;
    QPlainTextEdit *details;
    QProcess worker;
    QTimer deadline, poll;
    QList<AurSearch::Package> packages;
    QString searchedQuery;
    QByteArray output, errors;
    bool busy = false, cancelled = false, timedOut = false, tooLarge = false;
    QString selectedHelper() const;
    void refreshHelpers();
    void rebuildMenu();
    void startSearch();
    void finishSearch(int code, QProcess::ExitStatus exit);
    void showResults();
    void updateActions();
    void setStatus(const QString &message, const QString &detail = {});
    void packageAction(bool uninstall);
    void helperAction(const QString &name, const QString &action);
    bool launch(const QStringList &arguments, const QString &message);
};
