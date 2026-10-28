// Native-plugin integration probe: compile/run against both supported Qt majors.
#include <QApplication>
#include <QDialogButtonBox>
#include <QFileDialog>
#include <QImage>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QScrollArea>
#include <QSettings>
#include <QTemporaryDir>
#include <QTest>
#include <QTimer>
#include <cstdio>
#include <functional>

static void check(bool ok, const char *message) { if (!ok) { fprintf(stderr,"FAIL: %s\n",message); exit(1); } }
static void waitFor(const std::function<bool()> &condition) {
    for (int i=0; i<200 && !condition(); ++i) QTest::qWait(10);
    check(condition(), "preview completion");
}
int main(int argc, char **argv) {
    QApplication app(argc,argv); QTemporaryDir files;
    QSettings::setPath(QSettings::NativeFormat,QSettings::UserScope,files.path());
    QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,files.path());
    const auto picture=files.filePath("picture.png"), text=files.filePath("preset.json");
    QImage image(800,400,QImage::Format_RGB32);image.fill(Qt::red);image.save(picture);
    QFile file(text);check(file.open(QIODevice::WriteOnly),"create fixture");file.write("{\"enabled\":true}");file.close();
    // Show before processing the platform theme's startup callback.
    auto first=new QFileDialog(nullptr,"Choose cube picture",files.path());
    first->setOption(QFileDialog::DontUseNativeDialog);first->show();
    waitFor([&]{return first->property("xetalFilePreview").toBool();});
    check(first->findChildren<QScrollArea *>("xetalFilePreviewPane").size()==1,"one preview pane");
    first->currentChanged(picture);
    auto label=first->findChild<QLabel *>("xetalPreviewImage");
    waitFor([&]{return !label->pixmap(Qt::ReturnByValue).isNull();});
    auto pixmap=label->pixmap(Qt::ReturnByValue);check(pixmap.width()==2*pixmap.height(),"image aspect ratio");
    first->currentChanged(text);
    auto excerpt=first->findChild<QPlainTextEdit *>("xetalPreviewText");
    waitFor([&]{return excerpt->toPlainText()=="{\"enabled\":true}";});
    check(excerpt->isReadOnly(),"read-only excerpt");
    if (argc>1) first->grab().save(argv[1]);
    first->currentChanged(picture);QTest::qWait(105);delete first;QTest::qWait(50);
    for (auto mode : {QFileDialog::ExistingFile,QFileDialog::ExistingFiles,QFileDialog::AnyFile,QFileDialog::Directory}) {
        QFileDialog dialog(nullptr,"Files",files.path());dialog.setOption(QFileDialog::DontUseNativeDialog);
        dialog.setFileMode(mode);if(mode==QFileDialog::AnyFile)dialog.setAcceptMode(QFileDialog::AcceptSave);
        dialog.selectFile(mode==QFileDialog::Directory ? files.path() : picture);
        const auto selected=dialog.selectedFiles();dialog.show();QTest::qWait(30);
        check(dialog.property("xetalFilePreview").toBool(),"all dialog modes");
        check(dialog.fileMode()==mode && dialog.selectedFiles()==selected,"unchanged selection and mode");
        dialog.hide();dialog.show();QTest::qWait(10);
        check(dialog.findChildren<QScrollArea *>("xetalFilePreviewPane").size()==1,"no duplicate on reopen");
        dialog.reject();
    }
    QTimer::singleShot(100,[&]{
        auto dialog=qobject_cast<QFileDialog *>(app.activeModalWidget());check(dialog,"static picker");
        check(dialog->property("xetalFilePreview").toBool(),"static picker preview");
        dialog->findChild<QLineEdit *>("fileNameEdit")->setText(picture);
        dialog->findChild<QDialogButtonBox *>()->button(QDialogButtonBox::Open)->click();
    });
    QTimer guard;guard.setSingleShot(true);QObject::connect(&guard,&QTimer::timeout,[&]{check(false,"static dialog timeout");});guard.start(3000);
    QString filter;
    const auto chosen=QFileDialog::getOpenFileName(nullptr,"Open",files.path(),"Images (*.png)",&filter,QFileDialog::DontUseNativeDialog);
    check(chosen==picture && filter=="Images (*.png)","static picker acceptance");guard.stop();
    printf("Qt %s: previews, image/text selection, modes, close/reopen and acceptance passed\n",QT_VERSION_STR);
}
