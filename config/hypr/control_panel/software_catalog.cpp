#include "software_catalog.h"
#include "software_actions.h"
#include "backend/package_install.h"
#include "terminal_exit.h"
#include <QtWidgets>
#include <algorithm>

namespace {
constexpr int AppRole=Qt::UserRole+1;
class RepositoryDialog final : public QDialog {
public:
    using QDialog::QDialog;
    bool running=false;
    void reject() override { if(!running)QDialog::reject(); }
};
QLabel *words(const QString &text,const char *name="catalogMuted") {
    auto *label=new QLabel(text);label->setObjectName(name);label->setTextFormat(Qt::PlainText);label->setWordWrap(true);return label;
}
void saveVendorDownload(QWidget *parent,const QString &root,const SoftwareApp &app,const QVariantMap &choice) {
    const QString suggested=QDir(QStandardPaths::writableLocation(QStandardPaths::DownloadLocation)).filePath(choice["filename"].toString());
    const QString destination=QFileDialog::getSaveFileName(parent,"Save "+app.name+" download",suggested);
    if(destination.isEmpty())return;
    QDialog dialog(parent);dialog.setObjectName("softwareDownloadProgress");dialog.setWindowTitle("Download "+app.name);dialog.resize(580,230);
    auto *layout=new QVBoxLayout(&dialog);layout->setContentsMargins(24,24,24,24);layout->setSpacing(14);
    auto *status=words("Preparing your download…","softwareDownloadStatus");layout->addWidget(status);
    auto *progress=new QProgressBar;progress->setRange(0,1000);progress->setValue(0);layout->addWidget(progress);
    auto *path=words(destination);path->setTextInteractionFlags(Qt::TextSelectableByMouse);layout->addWidget(path);
    auto *row=new QHBoxLayout;auto *folder=new QPushButton("Open folder");folder->setObjectName("softwareOpenDownloadFolder");folder->setEnabled(false);row->addWidget(folder);row->addStretch();
    auto *close=new QPushButton("Cancel download");row->addWidget(close);layout->addLayout(row);
    QProcess worker;QByteArray buffer;bool saved=false;QString failure;
    auto receive=[&]{
        buffer+=worker.readAllStandardOutput();
        while(buffer.contains('\n')){
            int end=buffer.indexOf('\n');const auto value=QJsonDocument::fromJson(buffer.left(end)).object();buffer.remove(0,end+1);
            if(value["type"]=="progress"){
                const auto total=qint64(value["total"].toDouble()),current=qint64(value["current"].toDouble());
                progress->setValue(total>0?int(current*1000/total):0);
                status->setText("Downloading · "+QLocale().formattedDataSize(current)+" / "+QLocale().formattedDataSize(total));
            }else if(value["type"]=="downloaded")saved=value["path"].toString()==QFileInfo(destination).absoluteFilePath();
            else if(value["type"]=="error")failure=value["message"].toString();
        }
    };
    QObject::connect(&worker,&QProcess::readyReadStandardOutput,&dialog,receive);
    QObject::connect(&worker,&QProcess::errorOccurred,&dialog,[&](QProcess::ProcessError error){if(error==QProcess::FailedToStart){status->setText("Could not start the download helper.");close->setText("Close");}});
    QObject::connect(&worker,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),&dialog,[&](int code,QProcess::ExitStatus exit){
        receive();close->setText("Close");
        if(!code&&exit==QProcess::NormalExit&&saved){progress->setValue(1000);status->setText("Download complete · checksum verified.\n"+choice["instructions"].toString());folder->setEnabled(true);}
        else status->setText(failure.isEmpty()?"Download did not complete. Please retry.":failure);
    });
    QObject::connect(folder,&QPushButton::clicked,&dialog,[&]{
        if(!QProcess::startDetached(root+"/scripts/files.sh",{QFileInfo(destination).absolutePath()}))
            status->setText("Could not open Fusion Files. Your download is saved at:\n"+destination);
    });
    QObject::connect(close,&QPushButton::clicked,&dialog,&QDialog::reject);
    worker.start("python3",{root+"/control_panel/software_download.py","--vendor",app.package,"--filename",choice["filename"].toString(),"--output",destination});
    dialog.exec();worker.disconnect(&dialog);
    if(worker.state()!=QProcess::NotRunning){worker.terminate();if(!worker.waitForFinished(2000)){worker.kill();worker.waitForFinished(1000);}}
}
bool installVendorApplication(QWidget *parent,const QString &root,const SoftwareApp &app) {
    RepositoryDialog dialog(parent);dialog.setObjectName("softwareInstallProgress");dialog.setWindowTitle("Install "+app.name);dialog.resize(580,280);
    auto *layout=new QVBoxLayout(&dialog);layout->setContentsMargins(24,24,24,24);layout->setSpacing(14);
    auto *status=words("Checking the latest release…","softwareInstallStatus");layout->addWidget(status);
    auto *progress=new QProgressBar;progress->setRange(0,0);layout->addWidget(progress);
    auto *details=new QPlainTextEdit;details->setReadOnly(true);details->setMaximumHeight(140);details->hide();layout->addWidget(details);
    auto *close=new QPushButton("Cancel download");layout->addWidget(close,0,Qt::AlignRight);
    QProcess worker;QByteArray buffer;bool installed=false;QString failure;
    auto receive=[&]{
        buffer+=worker.readAllStandardOutput();
        while(buffer.contains('\n')){
            const int end=buffer.indexOf('\n');const auto value=QJsonDocument::fromJson(buffer.left(end)).object();buffer.remove(0,end+1);
            const auto type=value["type"].toString();
            if(type=="progress"){
                const auto total=qint64(value["total"].toDouble()),current=qint64(value["current"].toDouble());
                progress->setRange(0,1000);progress->setValue(total>0?int(current*1000/total):0);
                status->setText("Downloading · "+QLocale().formattedDataSize(current)+" / "+QLocale().formattedDataSize(total));
            }else if(type=="status"||type=="installing"){
                status->setText(value["message"].toString());
                if(type=="installing"){dialog.running=true;close->setEnabled(false);close->setText("Installing…");progress->setRange(0,0);}
            }else if(type=="installed")installed=true;
            else if(type=="error")failure=value["message"].toString();
            else if(type=="log"){details->appendPlainText(value["message"].toString());details->show();}
        }
    };
    QObject::connect(&worker,&QProcess::readyReadStandardOutput,&dialog,receive);
    QObject::connect(&worker,&QProcess::errorOccurred,&dialog,[&](QProcess::ProcessError error){
        if(error==QProcess::FailedToStart){dialog.running=false;status->setText("Could not start the installer.");close->setText("Close");close->setEnabled(true);}
    });
    QObject::connect(&worker,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),&dialog,[&](int code,QProcess::ExitStatus exit){
        receive();dialog.running=false;close->setText("Close");close->setEnabled(true);progress->setRange(0,1000);
        if(!code&&exit==QProcess::NormalExit&&installed){progress->setValue(1000);status->setText(app.name+" is installed and ready to open.");}
        else {installed=false;status->setText(failure.isEmpty()?"Installation did not complete. Please retry.":failure);}
    });
    QObject::connect(close,&QPushButton::clicked,&dialog,&QDialog::reject);
    worker.start("python3",{root+"/control_panel/software_install.py","--vendor",app.package});
    dialog.exec();worker.disconnect(&dialog);
    if(worker.state()!=QProcess::NotRunning){worker.terminate();if(!worker.waitForFinished(7000)){worker.kill();worker.waitForFinished(1000);}}
    return installed;
}
QColor mix(QColor a,QColor b,qreal ratio) {
    return QColor::fromRgbF(a.redF()*(1-ratio)+b.redF()*ratio,a.greenF()*(1-ratio)+b.greenF()*ratio,a.blueF()*(1-ratio)+b.blueF()*ratio);
}
QIcon appIcon(const SoftwareApp &app) {
    static QCache<QString,QIcon> cache(256);
    static QString theme;
    const auto currentTheme=QIcon::themeName()+QIcon::themeSearchPaths().join('|');if(theme!=currentTheme){theme=currentTheme;cache.clear();}
    const auto key=app.icon+'|'+app.cachedIcon;
    if (auto *found=cache.object(key)) return *found;
    auto icon=app.icon=="package-x-generic"?QIcon():QFileInfo(app.icon).isAbsolute()?(QFileInfo::exists(app.icon)?QIcon(app.icon):QIcon()):QIcon::fromTheme(app.icon);
    if (icon.isNull()&&!app.cachedIcon.isEmpty()){QPixmap pixels(app.cachedIcon);if(!pixels.isNull())icon=QIcon(pixels);}
    if (icon.isNull())icon=QIcon::fromTheme(app.icon);
    if (icon.isNull()) icon=QIcon::fromTheme("application-x-executable",qApp->style()->standardIcon(QStyle::SP_FileIcon));
    cache.insert(key,new QIcon(icon));return icon;
}
void wrapped(QPainter *p,const QString &text,QRectF rect,QFont font,QColor color,int lines=2) {
    QTextLayout layout(text,font);QTextOption option;option.setWrapMode(QTextOption::WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option);
    layout.beginLayout();qreal y=0;
    for (int i=0;i<lines;++i) { auto line=layout.createLine();if (!line.isValid()) break;line.setLineWidth(rect.width());line.setPosition(QPointF(0,y));y+=line.height(); }
    layout.endLayout();p->save();p->setClipRect(rect);p->setPen(color);layout.draw(p,rect.topLeft());p->restore();
}
QString sourceName(const SoftwareApp &app) {
    if (app.source=="vendor") return "Official website";
    if (app.source=="aur") return "AUR · community";
    return "Pacman"+(app.repository.isEmpty()?QString():" · "+app.repository);
}
bool belongs(const SoftwareApp &app,const QString &category,const QStringList &tags) {
    if (category=="packages") return app.source!="vendor";
    if (category=="top") return app.essential||app.featured;
    if (app.source!="vendor"&&!app.available&&!app.installed) return false;
    if (category=="all") return !app.categories.isEmpty();
    for (const auto &tag:tags) if (app.categories.contains(tag)) return true;
    return false;
}
}

