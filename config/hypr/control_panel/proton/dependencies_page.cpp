#include "page.h"
#include "src/util.h"

namespace XetalProton {
using namespace Ui;
void Page::buildDependencies() {
    auto *page=new QWidget;auto *layout=new QVBoxLayout(page);
    hint("Install individual Windows components into the selected prefix using its Proton build's Winetricks.",layout);
    hint("Installed status comes from this prefix's Winetricks records. Manually installed components and Proton's built-in libraries may not appear here.",layout);
    auto *filters=new QHBoxLayout;dependencySearch=new QLineEdit;dependencySearch->setObjectName("protonDependencySearch");dependencySearch->setPlaceholderText("Search components…");filters->addWidget(dependencySearch,1);
    dependencyCategory=new QComboBox;dependencyCategory->addItems({"All","Visual C++",".NET","Fonts","Graphics & audio","Windows libraries"});filters->addWidget(dependencyCategory);
    button("Refresh status","protonRefreshDependencies",filters,[this]{refreshDependencies();});layout->addLayout(filters);
    dependencyInfo=hint({},layout);
    dependencyTable=table({"Component","Category","Status","Details"},"protonDependencies");dependencyTable->setColumnWidth(0,250);dependencyTable->setColumnWidth(1,160);dependencyTable->setColumnWidth(2,140);layout->addWidget(dependencyTable,1);
    auto *actions=new QHBoxLayout;dependencyInstall=button("Install selected component","protonInstallDependency",actions,[this]{installSelectedDependency();});
    dependencyStop=button("Stop installer","protonStopDependency",actions,[this]{for(const auto &p:model.processes)if(p.running && p.prefix_path==model.current && p.label.rfind("Install ",0)==0)model.stopProcess(p.pid,false);});
    button("Installer log","protonDependencyLog",actions,[this]{for(auto p=model.processes.rbegin();p!=model.processes.rend();++p)if(p->prefix_path==model.current && p->label.rfind("Install ",0)==0){viewLog(text(p->log_path));break;}});actions->addStretch();layout->addLayout(actions);
    connect(dependencySearch,&QLineEdit::textChanged,this,&Page::refreshDependencies);connect(dependencyCategory,&QComboBox::currentTextChanged,this,&Page::refreshDependencies);
    connect(dependencyTable,&QTableWidget::itemSelectionChanged,this,&Page::selectDependency);tabs->addTab(page,"Dependencies");
}
void Page::refreshDependencies() {
    const int selectedRow=dependencyTable->currentRow();const auto selected=selectedRow>=0?dependencyTable->item(selectedRow,0)->data(Qt::UserRole).toString():QString();
    dependencies::Status state;std::set<std::string> available;QString error;
    const auto *proton=model.proton(model.current);
    try {state=dependencies::status(model.current);if(proton)available=dependencies::available(*proton);}
    catch(const std::exception &e){error=text(e.what());}
    dependencyInfo->setText(!error.isEmpty()?error:model.current.empty()?"Create or select a prefix first.":!proton?"Choose an installed Proton version.":available.empty()?"This Proton build does not bundle Winetricks. Choose a build that includes it.":"Prefix: "+text(model.current));
    const QSignalBlocker blocker(dependencyTable);dependencyTable->setRowCount(0);
    for(const auto &component:dependencies::catalog()) {
        if(dependencyCategory->currentText()!="All" && dependencyCategory->currentText()!=text(component.category))continue;
        if(!text(component.name+" "+component.verb+" "+component.description).contains(dependencySearch->text(),Qt::CaseInsensitive))continue;
        const bool installed=state.installed.count(component.verb),supported=available.count(component.verb);
        QString details=text(component.description);if(state.failures.count(component.verb))details=text(state.failures.at(component.verb));
        const int row=dependencyTable->rowCount();dependencyTable->insertRow(row);
        Ui::row(dependencyTable,row,{text(component.name),text(component.category),!error.isEmpty()?"Unknown":installed?"Installed":!supported?"Unavailable":state.failures.count(component.verb)?"Retry available":"Missing",details},text(component.verb));
        dependencyTable->item(row,0)->setData(Qt::UserRole+1,error.isEmpty() && !model.current.empty() && !installed && supported);
        if(selected==text(component.verb))dependencyTable->selectRow(row);
    }
    selectDependency();
}
void Page::selectDependency() {
    const int row=dependencyTable->currentRow();
    const bool installing=std::any_of(model.processes.begin(),model.processes.end(),[&](const auto &p){return p.running && p.prefix_path==model.current && p.label.rfind("Install ",0)==0;});
    dependencyStop->setEnabled(installing);
    dependencyInstall->setEnabled(row>=0 && dependencyTable->item(row,0)->data(Qt::UserRole+1).toBool() && model.task!=Controller::Remove && !dependencies::busy(model.current));
    dependencyInstall->setText(row>=0 && dependencyTable->item(row,2)->text()=="Retry available"?"Retry installation":"Install selected component");
}
void Page::installSelectedDependency() {
    const int row=dependencyTable->currentRow();if(row<0)return;
    const auto verb=dependencyTable->item(row,0)->data(Qt::UserRole).toString().toStdString();
    if(model.installDependency(verb)){refreshDependencies();if(!model.processes.empty())viewLog(text(model.processes.back().log_path));}
}
}
