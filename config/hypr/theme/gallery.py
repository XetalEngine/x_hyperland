"""Searchable preset banners with an independent, accessible wallpaper reveal."""
import importlib

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QFont, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                            QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

import runtime
import wallpaper_sets


# Presentation only: selecting a banner still uses the normal component chooser.
STORIES = {
    'ghostbusters': ('GHOSTBUSTERS', 'A little slime.\nA lot of spirit.', 'ghostbusters ghost busters slimer geleia ecto slime green neon cartoon firehouse'),
    'leviathan': ('LEVIATHAN', 'Beyond the labyrinth.\nObsidian. Brass. Amethyst.', 'leviathan labyrinth puzzle cube gothic hellraiser cenobite pinhead obsidian brass gold violet purple storm'),
    'polaris': ('POLARIS', 'A familiar friend. A brighter horizon.\nMidnight. Cyan. Starlight.', 'polaris tux linux penguin navy cyan blue violet aurora north star orbit glass'),
    'infernalencore': ('INFERNAL\nENCORE', 'One last riff. All the fire.\nGraphite. Brass. Crimson.', 'infernal encore heavy metal gothic concert guitar fire red crimson brass skull purple'),
    'midnightrun': ('MIDNIGHT RUN', 'After hours. In full color.\nGraphite. Cyan. Magenta.', 'midnight run tokyo japan neon cyan magenta pink graphite car sports sedan sakura rain city night audi a4 2014 slammed stance rs6 avant wagon bay mountain'),
    'platform95': ('PLATFORM 95', 'A familiar desktop. A golden departure.\nIvory. Espresso. Antique gold.', 'platform 95 classic retro windows beige ivory brown espresso gold brass railway train station beveled'),
    'mycelium': ('MYCELIUM', 'Small lights. Hidden worlds.\nPlum velvet. Ivory roots.', 'mycelium mushroom forest roots purple lilac lavender spores moss fantasy'),
    'atomicafterglow': ('ATOMIC AFTERGLOW', 'Quiet power. Lasting light.\nGraphite. Brass. Phosphor.', 'atomic afterglow reactor nuclear green lime olive industrial brass graphite'),
    'blackwood': ('BLACKWOOD', 'A light on the coast.\nWalnut. Brass. Quiet sage.', 'blackwood walnut wood brass sage green lighthouse coastal classic serif'),
    'midnighttransit': ('MIDNIGHT\nTRANSIT', 'The last train. The first idea.\nTeal enamel. Amber light.', 'teal amber cream nickel enamel train railway station rain midnight transit'),
    'hyperfusionblue': ('HYPERFUSION\nBLUE', 'Power in plain sight.\nAlpine blue. Polished silver.', 'blue sapphire alpine lake mountain chrome silver classic glass hyperfusion'),
    'gildedhollow': ('THE GILDED\nHOLLOW', 'Quiet stone. Living gold.\nA little light from deep within.', 'gold brass green moss cave cavern dwarves lantern mining fantasy gilded hollow'),
    'hollowgrove': ('HOLLOW\nGROVE', 'A quieter kind of magic.\nMoonlit sage. Silver blossoms.', 'forest green sage moon botanical fantasy mist nature'),
    'raw': ('XETAL\nRAW', 'Your original world.\nElectric nights. Open possibilities.', 'cyan neon original xetal world'),
    'modern': ('Xetal\nModern', 'Room to think.\nSoft surfaces. A clearer workspace.', 'blue calm cards xetal world'),
    'breakpoint': ('BREAK\nPOINT', 'Break the routine.\nCharcoal glass. A pulse of crimson.', 'red crimson cyberpunk xetal world'),
    'binaryknife': ('BINARY\nKNIFE', 'Precision after dark.\nGraphite cut with electric blue.', 'blue circuits digital xetal world'),
    'tidalglass': ('TIDAL\nGLASS', 'A little calm. A little clarity.\nLight from a world beneath the waves.', 'ocean water teal blue atmospheres'),
    'porcelainink': ('Porcelain\nInk', 'A quieter desktop.\nWarm porcelain. A brush of vermilion.', 'japan warm paper painting atmospheres'),
    'obsidianforge': ('OBSIDIAN\nFORGE', 'Forged in the dark.\nBasalt, copper and living embers.', 'lava volcano orange fire atmospheres'),
    'candycloud': ('Candy\nCloud', 'Softer worlds. Higher focus.\nPearl clouds and a little starlight.', 'pink purple pastel fantasy atmospheres'),
    'shadowedge': ('SHADOW\nEDGE', 'Move in silence.\nSmoked glass, silver and crimson rain.', 'ninja moon black silver red rain'),
}
FOCAL_TOP = {'modern': .05, 'shadowedge': .08}
THUMBNAIL_FOCAL_TOP = {
    'audi-a4-sakura-stance.png': .95,
    'audi-a4-neon-profile.png': .95,
    'audi-a4-midnight-return.png': .95,
}