SoftwareApp SoftwareApp::fromJson(const QJsonObject &v,const QString &root) {
    SoftwareApp a;
    a.id=v["id"].toString();a.package=v["package"].toString();a.name=v["name"].toString(a.package);
    a.summary=v["summary"].toString();a.description=v["description"].toString();a.icon=v["icon"].toString();
    if (a.icon.contains('/')&&!QFileInfo(a.icon).isAbsolute()) a.icon=root+'/'+a.icon;
    a.cachedIcon=v["cached_icon"].toString();a.source=v["source"].toString("pacman");a.repository=v["repository"].toString();
    a.version=v["version"].toString();a.installedVersion=v["installed_version"].toString();a.license=v["license"].toString();
    a.installedPackage=v["installed_package"].toString();a.debId=v["deb_id"].toString();a.debNote=v["deb_note"].toString();
    a.website=v["website"].toString();a.desktopFile=v["desktop_file"].toString();a.accent=v["accent"].toString();a.tagline=v["tagline"].toString();
    for (const auto &c:v["categories"].toArray()) a.categories<<c.toString();
    a.installed=v["installed"].toBool();a.available=v["available"].toBool();a.featured=v["featured"].toBool();a.essential=v["essential"].toBool();
    a.featuredOrder=v["featured_order"].toInt(100);
    a.searchText=(a.name+' '+a.package+' '+a.summary+' '+a.categories.join(' ')).toCaseFolded();return a;
}

class SoftwareAppModel final:public QAbstractListModel {
public:
    QVector<SoftwareApp> entries;
    explicit SoftwareAppModel(QObject *parent):QAbstractListModel(parent) {}
    int rowCount(const QModelIndex &parent={}) const override {return parent.isValid()?0:entries.size();}
    QVariant data(const QModelIndex &index,int role) const override {
        if (!index.isValid()||index.row()>=entries.size()) return {};
        const auto &a=entries[index.row()];
        if (role==Qt::DisplayRole||role==Qt::AccessibleTextRole) return a.name+". "+a.summary+". "+sourceName(a)+". "+a.action;
        if (role==Qt::ToolTipRole) return a.name+"\n"+a.summary+"\n"+sourceName(a);
        if (role==AppRole) return a.id;
        return {};
    }
    void replace(QVector<SoftwareApp> values) {beginResetModel();entries=std::move(values);endResetModel();}
};

class AppDelegate final:public QStyledItemDelegate {
public:
    std::function<void(const SoftwareApp &)> action;
    std::function<void(const SoftwareApp &)> showDetails;
    explicit AppDelegate(QObject *parent):QStyledItemDelegate(parent) {}
    QSize sizeHint(const QStyleOptionViewItem &,const QModelIndex &) const override {
        auto *view=qobject_cast<QListView *>(parent());return view?view->gridSize():QSize(320,152);
    }
    static QRect buttonRect(const QRect &rect) {return QRect(rect.right()-124,rect.bottom()-44,106,28);}
    void paintFeatured(QPainter *p,const QStyleOptionViewItem &opt,const SoftwareApp &app) const {
        p->save();p->setRenderHint(QPainter::Antialiasing);p->translate(opt.rect.topLeft());
        const QRect r=QRect(QPoint(),opt.rect.size()).adjusted(5,5,-5,-5);QColor accent(app.accent);
        if(!accent.isValid())accent=opt.palette.color(QPalette::Highlight);
        QPainterPath clip;clip.addRoundedRect(r,16,16);p->setClipPath(clip);
        QLinearGradient gradient(r.topLeft(),r.bottomRight());gradient.setColorAt(0,mix(QColor("#0a1426"),accent,.27));gradient.setColorAt(1,QColor("#0b1527"));p->fillPath(clip,gradient);
        p->setPen(QPen(QColor(accent.red(),accent.green(),accent.blue(),30),1.3));p->setBrush(Qt::NoBrush);
        if(app.package=="xmusic"){
            for(int i=0;i<20;++i){const int h=16+((i*17+11)%7)*11;p->drawRoundedRect(QRectF(r.right()-160+i*10,r.bottom()-h,5,h+8),2,2);}
        }else if(app.package=="linuxstudio"){
            for(int i=0;i<8;++i)p->drawLine(r.right()-145+i*24,r.top(),r.right()-190+i*24,r.bottom());
            for(int i=1;i<7;++i)p->drawLine(r.right()-190,r.top()+i*28,r.right(),r.top()+i*28);
        }else if(app.package=="xvideo"){
            for(int i=0;i<4;++i)p->drawRoundedRect(QRectF(r.right()-150+i*18,r.top()-12+i*18,155,110),13,13);
        }else{
            for(int i=0;i<5;++i)p->drawEllipse(QPointF(r.right()-22,r.top()+22),52+i*24,52+i*24);
        }
        appIcon(app).paint(p,QRect(r.right()-85,r.top()+21,60,60));
        auto font=opt.font;font.setPixelSize(10);font.setBold(true);font.setLetterSpacing(QFont::AbsoluteSpacing,1.2);p->setFont(font);p->setPen(accent);
        p->drawText(r.adjusted(20,15,-95,-140),Qt::AlignVCenter,app.source=="vendor"?"FROM XETAL":app.source=="aur"?"COMMUNITY FAVORITE":"TOP PICK");
        font.setLetterSpacing(QFont::AbsoluteSpacing,0);font.setPixelSize(20);p->setFont(font);p->setPen(QColor("#f2f7ff"));
        wrapped(p,app.name,QRectF(r.left()+20,r.top()+41,r.width()-116,51),font,QColor("#f2f7ff"));
        font.setPixelSize(12);font.setBold(false);wrapped(p,app.tagline.isEmpty()?app.summary:app.tagline,QRectF(r.left()+20,r.top()+97,r.width()-40,34),font,QColor("#c8d8ec"));
        p->setFont(font);p->setPen(accent);p->drawText(r.adjusted(20,0,-135,-15),Qt::AlignLeft|Qt::AlignBottom,app.source=="vendor"?"Install · Linux":sourceName(app));
        const auto button=buttonRect(QRect(QPoint(),opt.rect.size()));p->setPen(Qt::NoPen);p->setBrush(mix(QColor("#112034"),accent,.16));p->drawRoundedRect(button,8,8);
        p->setPen(accent);font.setBold(true);p->setFont(font);p->drawText(button,Qt::AlignCenter,app.action);
        p->setClipping(false);p->setBrush(Qt::NoBrush);bool active=opt.state&(QStyle::State_MouseOver|QStyle::State_Selected|QStyle::State_HasFocus);p->setPen(QPen(active?accent:mix(accent,QColor("#24334a"),.65),active?1.6:1));p->drawPath(clip);p->restore();
    }
    void paint(QPainter *p,const QStyleOptionViewItem &opt,const QModelIndex &index) const override {
        auto *model=static_cast<const SoftwareAppModel *>(index.model());const auto &a=model->entries[index.row()];
        if(a.featured&&parent()->property("featuredCatalog").toBool()){paintFeatured(p,opt,a);return;}
        const QRect r=opt.rect.adjusted(5,5,-5,-5);auto palette=opt.palette;
        bool hover=opt.state&QStyle::State_MouseOver,selected=opt.state&QStyle::State_Selected;
        p->save();p->setRenderHint(QPainter::Antialiasing);
        p->setPen(QPen(selected?palette.color(QPalette::Highlight):hover?palette.color(QPalette::Midlight):palette.color(QPalette::Mid),selected?1.5:1));
        p->setBrush(hover?mix(palette.color(QPalette::AlternateBase),palette.color(QPalette::Highlight),.05):palette.color(QPalette::AlternateBase));
        p->drawRoundedRect(r,13,13);
        const QRect iconRect(r.left()+16,r.top()+17,48,48);appIcon(a).paint(p,iconRect);
        auto title=opt.font;title.setBold(true);if(title.pointSizeF()>0)title.setPointSizeF(title.pointSizeF()+1);else title.setPixelSize(std::max(14,title.pixelSize()+1));
        p->setFont(title);p->setPen(palette.color(QPalette::Text));
        p->drawText(QRect(r.left()+78,r.top()+16,r.width()-94,25),Qt::AlignVCenter,QFontMetrics(title).elidedText(a.name,Qt::ElideRight,r.width()-94));
        auto body=opt.font;body.setPointSizeF(std::max(9.,body.pointSizeF()-.3));
        wrapped(p,a.summary,QRectF(r.left()+78,r.top()+45,r.width()-94,43),body,palette.color(QPalette::PlaceholderText));
        p->setFont(body);p->setPen(palette.color(QPalette::PlaceholderText));
        p->drawText(QRect(r.left()+16,r.bottom()-40,r.width()-148,23),Qt::AlignVCenter,
                    QFontMetrics(body).elidedText(sourceName(a),Qt::ElideRight,r.width()-148));
        auto button=buttonRect(opt.rect);p->setPen(Qt::NoPen);
        p->setBrush(mix(palette.color(QPalette::Button),palette.color(QPalette::Highlight),.10));p->drawRoundedRect(button,8,8);
        p->setPen(palette.color(QPalette::Link));body.setBold(true);p->setFont(body);p->drawText(button,Qt::AlignCenter,a.action);
        p->restore();
    }
    bool editorEvent(QEvent *event,QAbstractItemModel *model,const QStyleOptionViewItem &opt,const QModelIndex &index) override {
        if (event->type()==QEvent::MouseButtonRelease) {
            auto *mouse=static_cast<QMouseEvent *>(event);
            if (mouse->button()==Qt::LeftButton) {
                const auto app=static_cast<SoftwareAppModel *>(model)->entries[index.row()];
                if(buttonRect(opt.rect).contains(mouse->position().toPoint())) {if(action)action(app);}
                else if(showDetails)showDetails(app);
                return true;
            }
        }
        return QStyledItemDelegate::editorEvent(event,model,opt,index);
    }
};

