"""Searchable preset banners with an independent, accessible wallpaper reveal."""
import importlib
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QEasingCurve, QPoint, QPointF, QRectF, QSize, QSizeF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QAbstractButton, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                            QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

import runtime
import wallpaper_sets
import gallery_state
from wallpaper.hidden import HideButton, HiddenDock, ThumbnailFlight
from wallpaper.tabs import TabNameDialog, DeleteTabDialog


# Presentation only: selecting a banner still uses the normal component chooser.
STORIES = {
    'integra': ('INTEGRA\nIVORY MIDNIGHT', 'The road feels like home.\nPearl. Lilac. Sakura.', 'integra acura honda type r dc2 db8 ivory midnight pearl lilac rose amber japan cherry blossom garage tuning car'),
    'hp4': ('BMW S1000RR\nHP4', 'Built for the dark.\nCarbon. Cobalt. Precision.', 'bmw s1000rr s1000 rr hp4 2012 motorcycle carbon cobalt blue wheelie racing midnight'),
    'killerinstinct': ('KILLER INSTINCT\nARCADE 94', 'One more credit.\nChrome. Violet. Ember.', 'killer instinct 1994 midway rare arcade spinal fulgore tj combo eyedol cabinet violet silver'), 'kitemple': ('KILLER INSTINCT\nJADE TEMPLE', 'Awaken the tiger.\nJade. Gold. Sapphire.', 'killer instinct 1994 orchid jago chief thunder temple jade emerald gold'), 'kiprimal': ('KILLER INSTINCT\nPRIMAL STORM', 'Unleash the instinct.\nStorm. Stone. Claw.', 'killer instinct 1994 sabrewulf riptor eyedol jungle primal storm violet moss'), 'kifireice': ('KILLER INSTINCT\nFIRE & ICE', 'Opposing forces.\nFire. Frost. Steel.', 'killer instinct 1994 cinder glacius tj combo fire ice foundry arctic cyan orange'), 'starcraft': ('STARCRAFT II', 'Command the frontier.\nSteel. Plasma. Starlight.', 'starcraft star craft ii 2 terran protoss zerg marine zealot battlecruiser aiur nexus blue cyan armor space'), 'mortalkombat2': ('MORTAL\nKOMBAT II', 'Choose your destiny.\nJade. Gold. Ice. Fire.', 'mortal kombat 2 ii mk2 arcade living forest scorpion sub zero shang tsung fatality fatalities dragon jade gold'), 'facadasexu': ('777\nFACADAS EXU', 'Candlelight in the dark.\nBlack. Oxblood. Ivory. Copper.', '777 facadas exu black red oxblood ivory copper candles trident altar'),
    'ghostbusters': ('GHOSTBUSTERS', 'A little slime.\nA lot of spirit.', 'ghostbusters ghost busters slimer geleia ecto slime green neon cartoon firehouse'),
    'amazon': ('AMAZON', 'Where the forest meets the moon.\nEmerald. Gold. Coral.', 'amazon rainforest jungle emerald green gold coral moon river tropical nature'),
    'leviathan': ('LEVIATHAN', 'Beyond the labyrinth.\nObsidian. Brass. Amethyst.', 'leviathan labyrinth puzzle cube gothic hellraiser cenobite pinhead obsidian brass gold violet purple storm'),
    'polaris': ('POLARIS', 'A familiar friend. A brighter horizon.\nMidnight. Cyan. Starlight.', 'polaris tux linux penguin navy cyan blue violet aurora north star orbit glass'),
    'prisonbreak': ('PRISON\nBREAK', 'Break out of the ordinary.\nGraphite. Violet. Amber.', 'prison break comic arcade industrial steel purple violet neon orange amber hazard stripes cell block escape'), 'infernalencore': ('INFERNAL\nENCORE', 'One last riff. All the fire.\nGraphite. Brass. Crimson.', 'infernal encore heavy metal gothic concert guitar fire red crimson brass skull purple'),
    'midnightrun': ('MIDNIGHT RUN', 'After hours. In full color.\nGraphite. Cyan. Magenta.', 'midnight run tokyo japan neon cyan magenta pink graphite car sports sedan sakura rain city night audi a4 2014 slammed stance rs6 avant wagon bay mountain'),
    'mystery98': ('MYSTERY 98', 'Every window holds a story.\nWalnut. Emerald. Antique gold.', 'windows 98 mystery victorian manor library walnut emerald gold brass classic retro parchment detective beveled'), 'platform95': ('PLATFORM 95', 'A familiar desktop. A golden departure.\nIvory. Espresso. Antique gold.', 'platform 95 classic retro windows beige ivory brown espresso gold brass railway train station beveled'),
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
FOCAL_TOP = {'integra': .72, 'modern': .05, 'shadowedge': .08, 'killerinstinct': 0.65, 'kitemple': 0.65, 'kiprimal': 0.65, 'kifireice': 0.65, 'starcraft': 0.62, 'mortalkombat2': .70}
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
    radius = {'killerinstinct': 3, 'kitemple': 2, 'kiprimal': 8, 'kifireice': 2, 'starcraft': 5, 'mortalkombat2': 4, 'facadasexu': 8, 'ghostbusters': 10, 'integra': 8, 'hp4': 6, 'amazon': 8, 'leviathan': 6, 'polaris': 12, 'prisonbreak': 5, 'infernalencore': 5, 'midnightrun': 7, 'mystery98': 1, 'platform95': 1, 'mycelium': 14, 'atomicafterglow': 5, 'blackwood': 5, 'midnighttransit': 7, 'hyperfusionblue': 9, 'candycloud': 26, 'porcelainink': 2, 'obsidianforge': 3, 'binaryknife': 3,
              'breakpoint': 8, 'tidalglass': 20}.get(design, 16)
    path.addRoundedRect(box, radius, radius)
    return path


class WallpaperReveal(QAbstractButton):
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
        if self.card.compact:
            pill=QRectF(self.width()-178,self.height()-30,174,28)
            p.setBrush(QColor(colors['Window']));p.setPen(QPen(QColor(colors['Accent']),1));p.drawRoundedRect(pill,7,7)
            p.setFont(QFont('Inter',9,QFont.Weight.DemiBold));p.setPen(QColor(colors['Text']))
            p.drawText(pill,Qt.AlignmentFlag.AlignCenter,f'{len(self.card.paths)} wallpapers   ↗')
        else:
            title, story, _ = STORIES.get(self.card.design, (runtime.DESIGNS[self.card.design], runtime.designs.DESCRIPTIONS[self.card.design], ''))
            serif = self.card.design in ('porcelainink','blackwood','mortalkombat2')
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
            p.fillPath(shape(QRectF(self.rect()),self.card.design),QColor(colors['Base']))
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


class DesignCard(QAbstractButton):
    hideRequested = pyqtSignal(str)
    def __init__(self, design, paths, parent=None):
        super().__init__(parent)
        self.design = design; self.mode = 'dark'; self.paths = paths; self.hero = None
        self.compact = True
        self.setCheckable(True); self.setFixedHeight(304); self.setMinimumWidth(320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(runtime.DESIGNS[design])
        self.setAccessibleDescription(runtime.designs.DESCRIPTIONS[design]+'. Select to choose which components to apply.')
        self.wallpapers = WallpaperReveal(self)
        self.hide_button=HideButton(self);self.hide_button.setAccessibleName('Hide '+runtime.DESIGNS[design]+' preset')
        self.hide_button.setToolTip('Move this preset into the selected hidden tab. Your current theme stays selected.')
        self.hide_button.clicked.connect(lambda:self.hideRequested.emit(design))

    def sizeHint(self): return QSize(470, 304)

    def position_wallpapers(self):
        self.compact=self.width()<740
        self.hide_button.move(self.width()-94,self.height()-43)
        if self.compact:
            amount=self.wallpapers.amount
            start=QRectF(self.width()-194,216,180,30);end=QRectF(14,16,self.width()-28,232)
            rect=QRectF(*(a+(b-a)*amount for a,b in zip(start.getRect(),end.getRect())))
            self.wallpapers.setGeometry(rect.toAlignedRect());self.hide_button.raise_();return
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
        if self.design in ('shadowedge', 'candycloud', 'obsidianforge', 'porcelainink', 'tidalglass', 'hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow','mycelium','platform95','mystery98','midnightrun','infernalencore','prisonbreak','polaris','leviathan','hp4','integra','amazon','ghostbusters', 'killerinstinct', 'kitemple', 'kiprimal', 'kifireice', 'starcraft', 'mortalkombat2', 'facadasexu'):
            importlib.import_module(self.design).paint_surface(p, box, colors, focused=self.isChecked())
        else:
            shade = QLinearGradient(box.topLeft(), box.bottomRight())
            shade.setColorAt(0, QColor(colors['AlternateBase'])); shade.setColorAt(1, QColor(colors['Window']))
            p.fillPath(shape(box, self.design), shade)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(colors['Accent'] if self.isChecked() or self.hasFocus() else colors['Midlight']), 2 if self.isChecked() or self.hasFocus() else 1))
        p.drawPath(shape(box, self.design))
        scene = box.adjusted(12, 12, -12, -54)
        art = scene if self.compact else QRectF(scene.left(), scene.top(), self.wallpapers.x()-scene.left()+50, scene.height())
        if self.hero is None:
            index = min(1, len(self.paths)-1) if self.design not in ('tidalglass','hyperfusionblue','midnighttransit','blackwood','atomicafterglow','mycelium','platform95','mystery98','midnightrun','infernalencore','prisonbreak','polaris','leviathan','hp4','integra','amazon','ghostbusters', 'killerinstinct', 'kitemple', 'kiprimal', 'kifireice', 'starcraft', 'mortalkombat2', 'facadasexu') else 0
            self.hero = picture(self.paths[index], 1440) if self.paths else QPixmap()
        p.save(); p.setClipPath(shape(scene, self.design))
        p.fillRect(scene, QColor(colors['Base'])); cover(p, self.hero, art, FOCAL_TOP.get(self.design, .35))
        fade = QLinearGradient(art.right()-min(220, art.width()*.35), 0, art.right(), 0)
        transparent = QColor(colors['Base']); transparent.setAlpha(0)
        fade.setColorAt(0, transparent); fade.setColorAt(1, QColor(colors['Base'])); p.fillRect(art, fade) if not self.compact else None
        p.restore()
        # A small theme-specific signature keeps the artwork dominant.
        p.setPen(QPen(QColor(colors['Accent']), 2))
        if self.design in ('shadowedge', 'binaryknife', 'breakpoint'):
            p.drawLine(QPointF(box.left()+18, box.bottom()-13), QPointF(box.left()+39, box.bottom()-35))
        else:
            p.drawLine(QPointF(box.left()+18, box.bottom()-24), QPointF(box.left()+37, box.bottom()-24))
        left = box.left()+49
        p.setFont(QFont('Inter', 11, QFont.Weight.DemiBold)); p.setPen(QColor(colors['Text']))
        title=p.fontMetrics().elidedText(runtime.DESIGNS[self.design],Qt.TextElideMode.ElideRight,int(box.width()-160))
        p.drawText(QRectF(left, box.bottom()-45, box.width()-160, 23), Qt.AlignmentFlag.AlignVCenter, title)
        p.setFont(QFont('Inter', 8)); p.setPen(QColor(colors['PlaceholderText']))
        text = p.fontMetrics().elidedText(runtime.designs.DESCRIPTIONS[self.design], Qt.TextElideMode.ElideRight, int(box.width()-160))
        p.drawText(QRectF(left, box.bottom()-23, box.width()-160, 18), Qt.AlignmentFlag.AlignVCenter, text)