def caption(path):
    return path.stem.replace('-', ' ').title()


def picture(path, width):
    """Decode only visible artwork, bounded to its display size."""
    reader = QImageReader(str(path)); reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() > width:
        reader.setScaledSize(size.scaled(width, width, Qt.AspectRatioMode.KeepAspectRatio))
    return QPixmap.fromImage(reader.read())


def cover(painter, pixmap, box, top=.35):
    if pixmap.isNull(): return
    scale = max(box.width()/pixmap.width(), box.height()/pixmap.height())
    width, height = pixmap.width()*scale, pixmap.height()*scale
    target = QRectF(box.center().x()-width/2, box.top()-(height-box.height())*top, width, height)
    painter.save(); painter.setClipRect(box, Qt.ClipOperation.IntersectClip)
    painter.drawPixmap(target, pixmap, QRectF(pixmap.rect())); painter.restore()


def shape(box, design):
    if design == 'shadowedge':
        from shadowedge import cut_path
        return cut_path(box, 14)
    path = QPainterPath()
    radius = {'ghostbusters': 10, 'leviathan': 6, 'polaris': 12, 'infernalencore': 5, 'midnightrun': 7, 'platform95': 1, 'mycelium': 14, 'atomicafterglow': 5, 'blackwood': 5, 'midnighttransit': 7, 'hyperfusionblue': 9, 'candycloud': 26, 'porcelainink': 2, 'obsidianforge': 3, 'binaryknife': 3,
              'breakpoint': 8, 'tidalglass': 20}.get(design, 16)
    path.addRoundedRect(box, radius, radius)
    return path


