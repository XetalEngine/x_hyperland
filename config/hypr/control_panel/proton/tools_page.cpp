#include "page.h"
#include "src/util.h"
#include <QDesktopServices>

namespace XetalProton {
using namespace Ui;
void Page::buildTools() {
    toolTabs=new QTabWidget;toolTabs->setObjectName("protonToolTabs");tabs->addTab(toolTabs,"Downloads");
    auto *catalog=new QWidget;auto *layout=new QVBoxLayout(catalog);auto *top=new QHBoxLayout;
    providers=new QComboBox;providers->setObjectName("protonProviders");for(const auto &p:toolstore::providers())providers->addItem(text(p.name),text(p.id));top->addWidget(providers,1);
    button("Load releases","protonLoadReleases",top,[this]{model.loadReleases(1);});
    button("Upstream website","protonUpstream",top,[this]{QDesktopServices::openUrl(QUrl(text(toolstore::provider(model.provider).website)));});layout->addLayout(top);
    providerInfo=hint(text(toolstore::provider(model.provider).description),layout);
    auto *filters=new QHBoxLayout;releaseSearch=new QLineEdit;releaseSearch->setObjectName("protonReleaseSearch");releaseSearch->setPlaceholderText("Search versions or variants…");filters->addWidget(releaseSearch,1);
    prereleases=new QCheckBox("Prereleases");incompatible=new QCheckBox("Show incompatible builds");filters->addWidget(prereleases);filters->addWidget(incompatible);layout->addLayout(filters);
    releaseTable=table({"Version","Variant / archive","Size","Status"},"protonReleases");releaseTable->setColumnWidth(0,185);releaseTable->setColumnWidth(1,365);releaseTable->setColumnWidth(2,100);layout->addWidget(releaseTable,1);
    auto *actions=new QHBoxLayout;download=button("Download and install","protonDownload",actions,[this]{
        const int row=releaseTable->currentRow();if(row<0)return;const auto index=releaseTable->item(row,0)->data(Qt::UserRole).toULongLong();if(index<model.releases.size())model.installRelease(model.releases[index]);
    });
    older=button("Load older releases","protonOlderReleases",actions,[this]{model.loadReleases(model.page+1);});
    button("Release notes","protonReleaseNotes",actions,[this]{const int row=releaseTable->currentRow();if(row<0)return;const auto i=releaseTable->item(row,0)->data(Qt::UserRole).toULongLong();if(i<model.releases.size())QDesktopServices::openUrl(QUrl(text(model.releases[i].page_url)));});actions->addStretch();layout->addLayout(actions);
    hint("Downloads can be cancelled and retried. Recoverable partial downloads resume; completed tools install alongside existing versions. UMU is installed automatically with Proton.",layout);
    toolTabs->addTab(catalog,"Available");
    connect(providers,qOverload<int>(&QComboBox::currentIndexChanged),this,[this](int index){if(index<0 || model.busy())return;model.provider=providers->itemData(index).toString().toStdString();model.releases.clear();model.page=0;model.more=false;refreshTools();model.loadReleases(1);});
    connect(releaseSearch,&QLineEdit::textChanged,this,&Page::refreshTools);connect(prereleases,&QCheckBox::toggled,this,&Page::refreshTools);connect(incompatible,&QCheckBox::toggled,this,&Page::refreshTools);
    connect(releaseTable,&QTableWidget::itemSelectionChanged,this,&Page::selectDownload);
    auto *local=new QWidget;auto *localLayout=new QVBoxLayout(local);
    hint("Select a downloaded Proton version for the current prefix. Updating a tool keeps your current prefix selections.",localLayout);
    installedTable=table({"Tool","Version","Kind","Folder"},"protonInstalled");installedTable->setColumnWidth(0,230);installedTable->setColumnWidth(1,190);localLayout->addWidget(installedTable,1);
    auto *installedActions=new QHBoxLayout;
    useInstalled=button("Use for this prefix","protonUseInstalled",installedActions,[this]{const int row=installedTable->currentRow();if(row<0)return;const auto i=installedTable->item(row,0)->data(Qt::UserRole).toULongLong();if(i<model.installed.size() && model.installed[i].kind==toolstore::Kind::Proton)model.selectProton(model.installed[i].directory);});
    button("Open folder","protonOpenTool",installedActions,[this]{const int row=installedTable->currentRow();if(row>=0)openFolder(installedTable->item(row,3)->text());});
    removeInstalled=button("Remove tool…","protonRemoveTool",installedActions,[this]{const int row=installedTable->currentRow();if(row<0)return;const auto i=installedTable->item(row,0)->data(Qt::UserRole).toULongLong();if(i<model.installed.size() && confirm("Remove downloaded tool","Remove "+text(model.installed[i].name)+"? Prefixes and installed Windows applications will remain."))model.removeTool(model.installed[i]);});
    installedActions->addStretch();localLayout->addLayout(installedActions);toolTabs->addTab(local,"Installed");
    connect(installedTable,&QTableWidget::itemSelectionChanged,this,&Page::refreshTask);
    auto *updates=new QWidget;auto *updatesLayout=new QVBoxLayout(updates);auto *updateActions=new QHBoxLayout;
    button("Check for updates","protonCheckUpdates",updateActions,[this]{model.checkUpdates();});
    button("Install selected update","protonInstallUpdate",updateActions,[this]{const int row=updateTable->currentRow();if(row<0)return;const auto i=updateTable->item(row,0)->data(Qt::UserRole).toULongLong();if(i<model.updates.size())model.installRelease(model.updates[i].release);});updateActions->addStretch();updatesLayout->addLayout(updateActions);
    toolNotice=hint("Updates install alongside your current tools. Choose the new version for a prefix when ready.",updatesLayout);
    updateTable=table({"Tool","Installed","Available","Variant"},"protonUpdates");updateTable->setColumnWidth(0,200);updateTable->setColumnWidth(1,190);updateTable->setColumnWidth(2,190);updatesLayout->addWidget(updateTable,1);toolTabs->addTab(updates,"Updates");
    connect(updateTable,&QTableWidget::itemSelectionChanged,this,&Page::refreshTask);
}
void Page::refreshTools() {
    providerInfo->setText(text(toolstore::provider(model.provider).description));
    const int selectedRow=releaseTable->currentRow();const QVariant selected=selectedRow>=0?releaseTable->item(selectedRow,0)->data(Qt::UserRole):QVariant();
    {const QSignalBlocker blocker(releaseTable);releaseTable->setRowCount(0);
        for(size_t i=0;i<model.releases.size();++i) {
            const auto &r=model.releases[i];
            if((r.prerelease && !prereleases->isChecked()) || (!r.incompatibility.empty() && !incompatible->isChecked()))continue;
            if(!text(r.name+" "+r.version+" "+r.asset).contains(releaseSearch->text(),Qt::CaseInsensitive))continue;
            const auto installed=std::any_of(model.installed.begin(),model.installed.end(),[&](const auto &item){return item.id==toolstore::installation_id(r);});
            const int row=releaseTable->rowCount();releaseTable->insertRow(row);
            Ui::row(releaseTable,row,{text(r.version)+(r.prerelease?" · prerelease":""),text(r.asset),r.size?text(util::human_size(r.size)):"Unknown",installed?"Installed":!r.incompatibility.empty()?text(r.incompatibility):"Available"},qulonglong(i));
            if(selected.isValid() && selected.toULongLong()==i)releaseTable->selectRow(row);
        }
    }
    {const QSignalBlocker blocker(installedTable);const int previous=installedTable->currentRow();installedTable->setRowCount(int(model.installed.size()));
        for(size_t i=0;i<model.installed.size();++i){const auto &p=model.installed[i];Ui::row(installedTable,int(i),{text(p.name),text(p.version),p.kind==toolstore::Kind::Proton?"Proton":p.kind==toolstore::Kind::Launcher?"Launcher":"Companion",text(p.directory)},qulonglong(i));}
        if(previous>=0 && previous<installedTable->rowCount())installedTable->selectRow(previous);
    }
    {const QSignalBlocker blocker(updateTable);updateTable->setRowCount(int(model.updates.size()));
        for(size_t i=0;i<model.updates.size();++i){const auto &u=model.updates[i];Ui::row(updateTable,int(i),{text(u.current.name),text(u.current.version),text(u.release.version),text(u.release.asset)},qulonglong(i));}}
    toolNotice->setText(model.updateNotice.isEmpty()?(model.updates.empty()?"No update offers loaded. Check for newer matching releases.":"Install updates alongside existing versions; prefix selections stay unchanged."):model.updateNotice);
    refreshTask();
}
void Page::selectDownload() {
    const int row=releaseTable->currentRow();bool enabled=false;
    if(row>=0) {const auto i=releaseTable->item(row,0)->data(Qt::UserRole).toULongLong();if(i<model.releases.size()) {
        const auto &r=model.releases[i];enabled=!model.busy() && r.incompatibility.empty() && std::none_of(model.installed.begin(),model.installed.end(),[&](const auto &p){return p.id==toolstore::installation_id(r);});}}
    download->setEnabled(enabled);
    for(const auto *name:{"protonLoadReleases","protonCheckUpdates"})if(auto *b=findChild<QPushButton *>(name))b->setEnabled(!model.busy());
    if(auto *b=findChild<QPushButton *>("protonInstallUpdate"))b->setEnabled(!model.busy() && updateTable->currentRow()>=0);
    const int selected=installedTable->currentRow();
    if(selected>=0){const auto i=installedTable->item(selected,0)->data(Qt::UserRole).toULongLong();useInstalled->setEnabled(!model.current.empty() && i<model.installed.size() && model.installed[i].kind==toolstore::Kind::Proton);}
}
}
