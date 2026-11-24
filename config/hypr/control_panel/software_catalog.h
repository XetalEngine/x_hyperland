#pragma once
#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
#include <QProcess>
#include <QTimer>
#include <QVector>
#include <QWidget>

class QCheckBox;
class QLabel;
class QLineEdit;
class QListView;
class QTreeWidget;
class QTreeWidgetItem;
class QStackedWidget;
class QSplitter;
class SoftwareAppModel;

struct SoftwareApp {
    QString id, package, name, summary, description, icon, cachedIcon, source, repository,
            version, installedVersion, license, website, desktopFile, searchText, action, accent, tagline;
    QStringList categories;
    int featuredOrder=100;
    bool installed=false, available=false, featured=false, essential=false;
    static SoftwareApp fromJson(const QJsonObject &value, const QString &root);
};

class SoftwareCatalogPage final : public QWidget {
    Q_OBJECT
public:
    SoftwareCatalogPage(const QString &root, const QString &terminal, QWidget *parent=nullptr);
    ~SoftwareCatalogPage() override;
    void refresh();
    void focusSearch();
signals:
    void openTool(const QString &id);
    void packagesChanged();
protected:
    void showEvent(QShowEvent *event) override;
    bool eventFilter(QObject *object,QEvent *event) override;
private:
    QString root, terminal, category="top", aurQuery, aurResultsQuery;
    QTreeWidget *tree;
    QLineEdit *search;
    QCheckBox *pacman, *yay, *paru;
    QLabel *heading, *subtitle, *count, *notice, *cacheStatus, *empty;
    QListView *grid;
    SoftwareAppModel *model;
    QStackedWidget *results;
    QSplitter *splitter;
    QVector<SoftwareApp> apps, aurApps;
    QJsonObject installedPackages;
    QProcess localWorker, aurWorker;
    QTimer filterDelay, aurDelay, localDeadline, aurDeadline;
    QByteArray localBuffer, aurBuffer;
    QDateTime lastRead;
    bool loaded=false, pendingRefresh=false, aurForcePending=false;
    void buildTree(const QJsonArray &categories);
    void addCategory(const QJsonObject &value,QTreeWidgetItem *parent=nullptr);
    void requestCatalog(bool force=false);
    void receiveCatalog();
    void applyCatalog(const QJsonObject &value);
    void refilter(bool resetScroll=false);
    void sourceChanged();
    void requestAur(bool force=false);
    void finishAur(int code,QProcess::ExitStatus status);
    QString aurHelper() const;
    QString actionText(const SoftwareApp &app) const;
    void details(const SoftwareApp &app);
    void activate(const SoftwareApp &app);
    void vendorDownloads(const SoftwareApp &app);
    void fitGrid();
};
