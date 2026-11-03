"""Transfer questions embedded below the selected style's animated card."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
try:
    from .model import short_location
except ImportError:
    from model import short_location


class Symbol(QWidget):
    def __init__(self, choice, parent):
        super().__init__(parent)
        self.choice = choice
        self.setFixedSize(26, 28)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.parentWidget().parentWidget().accent, 1.7,
                           Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        if self.choice in ('replace', 'copy'):
            painter.drawRoundedRect(9, 8, 13, 16, 2, 2)
            painter.drawLine(5, 18, 3, 18); painter.drawLine(3, 18, 3, 3); painter.drawLine(3, 3, 16, 3)
            painter.drawLine(12, 16, 19, 16)
            if self.choice == 'copy': painter.drawLine(16, 12, 16, 20)
            else:
                painter.drawLine(16, 12, 20, 16); painter.drawLine(20, 16, 16, 20)
        elif self.choice == 'skip':
            painter.drawArc(3, 5, 18, 18, 40*16, 275*16)
            painter.drawLine(20, 5, 20, 12); painter.drawLine(20, 12, 13, 12)
        else:
            for y in (7, 14, 21):
                painter.drawPoint(QPointF(4, y)); painter.drawLine(10, y, 22, y)


class ChoiceButton(QPushButton):
    def __init__(self, choice, title, description, parent):
        super().__init__(parent)
        self.setObjectName('transferChoice')
        self.setProperty('choice', choice)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(64)
        row = QHBoxLayout(self); row.setContentsMargins(12, 10, 12, 10); row.setSpacing(12)
        row.addWidget(Symbol(choice, self), 0, Qt.AlignmentFlag.AlignVCenter)
        words = QVBoxLayout(); words.setSpacing(3)
        for text, name in ((title, 'choiceTitle'), (description, 'choiceDescription')):
            label = QLabel(text, self); label.setObjectName(name)
            label.setTextFormat(Qt.TextFormat.PlainText); label.setWordWrap(True)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            words.addWidget(label)
        row.addLayout(words, 1)


class QuestionPanel(QWidget):
    def __init__(self, job, accent, parent=None):
        super().__init__(parent)
        self.job = job
        self.accent = accent
        self.setObjectName('transferQuestion')
        self.setCursor(Qt.CursorShape.ArrowCursor)
        question = job.question
        self.kind = question['kind']
        self.apply_all = None
        layout = QVBoxLayout(self); layout.setContentsMargins(8, 12, 8, 12); layout.setSpacing(9)
        title = ('The files are already in this folder.' if self.kind == 'duplicate'
                 else f'“{short_location(question["destination"])}” already exists.' if self.kind == 'file'
                 else 'The destination has files with the same names.')
        heading = QLabel(title, self); heading.setObjectName('questionHeading')
        heading.setWordWrap(True); heading.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(heading)
        if self.kind == 'duplicate':
            self.add('copy', 'Copy anyway', 'Keep the originals. Name the new copies _copy1, _copy2, and so on.')
        elif self.kind == 'conflicts':
            self.add('replace', 'Replace the files in the destination', 'Overwrite matching files, including those in subfolders.')
            self.add('skip', 'Skip these files', 'Keep existing files. Still transfer all new files, including those in matching folders.')
            self.add('individual', 'Let me decide for each file', 'Choose which matching files to replace and which to skip.')
        else:
            for caption, value in (('From', question['source']), ('To', question['destination'])):
                label = QLabel(caption + ': ' + value, self); label.setObjectName('questionPath')
                label.setTextFormat(Qt.TextFormat.PlainText); label.setWordWrap(True)
                label.setMaximumHeight(54); label.setToolTip(value); layout.addWidget(label)
            if question['replace_allowed']:
                self.add('replace', 'Replace this file', 'Overwrite the existing file with the incoming one.')
            self.add('skip', 'Skip this file', 'Keep the existing file and continue with the rest.')
            self.apply_all = QCheckBox('Do this for all conflicts, including subfolders', self)
            self.apply_all.setObjectName('applyToAllConflicts')
            layout.addWidget(self.apply_all)
        layout.addStretch()

    def add(self, choice, title, description):
        button = ChoiceButton(choice, title, description, self)
        button.clicked.connect(lambda: self.job.answer(choice, bool(self.apply_all and self.apply_all.isChecked())))
        self.layout().addWidget(button)