class CategoryDelegate final:public QStyledItemDelegate {
public:
    using QStyledItemDelegate::QStyledItemDelegate;
    QSize sizeHint(const QStyleOptionViewItem &,const QModelIndex &) const override{return {200,37};}
    void paint(QPainter *p,const QStyleOptionViewItem &opt,const QModelIndex &index) const override {
        p->save();p->setRenderHint(QPainter::Antialiasing);const QRect r=opt.rect.adjusted(1,2,-2,-2);
        const auto *view=qobject_cast<QTreeWidget *>(parent());
        const bool selected=(opt.state&QStyle::State_Selected)||(view&&view->selectionModel()->isSelected(index));
        p->setPen(Qt::NoPen);p->setBrush(selected?opt.palette.color(QPalette::Highlight):opt.state&QStyle::State_MouseOver?opt.palette.color(QPalette::Button):Qt::transparent);p->drawRoundedRect(r,9,9);
        auto color=selected?opt.palette.color(QPalette::HighlightedText):opt.palette.color(QPalette::Text);
        const QIcon icon=qvariant_cast<QIcon>(index.data(Qt::DecorationRole));icon.paint(p,QRect(r.left()+8,r.center().y()-10,20,20));
        auto font=opt.font;font.setBold(!index.parent().isValid());p->setFont(font);p->setPen(color);
        const auto number=index.data(Qt::UserRole+2).toString();const int countWidth=number.isEmpty()?0:QFontMetrics(font).horizontalAdvance(number)+13;
        const auto label=index.data(Qt::DisplayRole).toString();QRect labelRect(r.left()+36,r.top(),r.width()-46-countWidth,r.height());
        p->drawText(labelRect,Qt::AlignVCenter,QFontMetrics(font).elidedText(label,Qt::ElideRight,labelRect.width()));
        font.setBold(false);p->setFont(font);if(!selected)p->setPen(opt.palette.color(QPalette::PlaceholderText));p->drawText(r.adjusted(0,0,-9,0),Qt::AlignRight|Qt::AlignVCenter,number);p->restore();
    }
};

class CategoryTree final:public QTreeWidget {
protected:
    void drawRow(QPainter *p,const QStyleOptionViewItem &option,const QModelIndex &index) const override {
        auto clean=option;clean.state&=~QStyle::State_Selected;QTreeWidget::drawRow(p,clean,index);
    }
    void drawBranches(QPainter *p,const QRect &r,const QModelIndex &index) const override {
        p->fillRect(r,palette().color(QPalette::AlternateBase));
        if(!model()->hasChildren(index))return;
        p->save();p->setRenderHint(QPainter::Antialiasing);p->setPen(Qt::NoPen);p->setBrush(palette().color(QPalette::PlaceholderText));
        const QPointF c(r.right()-7,r.center().y());QPolygonF arrow;
        if(isExpanded(index))arrow<<c+QPointF(-3,-2)<<c+QPointF(3,-2)<<c+QPointF(0,2);
        else arrow<<c+QPointF(-2,-3)<<c+QPointF(-2,3)<<c+QPointF(2,0);
        p->drawPolygon(arrow);p->restore();
    }
};

