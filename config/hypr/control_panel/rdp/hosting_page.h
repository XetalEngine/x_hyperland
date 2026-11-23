#pragma once
#include <QJsonObject>
#include <QProcess>
#include <QWidget>

class QCheckBox;
class QComboBox;
class QGroupBox;
class QLabel;
class QLineEdit;
class QPlainTextEdit;
class QPushButton;
class QSpinBox;
class QTimer;

namespace FusionRdp {
class HostingPage : public QWidget {
    Q_OBJECT
public:
    explicit HostingPage(const QString &root, QWidget *parent = nullptr);
    ~HostingPage() override;
protected:
    void showEvent(QShowEvent *event) override;
    void hideEvent(QHideEvent *event) override;
private:
    QString root, action, pendingAction;
    QProcess *process;
    QTimer *poll, *deadline;
    QGroupBox *setup;
    QComboBox *protocol, *output, *address;
    QSpinBox *port, *fps;
    QLineEdit *username, *password;
    QCheckBox *control, *automatic;
    QLabel *state, *connection, *fingerprint, *hint, *message;
    QPlainTextEdit *log;
    QPushButton *refresh, *install, *save, *start, *stop;
    QJsonObject components;
    QByteArray response;
    bool loaded = false, busy = false, running = false, responseTooLarge = false;
    bool hasPassword = false, failed = false;
    void request(const QString &operation);
    void finished(int code);
    void populate(const QJsonObject &result);
    void display(const QJsonObject &result);
    void updateActions();
    void protocolChanged(bool resetPort = true);
    void addressChanged();
    bool passwordValid() const;
    void operationMessage(const QString &operation);
    QJsonObject values() const;
};
}
