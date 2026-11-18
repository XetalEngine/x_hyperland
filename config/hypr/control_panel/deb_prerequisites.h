#pragma once
#include "aur_helpers.h"
#include <QMessageBox>
#include <QStringList>

namespace HyperPanel {
enum class DebHelpers { Ready, InstallBoth, Cancel };

inline DebHelpers confirmDebHelpers(QWidget *parent, bool checkOnly) {
  if (checkOnly || aurHelperInstalled("yay") || aurHelperInstalled("paru"))
    return DebHelpers::Ready;
  QMessageBox prompt(QMessageBox::Question, "Install .deb",
      "This requires Yay or Paru. Install now?", QMessageBox::Yes | QMessageBox::No, parent);
  prompt.setObjectName("debHelperPrompt");
  prompt.setProperty("xetalWindowSized", true);
  prompt.setTextFormat(Qt::PlainText);
  prompt.setInformativeText("Yes installs both Yay and Paru, then continues with your .deb in the same terminal.");
  prompt.setDefaultButton(QMessageBox::Yes);
  return prompt.exec() == QMessageBox::Yes ? DebHelpers::InstallBoth : DebHelpers::Cancel;
}

inline QStringList debTerminalArguments(const QString &root, const QString &file,
                                       bool checkOnly, DebHelpers helpers) {
  if (helpers == DebHelpers::Cancel) return {};
  if (!checkOnly && helpers == DebHelpers::InstallBoth)
    return {"-e", "python3", root + "/control_panel/aur_helper_install.py", "--wait", "--deb", file, "both"};
  QStringList args{"-e", "python3", root + "/control_panel/deb_install.py", "--wait"};
  if (checkOnly) args << "--check";
  return args << "--" << file;
}
}