SoftwareCatalogPage::SoftwareCatalogPage(const QString &root,const QString &terminal,QWidget *parent)
    :QWidget(parent),root(root),terminal(terminal) {
    setObjectName("softwareCatalog");
    setStyleSheet(
        "QWidget#softwareCatalog,QWidget#catalogContent,QWidget#catalogRail {background:transparent;}"
        "QFrame#catalogSidebar {background:palette(alternate-base);border:1px solid palette(mid);border-radius:14px;}"
        "QTreeWidget#softwareCategories {background:transparent;border:0;outline:0;}"
        "QTreeWidget#softwareCategories::item {height:33px;padding:2px 5px;border:0;border-radius:9px;}"
        "QTreeWidget#softwareCategories::item:selected {background:transparent;}"
        "QTreeWidget#softwareCategories::branch:selected {background:transparent;}"
        "QLabel#catalogHeading {font-size:23px;font-weight:700;}"
        "QLabel#catalogMuted,QLabel#catalogCount {color:palette(placeholder-text);}"
        "QLabel#catalogSection {font-weight:650;font-size:15px;}"
        "QLabel#catalogSourceHeading {color:palette(placeholder-text);font-size:11px;font-weight:650;}"
        "QListView#softwareAppGrid {background:transparent;border:0;outline:0;padding:0;margin:0;}"
        "QLineEdit#softwareAppSearch {padding:9px 14px;border-radius:11px;}"
        "QSplitter::handle {background:transparent;}"
        "QPushButton#catalogManage {background:transparent;border:0;text-align:left;padding:4px;color:palette(link);}"
        "QLabel#catalogNotice {color:palette(placeholder-text);}"
        "QPushButton#catalogAction {background:palette(highlight);color:palette(highlighted-text);font-weight:650;}");
    auto *outer=new QVBoxLayout(this);outer->setContentsMargins(0,10,0,0);outer->setSpacing(10);
    splitter=new QSplitter;splitter->setObjectName("softwareCatalogSplitter");splitter->setChildrenCollapsible(false);splitter->setHandleWidth(14);outer->addWidget(splitter,1);
    auto *sidebar=new QFrame;sidebar->setObjectName("catalogSidebar");sidebar->setMinimumWidth(190);sidebar->setMaximumWidth(310);
    auto *side=new QVBoxLayout(sidebar);side->setContentsMargins(10,16,10,12);side->setSpacing(10);
    auto *browseTitle=words("EXPLORE","catalogSourceHeading");browseTitle->setContentsMargins(8,0,0,2);side->addWidget(browseTitle);
    tree=new CategoryTree;tree->setObjectName("softwareCategories");tree->setAccessibleName("Software categories");tree->setColumnCount(1);tree->setItemDelegate(new CategoryDelegate(tree));tree->setMouseTracking(true);tree->setHeaderHidden(true);
    tree->setUniformRowHeights(true);tree->setIndentation(13);tree->setIconSize(QSize(19,19));tree->setAnimated(false);
    tree->setSelectionMode(QAbstractItemView::SingleSelection);tree->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    tree->header()->setStretchLastSection(false);tree->header()->setSectionResizeMode(0,QHeaderView::Stretch);
    side->addWidget(tree,1);
    auto *line=new QFrame;line->setFrameShape(QFrame::HLine);side->addWidget(line);
    side->addWidget(words("SOURCES","catalogSourceHeading"));
    pacman=new QCheckBox("Pacman");yay=new QCheckBox("Yay · AUR");paru=new QCheckBox("Paru · AUR");
    pacman->setObjectName("softwareSourcePacman");yay->setObjectName("softwareSourceYay");paru->setObjectName("softwareSourceParu");
    QSettings settings("XetalHyperland","ControlPanel");
    pacman->setChecked(settings.value("software/catalog/pacman",true).toBool());
    yay->setChecked(settings.value("software/catalog/yay",false).toBool());paru->setChecked(settings.value("software/catalog/paru",false).toBool());
    yay->setEnabled(!QStandardPaths::findExecutable("yay").isEmpty());paru->setEnabled(!QStandardPaths::findExecutable("paru").isEmpty());
    pacman->setToolTip("Apps and packages from your configured Pacman repositories, including multilib when enabled.");
    for (auto *check:{pacman,yay,paru}) {side->addWidget(check);connect(check,&QCheckBox::toggled,this,&SoftwareCatalogPage::sourceChanged);}
    auto *manage=new QPushButton("Manage Yay & Paru…");manage->setObjectName("catalogManage");side->addWidget(manage);
    syncButton=new QPushButton(QIcon::fromTheme("view-refresh"),"Refresh package lists…");syncButton->setObjectName("softwareSyncRepositories");side->addWidget(syncButton);
    connect(syncButton,&QPushButton::clicked,this,&SoftwareCatalogPage::syncRepositories);
    connect(manage,&QPushButton::clicked,this,[this]{emit openTool("aur");});splitter->addWidget(sidebar);
    auto *content=new QWidget;content->setObjectName("catalogContent");auto *body=new QVBoxLayout(content);body->setContentsMargins(0,0,0,0);body->setSpacing(10);
    search=new QLineEdit;search->setObjectName("softwareAppSearch");search->setPlaceholderText("Search apps, descriptions and packages…");search->setAccessibleName("Search software");search->setClearButtonEnabled(true);
    search->addAction(QIcon::fromTheme("edit-find"),QLineEdit::LeadingPosition);body->addWidget(search);
    auto *titles=new QHBoxLayout;auto *caption=new QVBoxLayout;caption->setSpacing(3);heading=words("Find your next favorite.","catalogHeading");subtitle=words("Hand-picked essentials. Ready for your desktop.");caption->addWidget(heading);caption->addWidget(subtitle);titles->addLayout(caption,1);
    count=words({},"catalogCount");count->setAlignment(Qt::AlignRight|Qt::AlignVCenter);titles->addWidget(count);body->addLayout(titles);
    results=new QStackedWidget;results->setObjectName("softwareCatalogResults");body->addWidget(results,1);
    grid=new QListView;grid->setObjectName("softwareAppGrid");grid->setAccessibleName("Software apps");grid->setViewMode(QListView::IconMode);
    grid->setResizeMode(QListView::Adjust);grid->setMovement(QListView::Static);grid->setUniformItemSizes(true);grid->setLayoutMode(QListView::Batched);grid->setBatchSize(128);grid->setWrapping(true);grid->setWordWrap(false);grid->setSpacing(0);
    grid->setMouseTracking(true);grid->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);grid->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);grid->setSelectionMode(QAbstractItemView::SingleSelection);grid->viewport()->installEventFilter(this);
    model=new SoftwareAppModel(this);grid->setModel(model);auto *delegate=new AppDelegate(grid);grid->setItemDelegate(delegate);
    delegate->action=[this](const SoftwareApp &app){if(!app.installed&&!app.debId.isEmpty())details(app);else activate(app);};
    delegate->showDetails=[this](const SoftwareApp &app){details(app);};
    auto *detailShortcut=new QShortcut(QKeySequence(Qt::Key_Return),grid);detailShortcut->setContext(Qt::WidgetShortcut);connect(detailShortcut,&QShortcut::activated,this,[this]{if(grid->currentIndex().isValid())details(model->entries[grid->currentIndex().row()]);});
    results->addWidget(grid);
    auto *emptyPage=new QWidget;auto *emptyLayout=new QVBoxLayout(emptyPage);emptyLayout->addStretch();empty=words("Choose a category to start exploring.","catalogHeading");empty->setAlignment(Qt::AlignCenter);emptyLayout->addWidget(empty);emptyLayout->addStretch();results->addWidget(emptyPage);
    notice=words({},"catalogNotice");notice->hide();body->addWidget(notice);
    cacheStatus=words("Preparing your local app catalog…");cacheStatus->setObjectName("softwareCatalogStatus");body->addWidget(cacheStatus);
    splitter->addWidget(content);splitter->setStretchFactor(1,1);splitter->setSizes({settings.value("software/catalog/sidebarWidth",250).toInt(),1000});
    connect(splitter,&QSplitter::splitterMoved,this,[this]{QSettings s("XetalHyperland","ControlPanel");s.setValue("software/catalog/sidebarWidth",splitter->sizes().value(0,230));});
    filterDelay.setSingleShot(true);filterDelay.setInterval(120);connect(&filterDelay,&QTimer::timeout,this,[this]{refilter(true);});
    aurDelay.setSingleShot(true);aurDelay.setInterval(650);connect(&aurDelay,&QTimer::timeout,this,[this]{requestAur();});
    connect(search,&QLineEdit::textChanged,this,[this]{filterDelay.start();aurDelay.start();});
    connect(search,&QLineEdit::returnPressed,this,[this]{filterDelay.stop();refilter(true);aurDelay.stop();requestAur();});
    connect(tree,&QTreeWidget::currentItemChanged,this,[this](QTreeWidgetItem *item){if(!item)return;category=item->data(0,Qt::UserRole).toString();refilter(true);if(lastRead.isValid()&&lastRead.secsTo(QDateTime::currentDateTime())>60)requestCatalog();});
    connect(&localWorker,&QProcess::readyReadStandardOutput,this,&SoftwareCatalogPage::receiveCatalog);
    connect(&localWorker,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code,QProcess::ExitStatus){
        receiveCatalog();localDeadline.stop();
        if(code&&!loaded) {notice->setText("The local catalog could not be loaded. Your Top picks are still available. Try Refresh.");notice->show();}
        if(pendingRefresh){pendingRefresh=false;requestCatalog(true);}
    });
    connect(&localWorker,&QProcess::errorOccurred,this,[this](QProcess::ProcessError error){if(error==QProcess::FailedToStart){localDeadline.stop();notice->setText("Could not open the software catalog helper. Update the desktop and retry.");notice->show();}});
    localDeadline.setSingleShot(true);localDeadline.setInterval(45000);connect(&localDeadline,&QTimer::timeout,this,[this]{localWorker.kill();notice->setText("Catalog refresh timed out. The previous app list is kept.");notice->show();});
    connect(&aurWorker,&QProcess::readyReadStandardOutput,this,[this]{aurBuffer+=aurWorker.readAllStandardOutput();if(aurBuffer.size()>8*1024*1024)aurWorker.kill();});
    connect(&aurWorker,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,&SoftwareCatalogPage::finishAur);
    connect(&aurWorker,&QProcess::errorOccurred,this,[this](QProcess::ProcessError error){if(error==QProcess::FailedToStart){aurDeadline.stop();notice->setText("Could not start the AUR search helper. Local results are still available.");notice->show();}});
    aurDeadline.setSingleShot(true);aurDeadline.setInterval(18000);connect(&aurDeadline,&QTimer::timeout,this,[this]{aurWorker.kill();});
    QFile seed(root+"/control_panel/software/catalog.json");const auto document=seed.open(QIODevice::ReadOnly)?QJsonDocument::fromJson(seed.readAll()).object():QJsonObject();
    buildTree(document["categories"].toArray());for (const auto &value:document["apps"].toArray()) apps<<SoftwareApp::fromJson(value.toObject(),root);
    refilter();
}