class WallpaperReveal(QPushButton):
    """Preview while hovered or keyboard-focused, without a persistent open state."""
    def __init__(self, card):
        super().__init__(card)
        self.card = card; self.amount = 0.; self.hovered = False; self.pictures = None
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus); self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAccessibleName(f'Preview {runtime.DESIGNS[card.design]} wallpapers')
        names = ', '.join(caption(path) for path in card.paths)
        self.setAccessibleDescription(f'Wallpapers: {names}. Hover or focus to preview. Move away, move focus away, or press Escape to close. Does not apply the theme.')
        self.animation = QVariantAnimation(self); self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.animate)

    def animate(self, value):
        self.amount = float(value); self.card.position_wallpapers(); self.update()

    def reveal(self):
        self.animation.stop()
        if not self.isVisible():
            self.animate(0.); return
        opened = self.hovered or self.hasFocus()
        if opened and self.pictures is None:
            self.pictures = [picture(path, 540) for path in self.card.paths]
        self.animation.setStartValue(self.amount)
        self.animation.setEndValue(1. if opened else 0.); self.animation.start()

    def enterEvent(self, event):
        self.hovered = True; self.reveal(); super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False; self.clearFocus(); self.reveal(); super().leaveEvent(event)

    def focusInEvent(self, event):
        self.reveal(); super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.reveal(); super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hovered = False
            self.card.setFocus(Qt.FocusReason.OtherFocusReason); self.reveal(); event.accept()
        else: super().keyPressEvent(event)

    def hideEvent(self, event):
        self.animation.stop(); self.hovered = False; self.animate(0.)
        super().hideEvent(event)

    def preview_boxes(self):
        area = QRectF(self.rect()).adjusted(18, 12, -18, -10)
        count = max(1, len(self.card.paths)); columns = 3 if count > 6 else 2 if count > 3 else 1
        rows = (count+columns-1)//columns
        width = (area.width()-(columns-1)*6)/columns
        height = (area.height()-50-(rows-1)*6)/rows
        return [QRectF(area.left()+(i%columns)*(width+6), area.top()+25+(i//columns)*(height+6), width, height)
                for i in range(count)]

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        colors = runtime.colors(self.card.mode, self.card.design)
        area = QRectF(self.rect()).adjusted(18, 12, -18, -10)
        p.save(); p.setOpacity(1-self.amount)
        title, story, _ = STORIES.get(self.card.design, (runtime.DESIGNS[self.card.design], runtime.designs.DESCRIPTIONS[self.card.design], ''))
        serif = self.card.design in ('porcelainink','blackwood')
        font = QFont('Noto Serif' if serif else 'Inter', 27 if area.width() >= 280 else 22,
                     QFont.Weight.DemiBold if self.card.design in ('candycloud', 'modern', 'breakpoint') else QFont.Weight.Light)
        if self.card.design not in ('candycloud', 'modern', 'porcelainink'):
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        p.setFont(font); p.setPen(QColor(colors['Text']))
        p.drawText(QRectF(area.left(), area.top()+2, area.width(), 100), Qt.AlignmentFlag.AlignTop, title)
        p.setPen(QColor(colors['PlaceholderText'])); p.setFont(QFont('Inter', 9))
        p.drawText(QRectF(area.left(), area.top()+105, area.width(), 46), Qt.TextFlag.TextWordWrap, story)
        for i, key in enumerate(('Window', 'Midlight', 'Link', 'Accent')):
            swatch = QRectF(area.left()+i*31, area.top()+164, 21, 9)
            p.setPen(QPen(QColor(colors['Midlight']), .6)); p.setBrush(QColor(colors[key])); p.drawRoundedRect(swatch, 2, 2)
        p.setPen(QColor(colors['Link'])); p.setFont(QFont('Inter', 9, QFont.Weight.DemiBold))
        p.drawText(QRectF(area.left(), area.bottom()-26, area.width(), 24), Qt.AlignmentFlag.AlignVCenter,
                   f'{len(self.card.paths)} wallpapers   ↗')
        p.restore()
        if self.amount > 0:
            p.save(); p.setOpacity(self.amount)
            p.setPen(QColor(colors['Link'])); p.setFont(QFont('Inter', 8, QFont.Weight.DemiBold))
            p.drawText(QRectF(area.left(), area.top(), area.width(), 18), Qt.AlignmentFlag.AlignVCenter, 'YOUR WALLPAPER SET')
            for i, (path, pixmap, box) in enumerate(zip(self.card.paths, self.pictures or [], self.preview_boxes())):
                p.save(); p.setClipPath(shape(box, self.card.design))
                p.fillRect(box, QColor(colors['Base']))
                cover(p, pixmap, box, THUMBNAIL_FOCAL_TOP.get(path.name, FOCAL_TOP.get(self.card.design, .35)))
                fade = QLinearGradient(box.topLeft(), box.bottomLeft())
                fade.setColorAt(0, QColor(0, 0, 0, 0)); fade.setColorAt(1, QColor(0, 0, 0, 210)); p.fillRect(box, fade)
                p.setFont(QFont('Inter', 8, QFont.Weight.DemiBold)); p.setPen(QColor('#ffffff'))
                name = p.fontMetrics().elidedText(f'{i+1:02}   {caption(path)}', Qt.TextElideMode.ElideRight, int(box.width()-16))
                p.drawText(box.adjusted(8, 0, -8, -5), Qt.AlignmentFlag.AlignBottom, name); p.restore()
            p.restore()
        if self.hasFocus():
            p.setPen(QPen(QColor(colors['Accent']), 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(3, 3, -3, -3), 6, 6)


class DesignCard(QPushButton):
    def __init__(self, design, paths, parent=None):
        super().__init__(parent)
        self.design = design; self.mode = 'dark'; self.paths = paths; self.hero = None
        self.setCheckable(True); self.setFixedHeight(304); self.setMinimumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(runtime.DESIGNS[design])
        self.setAccessibleDescription(runtime.designs.DESCRIPTIONS[design]+'. Select to choose which components to apply.')
        self.wallpapers = WallpaperReveal(self)

    def sizeHint(self): return QSize(920, 304)

    def position_wallpapers(self):
        width = max(250, min(430, round(self.width()*.34)))
        if len(self.paths) > 6:
            expanded = max(width, min(430, self.width()-32))
            width = round(width+(expanded-width)*self.wallpapers.amount)
        self.wallpapers.setGeometry(self.width()-width-16, 16, width, 232)

    def resizeEvent(self, event):
        self.position_wallpapers()
        super().resizeEvent(event)

    def nextCheckState(self):
        # The owner decides the selection after its component chooser is accepted.
        pass

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        colors = runtime.colors(self.mode, self.design); box = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self.design in ('shadowedge', 'candycloud', 'obsidianforge', 'porcelainink', 'tidalglass', 'hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow','mycelium','platform95','midnightrun','infernalencore','polaris','leviathan','ghostbusters'):
            importlib.import_module(self.design).paint_surface(p, box, colors, focused=self.isChecked())
        else:
            shade = QLinearGradient(box.topLeft(), box.bottomRight())
            shade.setColorAt(0, QColor(colors['AlternateBase'])); shade.setColorAt(1, QColor(colors['Window']))
            p.fillPath(shape(box, self.design), shade)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(colors['Accent'] if self.isChecked() or self.hasFocus() else colors['Midlight']), 2 if self.isChecked() or self.hasFocus() else 1))
        p.drawPath(shape(box, self.design))
        scene = box.adjusted(12, 12, -12, -54)
        art = QRectF(scene.left(), scene.top(), self.wallpapers.x()-scene.left()+50, scene.height())
        if self.hero is None:
            index = min(1, len(self.paths)-1) if self.design not in ('tidalglass','hyperfusionblue','midnighttransit','blackwood','atomicafterglow','mycelium','platform95','midnightrun','infernalencore','polaris','leviathan','ghostbusters') else 0
            self.hero = picture(self.paths[index], 1440) if self.paths else QPixmap()
        p.save(); p.setClipPath(shape(scene, self.design))
        p.fillRect(scene, QColor(colors['Base'])); cover(p, self.hero, art, FOCAL_TOP.get(self.design, .35))
        fade = QLinearGradient(art.right()-min(220, art.width()*.35), 0, art.right(), 0)
        transparent = QColor(colors['Base']); transparent.setAlpha(0)
        fade.setColorAt(0, transparent); fade.setColorAt(1, QColor(colors['Base'])); p.fillRect(art, fade)
        p.restore()
        # A small theme-specific signature keeps the artwork dominant.
        p.setPen(QPen(QColor(colors['Accent']), 2))
        if self.design in ('shadowedge', 'binaryknife', 'breakpoint'):
            p.drawLine(QPointF(box.left()+18, box.bottom()-13), QPointF(box.left()+39, box.bottom()-35))
        else:
            p.drawLine(QPointF(box.left()+18, box.bottom()-24), QPointF(box.left()+37, box.bottom()-24))
        left = box.left()+49
        p.setFont(QFont('Inter', 11, QFont.Weight.DemiBold)); p.setPen(QColor(colors['Text']))
        p.drawText(QRectF(left, box.bottom()-45, box.width()-245, 23), Qt.AlignmentFlag.AlignVCenter, runtime.DESIGNS[self.design])
        p.setFont(QFont('Inter', 8)); p.setPen(QColor(colors['PlaceholderText']))
        text = p.fontMetrics().elidedText(runtime.designs.DESCRIPTIONS[self.design], Qt.TextElideMode.ElideRight, int(box.width()-245))
        p.drawText(QRectF(left, box.bottom()-23, box.width()-245, 18), Qt.AlignmentFlag.AlignVCenter, text)
        p.setPen(QColor(colors['Link'])); p.setFont(QFont('Inter', 9, QFont.Weight.DemiBold))
        p.drawText(QRectF(box.right()-185, box.bottom()-39, 165, 28), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   'Selected · Customize →' if self.isChecked() else 'Choose theme →')


class DesignPage(QWidget):
    def __init__(self, owner):
        super().__init__(); self.owner = owner; self.cards = {}
        outer = QVBoxLayout(self); outer.setContentsMargins(6, 10, 6, 0); outer.setSpacing(12)
        toolbar = QHBoxLayout(); title = QLabel('Find your next atmosphere'); title.setObjectName('section')
        toolbar.addWidget(title); toolbar.addStretch()
        self.count = QLabel(); self.count.setObjectName('muted'); toolbar.addWidget(self.count)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search themes, colors or mood…')
        self.search.setAccessibleName('Search theme presets'); self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240); self.search.setMaximumWidth(430); toolbar.addWidget(self.search, 1)
        outer.addLayout(toolbar)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAccessibleName('Theme preset gallery'); outer.addWidget(self.scroll, 1)
        body = QWidget(); self.scroll.setWidget(body)
        rows = QVBoxLayout(body); rows.setContentsMargins(0, 0, 10, 8); rows.setSpacing(18)
        catalog = wallpaper_sets.catalog(runtime.ROOT.parent/'wallpaper')
        for name in runtime.DESIGNS:
            card = DesignCard(name, catalog.get(name, []))
            card.clicked.connect(lambda _, value=name: owner.select_preset(value))
            self.cards[name] = card; rows.addWidget(card)
        self.empty = QLabel('No themes found. Try a name, color or mood.'); self.empty.setObjectName('muted')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty.setMinimumHeight(150)
        rows.addWidget(self.empty); rows.addStretch()
        self.search.textChanged.connect(self.filter); self.filter()

    def filter(self):
        words = self.search.text().casefold().split(); matches = 0
        for name, card in self.cards.items():
            haystack = ' '.join((name, runtime.DESIGNS[name], runtime.designs.DESCRIPTIONS[name], *STORIES.get(name, ()))).casefold()
            visible = all(word in haystack for word in words)
            card.setVisible(visible); matches += visible
        self.empty.setVisible(matches == 0)
        self.count.setText(f'{matches} of {len(self.cards)} themes' if words else f'{matches} themes')
        self.scroll.verticalScrollBar().setValue(0)

    def refresh(self):
        for name, card in self.cards.items():
            selected = name == self.owner.design.currentData()
            card.mode = self.owner.mode.currentData() if selected else runtime.designs.DEFAULT_MODES[name]
            card.setChecked(selected); card.update(); card.wallpapers.update()