@dataclass(frozen=True)
class ThemeThumbnail:
    path: str
    title: str


class DesignPage(QWidget):
    def __init__(self, owner):
        super().__init__(); self.owner=owner;self.cards={};self.columns=0;self.visible_names=[];self.flight=None;self.dialog=None
        error=''
        try:self.options=gallery_state.read()
        except (OSError,ValueError) as problem:self.options=gallery_state.normalize(gallery_state.DEFAULTS);error=str(problem)
        outer=QVBoxLayout(self);outer.setContentsMargins(6,10,6,0);outer.setSpacing(10)
        toolbar=QHBoxLayout();title=QLabel('Find your next atmosphere');title.setObjectName('section');toolbar.addWidget(title);toolbar.addStretch()
        self.count=QLabel();self.count.setObjectName('muted');toolbar.addWidget(self.count)
        self.search=QLineEdit();self.search.setPlaceholderText('Search themes, colors or mood…');self.search.setAccessibleName('Search theme presets');self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(180);self.search.setMaximumWidth(430);toolbar.addWidget(self.search,1);outer.addLayout(toolbar)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.scroll.setAccessibleName('Theme preset gallery');outer.addWidget(self.scroll,1)
        body=QWidget();self.scroll.setWidget(body);self.rows=QGridLayout(body);self.rows.setContentsMargins(0,0,10,8);self.rows.setSpacing(18)
        self.scroll.viewport().installEventFilter(self)
        catalog=wallpaper_sets.catalog(runtime.ROOT.parent/'wallpaper')
        for name in runtime.DESIGNS:
            card=DesignCard(name,catalog.get(name,[]),body);card.clicked.connect(lambda _,value=name:owner.select_preset(value));card.hideRequested.connect(self.hide_preset)
            self.cards[name]=card
        self.empty=QLabel('No visible themes found. Try another search or restore a theme from a tab below.');self.empty.setWordWrap(True);self.empty.setObjectName('muted')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);self.empty.setMinimumHeight(150)
        self.hidden_dock=HiddenDock(self,item_label='themes',show_titles=True,collapsible=True)
        self.hidden_dock.collapseRequested.connect(self.collapse_dock)
        self.hidden_dock.restored.connect(lambda item:self.restore_preset(item.path))
        self.hidden_dock.tabChosen.connect(self.switch_tab);self.hidden_dock.tabAdded.connect(self.create_tab)
        self.hidden_dock.tabRenamed.connect(self.rename_tab);self.hidden_dock.tabDeleted.connect(self.delete_tab);self.hidden_dock.moved.connect(self.move_preset)
        outer.addWidget(self.hidden_dock)
        self.status=QLabel(error);self.status.setWordWrap(True);self.status.setObjectName('muted');self.status.setVisible(bool(error));outer.addWidget(self.status)
        self.search.textChanged.connect(lambda:self.filter());self.refresh_dock();self.filter()

    def message(self,text):self.status.setText(text);self.status.setVisible(bool(text))

    def eventFilter(self,watched,event):
        if watched is self.scroll.viewport() and event.type()==QEvent.Type.Resize:
            QTimer.singleShot(0,self.reflow)
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):
        self.hidden_dock.fit(event.size().height());super().resizeEvent(event)

    def reflow(self,force=False):
        columns=2 if self.scroll.viewport().width()>=800 else 1
        if columns==self.columns and not force:return
        previous=self.scroll.verticalScrollBar().value();self.columns=columns
        while self.rows.count():self.rows.takeAt(0)
        for row in range(self.rows.rowCount()):self.rows.setRowStretch(row,0)
        for column in (0,1):self.rows.setColumnStretch(column,1 if column<columns else 0)
        for index,name in enumerate(self.visible_names):self.rows.addWidget(self.cards[name],index//columns,index%columns)
        self.rows.addWidget(self.empty,0,0,1,columns);self.empty.setVisible(not self.visible_names)
        self.rows.setRowStretch((len(self.visible_names)+columns-1)//columns+1,1)
        self.rows.activate();self.scroll.verticalScrollBar().setValue(previous)

    def filter(self,reset=True):
        words=self.search.text().casefold().split();hidden=set(self.options['hidden']);self.visible_names=[]
        for name,card in self.cards.items():
            haystack=' '.join((name,runtime.DESIGNS[name],runtime.designs.DESCRIPTIONS[name],*STORIES.get(name,()))).casefold()
            visible=name not in hidden and all(word in haystack for word in words)
            card.setVisible(visible)
            if visible:self.visible_names.append(name)
        matches=len(self.visible_names);total=len(self.cards)-len(hidden.intersection(self.cards))
        self.count.setText((f'{matches} of {total} themes' if words else f'{matches} themes')+(f' · {len(hidden)} hidden' if hidden else ''))
        self.reflow(True)
        if reset:self.scroll.verticalScrollBar().setValue(0)

    def refresh_dock(self,animate=False,reveal=''):
        self.hidden_dock.set_collapsed(self.options['hidden_dock_collapsed'])
        self.hidden_dock.set_tabs(self.options['hidden_tabs'],self.options['active_hidden_tab'])
        items=[]
        for name in gallery_state.hidden_tab(self.options)['paths']:
            title=runtime.DESIGNS.get(name,name);items.append(ThemeThumbnail(name,title));card=self.cards.get(name)
            if name not in self.hidden_dock.thumbnails.cache:
                pixmap=picture(card.paths[0],280) if card and card.paths else QPixmap(160,90)
                if not card or not card.paths:pixmap.fill(QColor(runtime.colors()['Base']))
                self.hidden_dock.thumbnails.cache[name]=pixmap
        self.hidden_dock.populate(items,animate=animate,reveal=reveal)

    def commit(self,value):
        try:self.options=gallery_state.save(value,self.options)
        except (OSError,ValueError) as error:self.message(str(error));return False
        self.message('');return True

    def collapse_dock(self,collapsed):
        self.stop_flight()
        if self.commit({**self.options,'hidden_dock_collapsed':collapsed}):
            self.hidden_dock.set_collapsed(collapsed,animate=True)

    def switch_tab(self,identity):
        if identity==self.options['active_hidden_tab']:return
        self.stop_flight()
        if self.commit({**self.options,'active_hidden_tab':identity}):self.refresh_dock(True)
        else:self.hidden_dock.set_tabs(self.options['hidden_tabs'],self.options['active_hidden_tab'])

    def tab_dialog(self,dialog):
        self.stop_flight();self.dialog=dialog
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted:
                self.options=dialog.options;self.refresh_dock(True);self.filter(False);self.message('')
        finally:self.dialog=None;dialog.deleteLater()

    def create_tab(self):self.tab_dialog(TabNameDialog(self.options,self,model=gallery_state))
    def rename_tab(self,identity):self.tab_dialog(TabNameDialog(self.options,self,identity,model=gallery_state))
    def delete_tab(self,identity):
        if len(self.options['hidden_tabs'])>1:self.tab_dialog(DeleteTabDialog(self.options,identity,self,model=gallery_state,item_label='themes'))

    def move_preset(self,name,destination):
        try:value=gallery_state.move_hidden_picture(self.options,name,destination)
        except ValueError as error:self.message(str(error));return
        self.stop_flight()
        if self.commit(value):self.refresh_dock(True,reveal=name)

    def stop_flight(self):
        if self.flight:
            self.flight.animation.stop();self.flight.hide();self.flight.deleteLater();self.flight=None
        self.hidden_dock.omitted.clear();self.hidden_dock.update()

    def fly(self,pixmap,source,destination,name):
        if pixmap.isNull() or self.hidden_dock.reduced_motion:return
        self.hidden_dock.omitted.add(name)
        self.flight=ThumbnailFlight(self,pixmap,source,destination)
        self.flight.finished.connect(self.stop_flight);self.flight.start()

    def dock_rect(self,name):
        return self.hidden_dock.location(name).translated(QPointF(self.hidden_dock.mapTo(self,QPoint())))

    def card_rect(self,name):
        card=self.cards[name]
        return QRectF(QPointF(card.mapTo(self,QPoint(14,14))),QSizeF(card.width()-28,card.height()-68))

    def hide_preset(self,name):
        if name in self.options['hidden']:return
        self.stop_flight();source=self.card_rect(name);card=self.cards[name]
        pixmap=picture(card.paths[0],720) if card.paths else QPixmap()
        if not self.commit({**self.options,'hidden':[*self.options['hidden'],name]}):return
        self.filter(False);self.refresh_dock(True,reveal=name)
        self.fly(pixmap,source,lambda:self.dock_rect(name),name)

    def restore_preset(self,name):
        if name not in self.options['hidden']:return
        self.stop_flight();source=self.dock_rect(name);pixmap=self.hidden_dock.thumbnails.cache.get(name,QPixmap())
        if not self.commit({**self.options,'hidden':[item for item in self.options['hidden'] if item!=name]}):return
        self.search.clear();self.filter(False);self.refresh_dock(True)
        if name in self.cards:
            self.rows.activate();self.scroll.ensureWidgetVisible(self.cards[name],0,12)
            self.fly(pixmap,source,lambda:self.card_rect(name),name)

    def hideEvent(self,event):
        self.stop_flight();self.hidden_dock.stop();super().hideEvent(event)

    def refresh(self):
        try:
            saved=gallery_state.read()
            if saved!=self.options:self.stop_flight();self.options=saved;self.refresh_dock();self.filter(False)
        except (OSError,ValueError) as error:self.message(str(error))
        for name,card in self.cards.items():
            selected=name==self.owner.design.currentData();card.mode=self.owner.mode.currentData() if selected else runtime.designs.DEFAULT_MODES[name]
            card.setChecked(selected);card.update();card.wallpapers.update()