SoftwareCatalogPage::~SoftwareCatalogPage() {
    for(auto *object:findChildren<QObject *>())object->disconnect(this);
    for(auto *process:{&localWorker,&aurWorker}){process->disconnect(this);if(process->state()!=QProcess::NotRunning){process->kill();process->waitForFinished(1000);}}
}
void SoftwareCatalogPage::buildTree(const QJsonArray &values) {
    QSignalBlocker block(tree);tree->clear();for(const auto &value:values)addCategory(value.toObject());
    if(tree->topLevelItemCount())tree->setCurrentItem(tree->topLevelItem(0));
}
void SoftwareCatalogPage::addCategory(const QJsonObject &v,QTreeWidgetItem *parent) {
    auto *item=parent?new QTreeWidgetItem(parent):new QTreeWidgetItem(tree);item->setText(0,v["name"].toString());item->setIcon(0,QIcon::fromTheme(v["icon"].toString(),style()->standardIcon(QStyle::SP_DirIcon)));
    item->setToolTip(0,v["name"].toString());
    item->setData(0,Qt::UserRole,v["id"].toString());QStringList tags;for(const auto &value:v["tags"].toArray())tags<<value.toString();item->setData(0,Qt::UserRole+1,tags);
    item->setTextAlignment(1,Qt::AlignRight|Qt::AlignVCenter);if(!parent){auto font=item->font(0);font.setBold(true);item->setFont(0,font);}
    for(const auto &child:v["children"].toArray())addCategory(child.toObject(),item);
}
void SoftwareCatalogPage::showEvent(QShowEvent *event) {
    QWidget::showEvent(event);QTimer::singleShot(0,this,[this]{fitGrid();if(!lastRead.isValid()||lastRead.secsTo(QDateTime::currentDateTime())>60)requestCatalog();offerRepositorySync();});
}
bool SoftwareCatalogPage::eventFilter(QObject *object,QEvent *event) {
    if(object==grid->viewport()&&event->type()==QEvent::Resize)fitGrid();
    return QWidget::eventFilter(object,event);
}
void SoftwareCatalogPage::fitGrid() {
    const int width=grid->viewport()->width();const bool top=category=="top"&&search->text().trimmed().isEmpty();
    grid->setProperty("featuredCatalog",top);
    const int columns=std::clamp(width/(top?360:310),1,5);QSize size(std::max(220,(width-2)/columns),top?190:152);
    if(grid->gridSize()!=size)grid->setGridSize(size);
}
void SoftwareCatalogPage::focusSearch(){search->setFocus();}
void SoftwareCatalogPage::refresh(){requestCatalog(true);if(!search->text().trimmed().isEmpty())requestAur(true);}
void SoftwareCatalogPage::offerRepositorySync() {
    if(!isVisible()||!loaded||!hasPacman||repositoryPrompted||repositorySyncRunning)return;
    QSettings settings("XetalHyperland","ControlPanel");
    if(settings.value("software/catalog/repositoriesInitialized",false).toBool()&&!needsSync)return;
    repositoryPrompted=true;
    QMessageBox prompt(QMessageBox::Question,"Refresh package lists?",
        needsSync?"Some package lists are missing or unreadable. Refresh them to show available apps?":"Refresh package lists before your first visit to Software?",
        QMessageBox::Yes|QMessageBox::No,this);
    prompt.setObjectName("softwareRepositoryPrompt");prompt.setTextFormat(Qt::PlainText);
    prompt.setInformativeText("This downloads repository lists with sudo pacman -Sy. It does not install or upgrade packages. Administrator authentication is required.");
    prompt.button(QMessageBox::Yes)->setText("Refresh lists");prompt.button(QMessageBox::No)->setText("Later");
    if(prompt.exec()==QMessageBox::Yes)syncRepositories();
}
void SoftwareCatalogPage::syncRepositories() {
    if(repositorySyncRunning)return;
    repositoryPrompted=true;
    const QString askpass=root+"/scripts/sudo-askpass.sh";
    if(!QFileInfo::exists(askpass)){notice->setText("The administrator authentication helper is missing. Update Hyper Fusion to restore it.");notice->show();return;}
    RepositoryDialog dialog(this);dialog.setObjectName("softwareRepositorySync");dialog.setWindowTitle("Refresh package lists");dialog.resize(640,350);
    auto *layout=new QVBoxLayout(&dialog);layout->setContentsMargins(24,24,24,24);layout->setSpacing(12);
    auto *summary=new QHBoxLayout;summary->setSpacing(14);
    auto *successIcon=new QLabel;successIcon->setObjectName("softwareRepositorySuccess");successIcon->setAccessibleName("Success");successIcon->setFixedSize(36,36);
    const qreal scale=dialog.devicePixelRatioF();QPixmap mark(QSize(36,36)*scale);mark.setDevicePixelRatio(scale);mark.fill(Qt::transparent);
    {QPainter painter(&mark);painter.setRenderHint(QPainter::Antialiasing);painter.setPen(QPen(QColor("#46d986"),2));painter.setBrush(QColor("#163c2b"));painter.drawRoundedRect(QRectF(2,2,32,32),7,7);
     painter.setPen(QPen(QColor("#46d986"),3,Qt::SolidLine,Qt::RoundCap,Qt::RoundJoin));painter.drawPolyline(QPolygonF{QPointF(10,18),QPointF(16,24),QPointF(27,12)});}
    successIcon->setPixmap(mark);successIcon->hide();summary->addWidget(successIcon);
    auto *status=words("Refreshing repository lists. No packages will be installed or upgraded.","softwareRepositoryStatus");summary->addWidget(status,1);layout->addLayout(summary);
    auto *progress=new QProgressBar;progress->setRange(0,0);progress->setTextVisible(false);layout->addWidget(progress);
    auto *output=new QPlainTextEdit;output->setObjectName("softwareRepositoryOutput");output->setReadOnly(true);output->document()->setMaximumBlockCount(1500);layout->addWidget(output,1);
    auto *row=new QHBoxLayout;auto *details=new QPushButton("Show details");details->setObjectName("softwareRepositoryDetails");details->setCheckable(true);details->hide();row->addWidget(details);row->addStretch();auto *retry=new QPushButton("Retry");retry->hide();row->addWidget(retry);auto *close=new QPushButton("Close");close->setEnabled(false);row->addWidget(close);layout->addLayout(row);
    QProcess worker;worker.setProcessChannelMode(QProcess::MergedChannels);auto env=QProcessEnvironment::systemEnvironment();env.insert("SUDO_ASKPASS",askpass);env.insert("TERM","dumb");worker.setProcessEnvironment(env);
    auto finished=[&](bool success){
        repositorySyncRunning=false;dialog.running=false;syncButton->setEnabled(true);close->setEnabled(true);retry->setVisible(!success);progress->hide();successIcon->setVisible(success);details->setVisible(success);details->setChecked(false);output->setVisible(!success);
        if(success){QSettings("XetalHyperland","ControlPanel").setValue("software/catalog/repositoriesInitialized",true);status->setText("Your package list has been refreshed successfully.");status->setStyleSheet("font-weight:600;");requestCatalog(true);}
        else status->setText("Package lists could not be refreshed. Check the details below, then retry.");
        dialog.adjustSize();
    };
    auto start=[&]{
        repositorySyncRunning=true;dialog.running=true;syncButton->setEnabled(false);close->setEnabled(false);retry->hide();successIcon->hide();details->hide();progress->show();output->show();output->clear();status->setStyleSheet({});status->setText("Refreshing repository lists. No packages will be installed or upgraded.");
        worker.start("sudo",{"-A","-k","--","pacman","-Sy"});
    };
    connect(&worker,&QProcess::readyReadStandardOutput,&dialog,[&]{output->moveCursor(QTextCursor::End);output->insertPlainText(QString::fromUtf8(worker.readAllStandardOutput()));output->ensureCursorVisible();});
    connect(&worker,&QProcess::errorOccurred,&dialog,[&](QProcess::ProcessError error){if(error==QProcess::FailedToStart){output->appendPlainText(worker.errorString());finished(false);}});
    connect(&worker,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),&dialog,[&](int code,QProcess::ExitStatus exit){finished(code==0&&exit==QProcess::NormalExit);});
    connect(details,&QPushButton::toggled,&dialog,[&](bool visible){output->setVisible(visible);details->setText(visible?"Hide details":"Show details");dialog.adjustSize();});
    connect(retry,&QPushButton::clicked,&dialog,start);connect(close,&QPushButton::clicked,&dialog,&QDialog::reject);
    start();dialog.exec();
}
void SoftwareCatalogPage::requestCatalog(bool force) {
    if(localWorker.state()!=QProcess::NotRunning){pendingRefresh|=force;return;}
    if(!QFileInfo::exists(root+"/control_panel/software_catalog.py"))return;
    if(force)cacheStatus->setText("Refreshing your local catalog…");
    localBuffer.clear();QStringList args{root+"/control_panel/software_catalog.py"};if(force)args<<"--refresh";
    localDeadline.start();localWorker.start("python3",args);
}
void SoftwareCatalogPage::receiveCatalog() {
    localBuffer+=localWorker.readAllStandardOutput();if(localBuffer.size()>40*1024*1024){localWorker.kill();localBuffer.clear();return;}
    while(localBuffer.contains('\n')){
        int end=localBuffer.indexOf('\n');auto value=QJsonDocument::fromJson(localBuffer.left(end)).object();localBuffer.remove(0,end+1);
        if(value["type"]=="catalog")applyCatalog(value);
        else if(value["type"]=="error"){notice->setText(value["message"].toString());notice->show();}
    }
}
void SoftwareCatalogPage::applyCatalog(const QJsonObject &value) {
    if(!value["apps"].isArray()||value["apps"].toArray().size()>60000)return;
    QVector<SoftwareApp> incoming;for(const auto &entry:value["apps"].toArray())incoming<<SoftwareApp::fromJson(entry.toObject(),root);
    apps=std::move(incoming);loaded=true;lastRead=QDateTime::currentDateTime();installedPackages=value["installed_packages"].toObject();
    const auto helpers=value["helpers"].toObject();
    hasPacman=helpers["pacman"].toBool();needsSync=value["needs_sync"].toBool();syncButton->setEnabled(hasPacman&&!repositorySyncRunning);
    for(const auto &pair:{qMakePair(yay,QString("yay")),qMakePair(paru,QString("paru"))}){
        const bool present=helpers[pair.second].toBool();pair.first->setEnabled(present);
        pair.first->setToolTip(present?"Include community AUR apps. Yay and Paru use the same AUR catalog.":"Not installed. Open Manage Yay & Paru to set it up.");
    }
    QStringList warnings;for(const auto &warning:value["warnings"].toArray())warnings<<warning.toString();
    notice->setText(warnings.join(" · "));notice->setVisible(!warnings.isEmpty());
    cacheStatus->setText(QString("Local app catalog · %1%2 · refreshed %3")
        .arg(value["cached"].toBool()?"cached":"up to date",value["multilib"].toBool()?" · multilib enabled":"",QDateTime::fromSecsSinceEpoch(qint64(value["generated"].toDouble())).toString("MMM d, HH:mm")));
    refilter();QTimer::singleShot(0,this,&SoftwareCatalogPage::offerRepositorySync);
}
QString SoftwareCatalogPage::aurHelper() const {
    if(yay->isChecked()&&yay->isEnabled())return "yay";
    if(paru->isChecked()&&paru->isEnabled())return "paru";return {};
}
QString SoftwareCatalogPage::actionText(const SoftwareApp &app) const {
    if(app.installed&&!app.desktopFile.isEmpty())return "Open";
    if(app.source=="vendor")return "Install";
    if(app.source=="aur"&&aurHelper().isEmpty())return "Enable AUR";
    if(app.source=="pacman"&&!pacman->isChecked())return "Enable Pacman";
    if(!loaded)return "View app";
    if(!app.available)return needsSync?"Refresh lists":"Unavailable";
    return app.installed?"Installed":"Install";
}
void SoftwareCatalogPage::refilter(bool resetScroll) {
    const auto selected=grid->currentIndex().data(AppRole).toString();const int scroll=grid->verticalScrollBar()->value();
    const auto query=search->text().trimmed().toCaseFolded();const auto terms=query.split(' ',Qt::SkipEmptyParts);
    QTreeWidgetItem *current=tree->currentItem();const auto tags=current?current->data(0,Qt::UserRole+1).toStringList():QStringList();
    heading->setText(query.isEmpty()?(category=="top"?"Find your next favorite.":current?current->text(0):"Apps"):"Search results");
    subtitle->setText(!query.isEmpty()?"Apps and packages matching “"+search->text().trimmed()+"”":category=="top"?"Hand-picked essentials. Ready for your desktop.":category=="packages"?"Every package in your enabled repositories, including libraries and tools.":"Explore apps from your selected sources.");
    QVector<SoftwareApp> candidates=apps;QSet<QString> known;
    const bool includeAur=!query.isEmpty()&&query==aurResultsQuery.toCaseFolded();
    if(includeAur)for(const auto &app:apps)known.insert(app.id);
    if(includeAur)for(auto app:aurApps){
        app.installed=installedPackages.contains(app.package);app.installedVersion=installedPackages[app.package].toString();if(app.installed)app.installedPackage=app.package;
        if(!known.contains(app.id))candidates<<app;
        else for(auto &curated:candidates)if(curated.id==app.id){curated.version=app.version;if(curated.license.isEmpty())curated.license=app.license;break;}
    }
    QVector<SoftwareApp> shown;
    QHash<QString,int> counts;
    QVector<QPair<QString,QStringList>> categories;
    for(QTreeWidgetItemIterator i(tree);*i;++i)categories<<qMakePair((*i)->data(0,Qt::UserRole).toString(),(*i)->data(0,Qt::UserRole+1).toStringList());
    const bool pacmanEnabled=pacman->isChecked(),aurEnabled=!aurHelper().isEmpty();
    for(auto app:candidates){
        bool enabled=app.source=="vendor"||(app.source=="pacman"&&pacmanEnabled)||(app.source=="aur"&&aurEnabled);
        if(!enabled&&!(category=="top"&&query.isEmpty()&&app.featured))continue;
        if(enabled){
            if(app.categories.isEmpty()&&!app.essential&&!app.featured){if(app.source!="vendor")counts["packages"]++;}
            else for(const auto &node:categories)if(belongs(app,node.first,node.second))counts[node.first]++;
        }
        if(query.isEmpty()){if(!belongs(app,category,tags))continue;}
        else {bool match=true;for(const auto &term:terms)if(!app.searchText.contains(term)){match=false;break;}if(!match)continue;}
        app.action=actionText(app);shown<<app;
    }
    std::stable_sort(shown.begin(),shown.end(),[&](const SoftwareApp &a,const SoftwareApp &b){
        if(!query.isEmpty()){const bool ax=a.package.compare(query,Qt::CaseInsensitive)==0||a.name.compare(query,Qt::CaseInsensitive)==0;const bool bx=b.package.compare(query,Qt::CaseInsensitive)==0||b.name.compare(query,Qt::CaseInsensitive)==0;if(ax!=bx)return ax;}
        if(category=="top"&&query.isEmpty()){
            if(a.featured!=b.featured)return a.featured;
            if(a.featured&&a.featuredOrder!=b.featuredOrder)return a.featuredOrder<b.featuredOrder;
            if(a.essential!=b.essential)return a.essential;
        }
        return QString::localeAwareCompare(a.name,b.name)<0;
    });
    fitGrid();model->replace(std::move(shown));
    for(QTreeWidgetItemIterator i(tree);*i;++i){auto *node=*i;const auto id=node->data(0,Qt::UserRole).toString();node->setData(0,Qt::UserRole+2,id=="top"?QString():QLocale().toString(counts[id]));}
    count->setText(QString::number(model->rowCount())+(category=="packages"||!query.isEmpty()?" results":" apps"));
    results->setCurrentIndex(model->rowCount()?0:1);
    empty->setText(!pacman->isChecked()&&aurHelper().isEmpty()?"Choose a software source on the left.":query.isEmpty()?"No apps in this category yet.":"No matches. Try another name or enable an AUR helper.");
    fitGrid();
    if(!resetScroll){for(int i=0;i<model->entries.size();++i)if(model->entries[i].id==selected)grid->setCurrentIndex(model->index(i));grid->verticalScrollBar()->setValue(scroll);}
    else grid->scrollToTop();
}
void SoftwareCatalogPage::sourceChanged() {
    QSettings settings("XetalHyperland","ControlPanel");settings.setValue("software/catalog/pacman",pacman->isChecked());settings.setValue("software/catalog/yay",yay->isChecked());settings.setValue("software/catalog/paru",paru->isChecked());
    refilter(true);aurDelay.start();
}
void SoftwareCatalogPage::requestAur(bool force) {
    const auto query=search->text().trimmed();
    if(aurHelper().isEmpty()||query.size()<2){aurApps.clear();aurResultsQuery.clear();aurForcePending=false;refilter();return;}
    if(aurWorker.state()!=QProcess::NotRunning){aurForcePending|=force;aurDelay.start();return;}
    force|=aurForcePending;aurForcePending=false;
    if(!force&&query==aurResultsQuery)return;
    aurQuery=query;aurBuffer.clear();QStringList args{root+"/control_panel/software_catalog.py","--aur",query};if(force)args<<"--refresh";
    aurDeadline.start();aurWorker.start("python3",args);
}
void SoftwareCatalogPage::finishAur(int code,QProcess::ExitStatus exit) {
    aurDeadline.stop();aurBuffer+=aurWorker.readAllStandardOutput();
    if(search->text().trimmed()!=aurQuery||aurHelper().isEmpty()){aurDelay.start();return;}
    const auto value=QJsonDocument::fromJson(aurBuffer.trimmed()).object();
    if(value["type"]=="aur"){
        aurResultsQuery=aurQuery;aurApps.clear();for(const auto &v:value["apps"].toArray())aurApps<<SoftwareApp::fromJson(v.toObject(),root);
        const auto message=value["warning"].toString();notice->setText(message.isEmpty()?(value["truncated"].toBool()?"Showing the first 500 AUR results. Narrow your search.":"AUR results included · Yay and Paru share this community catalog."):message);notice->show();refilter();
    }else{notice->setText(value["message"].toString(exit!=QProcess::NormalExit?"AUR search timed out. Local results are still available.":"Could not search the AUR. Local results are still available."));notice->show();}
    if(aurForcePending)aurDelay.start();
    Q_UNUSED(code)
}
void SoftwareCatalogPage::details(const SoftwareApp &app) {
    QDialog dialog(this);dialog.setObjectName("softwareAppDetails");dialog.setWindowTitle(app.name);dialog.setMinimumWidth(520);dialog.resize(680,460);dialog.setProperty("xetalWindowSized",true);
    auto *layout=new QVBoxLayout(&dialog);layout->setContentsMargins(24,24,24,24);layout->setSpacing(16);
    auto *top=new QHBoxLayout;auto *icon=new QLabel;icon->setPixmap(appIcon(app).pixmap(72));top->addWidget(icon);auto *title=new QVBoxLayout;title->addWidget(words(app.name,"catalogHeading"));title->addWidget(words(app.summary));top->addLayout(title,1);layout->addLayout(top);
    auto *description=new QPlainTextEdit;description->setReadOnly(true);description->setFrameShape(QFrame::NoFrame);description->setPlainText(app.description.isEmpty()?app.summary:app.description);layout->addWidget(description,1);
    auto *facts=new QFormLayout;facts->addRow("Source",words(sourceName(app)));if(!app.package.isEmpty()&&app.source!="vendor")facts->addRow("Package",words(app.package));
    if(!app.version.isEmpty())facts->addRow("Version",words(app.version));if(!app.installedVersion.isEmpty())facts->addRow("Installed",words(app.installedVersion));if(!app.license.isEmpty())facts->addRow("License",words(app.license));layout->addLayout(facts);
    if(app.source=="aur")layout->addWidget(words("Community package · choose Yay or Paru to install. The build files are available for review before installation."));
    if(!app.debId.isEmpty())layout->addWidget(words("Also validated with the .deb installer. "+app.debNote));
    auto *installChoices=new QHBoxLayout;
    if(!app.debId.isEmpty()&&!app.installed){
        auto *package=new QPushButton(app.source=="pacman"?"Install with Pacman":aurHelper().isEmpty()?"Install with Yay / Paru":"Install with "+aurHelper());
        package->setObjectName("softwareInstallPackage");package->setEnabled(app.available||needsSync);installChoices->addWidget(package);
        package->setToolTip(app.source=="pacman"?"Install from your configured Pacman repositories.":"This app uses the community AUR; choose an installed helper.");
        connect(package,&QPushButton::clicked,&dialog,[this,&dialog,app]{dialog.accept();activate(app);});
        auto *deb=new QPushButton("Install with .deb installer");deb->setObjectName("softwareInstallDeb");installChoices->addWidget(deb);
        connect(deb,&QPushButton::clicked,&dialog,[this,&dialog,app]{dialog.accept();emit installDebRequested(app.debId);});
    }
    if(app.installed){auto *remove=new QPushButton(QIcon::fromTheme("edit-delete"),"Uninstall…");remove->setObjectName("softwareUninstallApp");installChoices->addWidget(remove);connect(remove,&QPushButton::clicked,&dialog,[this,&dialog,app]{dialog.accept();uninstall(app);});}
    if(installChoices->count()){installChoices->addStretch();layout->addLayout(installChoices);}else delete installChoices;
    auto *buttons=new QHBoxLayout;QUrl website(app.website);
    if((website.scheme()=="https"||website.scheme()=="http")&&!website.host().isEmpty()){
        auto *site=new QPushButton("Official website ↗");buttons->addWidget(site);connect(site,&QPushButton::clicked,&dialog,[website]{QDesktopServices::openUrl(website);});
    }
    if(app.source=="vendor"&&app.installed){auto *downloads=new QPushButton("Linux downloads…");buttons->addWidget(downloads);connect(downloads,&QPushButton::clicked,&dialog,[this,app]{vendorDownloads(app);});}
    buttons->addStretch();auto *close=new QPushButton("Close");buttons->addWidget(close);connect(close,&QPushButton::clicked,&dialog,&QDialog::reject);
    auto *action=new QPushButton(actionText(app));action->setObjectName("catalogAction");action->setEnabled(action->text()!="Unavailable"&&action->text()!="Installed");action->setVisible(app.debId.isEmpty()||app.installed);buttons->addWidget(action);
    connect(action,&QPushButton::clicked,&dialog,[this,&dialog,app]{dialog.accept();activate(app);});layout->addLayout(buttons);dialog.exec();
}
void SoftwareCatalogPage::vendorDownloads(const SoftwareApp &app) {
    QDialog dialog(this);dialog.setObjectName("softwareVendorDownloads");dialog.setWindowTitle(app.name+" · Install");dialog.setMinimumWidth(540);dialog.resize(620,390);dialog.setProperty("xetalWindowSized",true);
    auto *layout=new QVBoxLayout(&dialog);layout->setContentsMargins(24,24,24,24);layout->setSpacing(14);
    auto *top=new QHBoxLayout;auto *icon=new QLabel;icon->setPixmap(appIcon(app).pixmap(56));top->addWidget(icon);auto *title=new QVBoxLayout;title->addWidget(words(app.name,"catalogHeading"));auto *status=words("Checking the latest Linux release on xetal.net…");title->addWidget(status);top->addLayout(title,1);layout->addLayout(top);
    auto *choices=new QComboBox;choices->setObjectName("softwareDownloadFormat");choices->setEnabled(false);layout->addWidget(choices);
    auto *filename=words({});filename->setTextInteractionFlags(Qt::TextSelectableByMouse);layout->addWidget(filename);
    auto *instructions=words("Install for your account and add the app to Favorites.");layout->addWidget(instructions);layout->addStretch();
    auto *buttons=new QHBoxLayout;auto *site=new QPushButton("Official downloads ↗");buttons->addWidget(site);
    connect(site,&QPushButton::clicked,&dialog,[app]{QUrl url(app.website);url.setFragment("download");if(url.scheme()=="https"&&url.host()=="www.xetal.net")QDesktopServices::openUrl(url);});
    auto *retry=new QPushButton("Retry");retry->hide();buttons->addWidget(retry);buttons->addStretch();auto *close=new QPushButton("Close");buttons->addWidget(close);connect(close,&QPushButton::clicked,&dialog,&QDialog::reject);
    auto *download=new QPushButton("Install");download->setObjectName("catalogAction");download->setEnabled(false);buttons->addWidget(download);layout->addLayout(buttons);
    QProcess worker;QTimer timeout;timeout.setSingleShot(true);timeout.setInterval(18000);QByteArray buffer;
    auto load=[&]{if(worker.state()!=QProcess::NotRunning)return;buffer.clear();retry->hide();choices->clear();choices->setEnabled(false);download->setEnabled(false);status->setText("Checking the latest Linux release on xetal.net…");timeout.start();worker.start("python3",{root+"/control_panel/software_catalog.py","--vendor",app.package});};
    connect(retry,&QPushButton::clicked,&dialog,load);
    connect(&timeout,&QTimer::timeout,&dialog,[&]{worker.kill();});
    connect(&worker,&QProcess::readyReadStandardOutput,&dialog,[&]{buffer+=worker.readAllStandardOutput();if(buffer.size()>1024*1024)worker.kill();});
    connect(&worker,&QProcess::errorOccurred,&dialog,[&](QProcess::ProcessError error){if(error==QProcess::FailedToStart){timeout.stop();status->setText("Could not check downloads. Open the official downloads page or retry.");retry->show();}});
    connect(&worker,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),&dialog,[&](int,QProcess::ExitStatus){
        timeout.stop();buffer+=worker.readAllStandardOutput();const auto data=QJsonDocument::fromJson(buffer.trimmed()).object();
        if(data["type"]!="vendor"||data["product"].toString()!=app.package){status->setText(data["message"].toString("Could not check downloads. Open the official downloads page or retry."));retry->show();return;}
        for(const auto &value:data["choices"].toArray()){
            const auto choice=value.toObject();QUrl url(choice["url"].toString());if(url.scheme()!="https"||url.host()!="www.xetal.net"||!url.userInfo().isEmpty())continue;
            const auto size=QLocale().formattedDataSize(qint64(choice["size"].toDouble()));choices->addItem(choice["label"].toString()+" · "+size,choice.toVariantMap());
        }
        choices->setEnabled(choices->count()>0);download->setEnabled(choices->count()>0);
        status->setText(choices->count()?"Linux · version "+data["version"].toString()+" · from xetal.net":"No Linux download is available. Try the official downloads page.");
    });
    connect(choices,qOverload<int>(&QComboBox::currentIndexChanged),&dialog,[&]{const auto choice=choices->currentData().toMap();filename->setText(choice["filename"].toString());instructions->setText(choice["instructions"].toString());
        const auto file=choice["filename"].toString();download->setText(file.endsWith(".run")||(app.package=="linuxstudio"&&file.endsWith(".tar.gz"))?"Install":"Download only");});
    connect(download,&QPushButton::clicked,&dialog,[&]{
        if(download->text()=="Install"){
            if(installVendorApplication(&dialog,root,app)){requestCatalog(true);emit packagesChanged();dialog.accept();}
        }else saveVendorDownload(&dialog,root,app,choices->currentData().toMap());
    });
    load();dialog.exec();timeout.stop();worker.disconnect(&dialog);if(worker.state()!=QProcess::NotRunning){worker.kill();worker.waitForFinished(1000);}
}
void SoftwareCatalogPage::activate(const SoftwareApp &app) {
    if(app.installed&&!app.desktopFile.isEmpty()){
        if(!QFileInfo(app.desktopFile).isFile()){notice->setText("The app launcher is no longer available. Refresh the catalog.");notice->show();return;}
        if(!QProcess::startDetached("gio",{"launch",app.desktopFile})){notice->setText("Could not open "+app.name+".");notice->show();}return;
    }
    if(app.source=="vendor"){vendorDownloads(app);return;}
    if(app.source=="aur"&&aurHelper().isEmpty()){
        if(yay->isEnabled())yay->setChecked(true);else if(paru->isEnabled())paru->setChecked(true);else emit openTool("aur");return;
    }
    if(app.source=="pacman"&&!pacman->isChecked()){pacman->setChecked(true);return;}
    if(!loaded){requestCatalog();notice->setText("Checking package availability. Select the app again when the catalog is ready.");notice->show();return;}
    if(!app.available){if(needsSync)syncRepositories();return;}
    if(app.installed)return;
    static const QRegularExpression packagePattern("^[a-zA-Z0-9@_+][a-zA-Z0-9@_.+\\-]*$");
    if(!packagePattern.match(app.package).hasMatch())return;
    const QString helper=app.source=="aur"?aurHelper():"pacman";
    const QString target=app.source=="pacman"&&!app.repository.isEmpty()?app.repository+'/'+app.package:app.package;
    QMessageBox prompt(QMessageBox::Question,"Install "+app.name,"Install "+app.name+" using "+(helper=="pacman"?"Pacman":helper=="yay"?"Yay":"Paru")+"?",QMessageBox::Yes|QMessageBox::No,this);
    prompt.setTextFormat(Qt::PlainText);prompt.setProperty("xetalWindowSized",true);
    prompt.setInformativeText(helper=="pacman"?"Review the full package transaction in the terminal. Pending system updates are included.":"Review the community build files and package transaction in the terminal.");
    if(prompt.exec()!=QMessageBox::Yes)return;
    qint64 pid=0;const QString script=PackageInstall::script(helper,helper=="pacman"?"Pacman":helper=="yay"?"Yay":"Paru",target,false,SoftwareActions::pinCommand(root,target));
    if(!QProcess::startDetached(terminal,{"-e","bash","-c",script},{},&pid)){notice->setText("Could not open the installation terminal.");notice->show();return;}
    notice->setText("Review and confirm the installation in the terminal.");notice->show();
    TerminalExit::watch(this,pid,[this]{requestCatalog(true);emit packagesChanged();});
}
void SoftwareCatalogPage::uninstall(const SoftwareApp &app) {
    if(!app.installed)return;
    QString package=app.installedPackage;
    if(package.isEmpty()&&installedPackages.contains(app.package))package=app.package;
    if(package.isEmpty()&&!app.desktopFile.isEmpty()){
        QProcess owner;owner.start("pacman",{"-Qqo","--",app.desktopFile});
        if(owner.waitForFinished(2000)&&owner.exitCode()==0)package=QString::fromUtf8(owner.readAllStandardOutput()).trimmed();
    }
    if(!package.isEmpty()){
        const QString script=SoftwareActions::removePackage(package);if(script.isEmpty())return;
        QMessageBox prompt(QMessageBox::Question,"Uninstall "+app.name,"Uninstall "+app.name+"?",QMessageBox::Yes|QMessageBox::No,this);
        prompt.setObjectName("softwareUninstallConfirm");prompt.setTextFormat(Qt::PlainText);
        prompt.setInformativeText("Package: "+package+"\nReview and confirm removal in the terminal. Your personal settings and files are kept.");prompt.setDefaultButton(QMessageBox::No);
        if(prompt.exec()!=QMessageBox::Yes)return;
        qint64 pid=0;if(!QProcess::startDetached(terminal,{"-e","bash","-c",script},{},&pid)){notice->setText("Could not open the uninstall terminal.");notice->show();return;}
        notice->setText("Review and confirm removal in the terminal.");notice->show();
        TerminalExit::watch(this,pid,[this]{requestCatalog(true);emit packagesChanged();});return;
    }
    const auto paths=SoftwareActions::localRemovalPaths(app.package,app.desktopFile);
    if(paths.isEmpty()){
        QMessageBox::information(this,"Uninstall "+app.name,"This app uses a custom or portable installation that Software does not manage. Use its original uninstaller or remove its portable copy.\n\nLauncher: "+app.desktopFile);return;
    }
    QMessageBox prompt(QMessageBox::Question,"Uninstall "+app.name,"Move this app and its launcher to Trash?",QMessageBox::Yes|QMessageBox::No,this);
    prompt.setTextFormat(Qt::PlainText);prompt.setDefaultButton(QMessageBox::No);
    prompt.setInformativeText(paths.join('\n')+"\n\nSettings outside this installation folder are kept. You can restore the app from Trash.");
    if(prompt.exec()!=QMessageBox::Yes)return;
    if(paths!=SoftwareActions::localRemovalPaths(app.package,app.desktopFile)){QMessageBox::warning(this,"Uninstall stopped","The installation changed. Refresh the catalog and try again.");return;}
    for(const auto &path:paths){if(!QFile::moveToTrash(path)){QMessageBox::warning(this,"Uninstall incomplete","Could not move to Trash: "+path);break;}}
    requestCatalog(true);emit packagesChanged();
}
