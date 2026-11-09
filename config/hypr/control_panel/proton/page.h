#pragma once
#include "controller.h"
#include <QtWidgets>

namespace XetalProton {
class Page final : public QWidget {
    Q_OBJECT
public:
    explicit Page(QWidget *parent=nullptr);
    Controller *controller() { return &model; }
    void focusSearch();
    QSize sizeHint() const override { return {1150,720}; }
    QSize minimumSizeHint() const override { return {640,480}; }
protected:
    void showEvent(QShowEvent *event) override;
    void dragEnterEvent(QDragEnterEvent *event) override;
    void dropEvent(QDropEvent *event) override;
private:
    Controller model;
    QTabWidget *tabs, *toolTabs;
    QComboBox *prefixChoice, *protonChoice, *providers, *dependencyCategory;
    QLabel *status, *prefixPath, *providerInfo, *toolNotice, *dependencyInfo, *settingsPaths;
    QProgressBar *progress;
    QPushButton *cancelButton, *older, *download, *removeInstalled, *useInstalled;
    QPushButton *dependencyInstall, *dependencyStop;
    QListWidget *shortcuts;
    QPlainTextEdit *processLog, *events;
    QLineEdit *releaseSearch, *dependencySearch, *librarySearch;
    QStackedWidget *libraryStack;
    QMenu *appMenu;
    QLabel *libraryCount, *emptyTitle, *emptyDescription, *shortcutTitle, *shortcutArtwork;
    QPushButton *emptyAction;
    QCheckBox *prereleases, *incompatible, *launchAdded, *discoverSteam;
    QSpinBox *iconSize;
    QTableWidget *releaseTable, *installedTable, *updateTable, *dependencyTable, *processTable;
    QLabel *shortcutInfo;
    QTimer logTimer;
    bool refreshing=false, firstShow=true;
    std::string selectedShortcut;
    std::map<std::string,bool> launchFeedback;
    QString activeLog;
    QHash<QString,QIcon> iconCache;
    void buildLibrary();
    void buildTools();
    void buildDependencies();
    void buildProcesses();
    void buildSettings();
    void refresh();
    void refreshLibrary();
    void refreshTools();
    void refreshDependencies();
    void refreshProcesses();
    void refreshTask();
    void selectShortcut();
    void filterLibrary();
    void launchApp(std::string id);
    void showCommand();
    void editShortcut(bool browserSignIn=false);
    void managePrefix();
    void addShortcut(bool once=false);
    void exportShortcut();
    void viewLog(const QString &path);
    void readLog();
    void selectDownload();
    void selectDependency();
    void installSelectedDependency();
    bool confirm(const QString &title,const QString &text);
    static void openFolder(const QString &path);
    static void openFile(const QString &path);
    QIcon shortcutIcon(const Shortcut &shortcut);
};
namespace Ui {
QPushButton *button(const QString &text,const QString &name,QBoxLayout *layout,std::function<void()> action);
QIcon icon(const QString &name, QStyle::StandardPixmap fallback=QStyle::SP_FileIcon);
void decorate(QAbstractButton *button,const QString &iconName,const QString &description={},bool iconOnly=false);
QLabel *hint(const QString &text,QBoxLayout *layout);
QTableWidget *table(const QStringList &headers,const QString &name);
void row(QTableWidget *table,int index,const QStringList &values,const QVariant &key={});
QString text(const std::string &value);
}
}
