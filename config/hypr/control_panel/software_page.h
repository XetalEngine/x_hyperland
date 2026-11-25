#pragma once
#include <QProcess>
#include <QSet>
#include <QTimer>
#include <QWidget>

class SoftwareCatalogPage;
class QBoxLayout;
class QLabel;
class QLineEdit;
class QPushButton;
class QScrollArea;
class QTabWidget;
class QTableWidget;
class QTreeWidget;

class SoftwarePage final : public QWidget {
    Q_OBJECT
public:
    SoftwarePage(QWidget *legacy, const QString &root, const QString &terminal, QWidget *parent = nullptr);
    ~SoftwarePage() override;
    void openSection(int index);
    void focusSearch();
public slots:
    void refreshInstalled();
    void filterInstalled();
signals:
    void openTool(const QString &id);
    void installDebRequested(const QString &appId);
protected:
    void showEvent(QShowEvent *event) override;
    bool eventFilter(QObject *object, QEvent *event) override;
private:
    QWidget *legacy;
    QString root, terminal;
    QTabWidget *sections;
    SoftwareCatalogPage *browser;
    QTableWidget *installed;
    QTreeWidget *diagnostics;
    QLabel *count, *space, *foreign, *installedStatus, *diagnosisSource;
    QLineEdit *filter;
    QPushButton *refresh, *remove, *reinstall, *details;
    QScrollArea *repairScroll;
    QBoxLayout *repairColumns;
    QProcess loader;
    QTimer deadline;
    QByteArray output, errors;
    QSet<QString> foreignNames, selectedNames;
    bool loading = false, loaded = false, timedOut = false;
    int stage = 0;
    void refreshSection();
    void runRead(const QStringList &args);
    void readFinished(int code, QProcess::ExitStatus exit);
    void updateActions();
    void syncDiagnosis();
    void syncConfigFiles();
    void showPackageDetails();
    void reinstallPackage();
};
