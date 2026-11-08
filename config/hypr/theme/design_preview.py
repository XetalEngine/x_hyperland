"""Small desktop illustrations using the selected palette and personal artwork."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from identity import avatar_path, wallpaper_path,launcher_background_path
import runtime
import wallpaper_sets
from launcher_surfaces import DEFAULTS, paint_group, paint_tile


class DesktopPreview:
    def __init__(self):
        self.paths=None
        self.visibility=runtime.launcher_background_visibility();self.labels=runtime.launcher_labels()
        self.theme_wallpapers={design:QPixmap(str(paths[1 if design in ('porcelainink','obsidianforge','candycloud','shadowedge','hollowgrove', 'gildedhollow') and len(paths)>1 else 0])) for design,paths in wallpaper_sets.catalog(runtime.ROOT.parent/'wallpaper').items()}
        self.icons=[QIcon.fromTheme(name).pixmap(48,48) for name in (
            'system-file-manager','internet-web-browser','utilities-terminal',
            'applications-multimedia','preferences-system','accessories-calculator')]
        self.refresh()

    def refresh(self,avatar=None,background=None,enabled=None):
        self.show_background=runtime.launcher_wallpaper() if enabled is None else enabled
        self.custom_background=bool(runtime.launcher_background() if background is None else background)
        paths=(wallpaper_path(),avatar_path(avatar),launcher_background_path(choice=background))
        if paths==self.paths:return
        self.paths=paths
        self.wallpaper,self.avatar,self.background=[QPixmap(str(path)) if path else QPixmap() for path in paths]

    @staticmethod
    def picture(p,image,box,rounding=0,circle=False):
        if image.isNull():return
        clip=QPainterPath()
        if circle:clip.addEllipse(box)
        else:clip.addRoundedRect(box,rounding,rounding)
        p.save();p.setClipPath(clip,Qt.ClipOperation.IntersectClip)
        scale=max(box.width()/image.width(),box.height()/image.height())
        target=QRectF(0,0,image.width()*scale,image.height()*scale);target.moveCenter(box.center())
        p.drawPixmap(target,image,QRectF(image.rect()));p.restore()

    def paint(self,p,box,design,mode,surfaces=None,group_image=None,launcher_design=None):
        modern=design=='modern';colors=runtime.colors(mode,design)
        launcher_design=launcher_design or design
        surfaces=surfaces or DEFAULTS[launcher_design]
        p.save();clip=QPainterPath();radius=3 if design=='shadowedge' else 18 if design=='candycloud' else 3 if design=='obsidianforge' else 2 if design=='porcelainink' else 10
        clip.addRoundedRect(box,radius,radius);p.setClipPath(clip)
        p.translate(box.topLeft());p.scale(box.width()/720,box.height()/240)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        def panel(x,y,w,h,fill='Window',radius=0,border=None):
            p.setPen(QPen(QColor(colors[border]),1) if border else Qt.PenStyle.NoPen)
            p.setBrush(QColor(colors.get(fill,fill)));p.drawRoundedRect(QRectF(x,y,w,h),radius,radius)

        def text(x,y,w,h,value,size=11,color='Text',bold=False):
            p.setFont(QFont(runtime.ui_font(design),size,QFont.Weight.DemiBold if bold else QFont.Weight.Normal))
            p.setPen(QColor(colors.get(color,color)));p.drawText(QRectF(x,y,w,h),Qt.AlignmentFlag.AlignVCenter,value)

        panel(0,0,720,240,'Base')
        wallpaper=self.theme_wallpapers.get(design,self.wallpaper)
        if wallpaper.isNull():wallpaper=self.wallpaper
        self.picture(p,wallpaper,QRectF(0,0,720,240))
        p.fillRect(QRectF(0,0,720,240),QColor(8,17,28,0 if design in ('porcelainink','obsidianforge','candycloud','shadowedge','hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow') else 15 if design=='tidalglass' else 80))
        panel(0,0,720,23)
        panel(5,3,55,17,'Highlight',5 if modern else 2)
        text(13,2,45,18,'Apps',8,'HighlightedText',True)
        text(74,2,190,18,'1   2   +      Keys',8)
        text(575,2,140,18,'♪   ◉   100%    21:10',7)
        if design=='atomicafterglow':
            from atomicafterglow import paint_surface
            paint_surface(p,QRectF(4,1,712,23),colors,5,100,True)
            text(18,2,260,20,'⚛   ATOMIC AFTERGLOW    |    Apps',8,'Link')
            for i in range(5):
                panel(313+i*24,4,20,17,'Highlight' if i==1 else 'Base',3,'Accent' if i==1 else 'Midlight')
                text(320+i*24,4,12,17,str(i+1),7,'HighlightedText' if i==1 else 'Text')
            text(575,2,140,20,'♪   ◉   100%    21:10',7,'Link')
        if design=='blackwood':
            from blackwood import paint_surface
            paint_surface(p,QRectF(4,1,712,23),colors,5,100,True)
            text(18,2,250,20,'HF   BLACKWOOD    |    Apps',8,'Link')
            for i in range(5):
                panel(313+i*24,4,20,17,'Highlight' if i==1 else 'Base',4,'Accent' if i==1 else 'Midlight')
                text(320+i*24,4,12,17,str(i+1),7,'HighlightedText' if i==1 else 'Text')
            text(575,2,140,20,'♪   ◉   100%    21:10',7,'Link')

        if design=='midnighttransit':
            from midnighttransit import paint_surface
            paint_surface(p,QRectF(4,1,712,23),colors,7,100,True)
            text(18,2,250,20,'HF   MIDNIGHT TRANSIT    |    Apps',8,'Link')
            for i in range(5):
                panel(313+i*24,4,20,17,'Highlight' if i==1 else 'Base',4,'Accent' if i==1 else 'Midlight')
                text(320+i*24,4,12,17,str(i+1),7,'HighlightedText' if i==1 else 'Text')
            text(575,2,140,20,'♪   ◉   100%    21:10',7,'Link')

        if design=='hyperfusionblue':
            from hyperfusionblue import paint_surface
            paint_surface(p,QRectF(4,1,712,23),colors,11,100,True)
            text(18,2,250,20,'HF   HYPERFUSION BLUE    |    Apps',8,'Link')
            for i in range(5):
                panel(313+i*24,4,20,17,'Highlight' if i==1 else 'Base',4,'Accent' if i==1 else 'Midlight')
                text(320+i*24,4,12,17,str(i+1),7,'Link')
            text(575,2,140,20,'♪   ◉   100%    21:10',7,'Link')

        if design=='gildedhollow':
            from gildedhollow import paint_surface
            paint_surface(p,QRectF(4,1,712,23),colors,11,100,True)
            text(18,2,250,20,'⚒   XETAL FUSION    |    Apps',8,'Link')
            for i in range(5):
                panel(313+i*24,4,20,17,'Highlight' if i==1 else 'Base',4,'Accent' if i==1 else 'Midlight')
                text(320+i*24,4,12,17,str(i+1),7,'Link')
            text(575,2,140,20,'♪   ◉   100%    21:10',7,'Link')

        # Launcher: profile, navigation, group title and real application icons.
        modern=launcher_design in ('modern','tidalglass','porcelainink','obsidianforge','candycloud','shadowedge','hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow');colors=runtime.colors(mode,launcher_design)
        radius=3 if launcher_design=='shadowedge' else 20 if launcher_design=='candycloud' else 3 if launcher_design=='obsidianforge' else 2 if launcher_design=='porcelainink' else 4 if launcher_design=='binaryknife' else 12 if launcher_design=='breakpoint' else 13 if modern else 5
        panel(14,37,389,190,'Window',radius,'Midlight')
        if launcher_design=='tidalglass':
            from tidalglass import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors,16,94)
        elif launcher_design=='porcelainink':
            from porcelainink import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        elif launcher_design=='atomicafterglow':
            from atomicafterglow import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        elif launcher_design=='blackwood':
            from blackwood import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        elif launcher_design=='midnighttransit':
            from midnighttransit import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        elif launcher_design=='hyperfusionblue':
            from hyperfusionblue import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        elif launcher_design=='gildedhollow':
            from gildedhollow import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        elif launcher_design=='hollowgrove':
            from hollowgrove import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        elif launcher_design=='shadowedge':
            from shadowedge import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        elif launcher_design=='candycloud':
            from candycloud import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors,20)
        elif launcher_design=='obsidianforge':
            from obsidianforge import paint_surface
            paint_surface(p,QRectF(14,37,389,190),colors)
        background=self.background if self.custom_background else wallpaper
        if self.show_background and not background.isNull():
            menu=QRectF(14,37,389,190)
            self.picture(p,background,menu,radius)
            shade=QColor(colors['Window']);shade.setAlpha(round(255*(1-self.visibility/100)))
            p.setPen(QPen(QColor(colors['Midlight']),1));p.setBrush(shade);p.drawRoundedRect(menu,radius,radius)
        self.picture(p,self.avatar,QRectF(27,49,32,32),circle=True)
        text(66,49,98,17,'xetal' if modern else 'XETAL',10,'Text',True)
        text(66,65,100,14,runtime.DESIGNS[launcher_design],7,'PlaceholderText')
        paint_group(p,QRectF(24,92,100,118),colors,launcher_design,surfaces['sidebar_opacity'])
        for row,title in enumerate(('Favorites','All apps','Development','Media','Files')):
            y=94+row*23
            if row==0:panel(24,y,96,20,'Highlight',6 if modern else 2)
            text(32,y,95,20,title,8,'HighlightedText' if row==0 else 'Text')
        text(137,45,200,22,'Favorites',11,'Text',True)
        panel(137,75,251,22,'Base',8 if modern else 3,'Midlight')
        text(146,75,240,22,'Search apps, tools, and favorites…',7,'PlaceholderText')
        paint_group(p,QRectF(137,105,251,19),colors,launcher_design,surfaces['group_opacity'],group_image)
        text(143,105,240,19,'Xetal Engine                                      ⋯',8,'Text',True)
        for i,icon in enumerate(self.icons):
            x=139+(i%3)*84;y=131+(i//3)*43
            paint_tile(p,QRectF(x,y,79,39),colors,launcher_design,mode,surfaces['tile_opacity'],radius=9 if modern else 3)
            if not icon.isNull():p.drawPixmap(QRectF(x+29,y+(4 if self.labels['names'] else 9),21,21),icon,QRectF(icon.rect()))
            if self.labels['names']:text(x+6,y+25,72,12,('Files','Browser','Terminal','Music','Settings','Calculator')[i],6)

        # The Fusion Settings changes from Raw tabs to the Modern navigation rail.
        modern=design=='modern';colors=runtime.colors(mode,design)
        panel(420,52,284,166,'Window',13 if modern else 5,'Midlight')
        if design in ('tidalglass','porcelainink','obsidianforge','candycloud','shadowedge','hollowgrove', 'gildedhollow','hyperfusionblue','midnighttransit','blackwood','atomicafterglow'):
            if design=='atomicafterglow':
                from atomicafterglow import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            elif design=='blackwood':
                from blackwood import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            elif design=='midnighttransit':
                from midnighttransit import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            elif design=='hyperfusionblue':
                from hyperfusionblue import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            elif design=='gildedhollow':
                from gildedhollow import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            elif design=='hollowgrove':
                from hollowgrove import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            elif design=='shadowedge':
                from shadowedge import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            elif design=='candycloud':
                from candycloud import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors,20)
            elif design=='obsidianforge':
                from obsidianforge import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            elif design=='porcelainink':
                from porcelainink import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors)
            else:
                from tidalglass import paint_surface
                paint_surface(p,QRectF(420,52,284,166),colors,16,97)
            text(433,58,245,20,runtime.DESIGNS[design]+'  /  Fusion Settings',9,'Text',True)
            panel(429,84,76,122,'Button',3 if design=='obsidianforge' else 0 if design=='porcelainink' else 10)
            for row,title in enumerate(('Appearance','Workspaces','Windows','Audio','System')):
                y=88+row*22
                if row==0:
                    panel(433,y,68,20,'Highlight',3 if design=='obsidianforge' else 0 if design=='porcelainink' else 7)
                    if design=='porcelainink':panel(433,y,2,20,'Accent')
                text(439,y,65,20,title,6,'HighlightedText' if row==0 else 'Text')
            text(517,86,173,22,'Audio',13,'Text',True)
            text(517,110,173,16,'Quiet power. A brighter idea.' if design=='atomicafterglow' else 'A light on the coast.' if design=='blackwood' else 'The last train. The first idea.' if design=='midnighttransit' else 'Power in plain sight.' if design=='hyperfusionblue' else 'Quiet stone. Living gold.' if design=='gildedhollow' else 'A quieter kind of magic.' if design=='hollowgrove' else 'Move in silence.' if design=='shadowedge' else 'Softer worlds. Higher focus.' if design=='candycloud' else 'Forged in the dark.' if design=='obsidianforge' else 'A quieter desktop.' if design=='porcelainink' else 'A little calm. A little clarity.',6,'PlaceholderText')
            for i,caption in enumerate(('Speakers','Microphone')):
                y=135+i*34;text(518,y,164,15,caption,7)
                panel(518,y+19,160,4,'Midlight',2);panel(518,y+19,108-i*24,4,'Accent',2)
                panel(620-i*24,y+15,12,12,'Base',6,'Accent')
        elif modern:
            panel(429,61,27,147,'AlternateBase',10)
            for row,icon in enumerate(self.icons[:5]):
                if row==0:panel(433,66,19,19,'Highlight',6)
                if not icon.isNull():p.drawPixmap(QRectF(436,69+row*27,13,13),icon,QRectF(icon.rect()))
            text(466,62,205,25,'Home',12,'Text',True)
            self.picture(p,self.wallpaper,QRectF(466,94,225,49),8)
            p.fillRect(QRectF(466,94,225,49),QColor(14,27,41,95))
            self.picture(p,self.avatar,QRectF(477,102,31,31),circle=True)
            text(517,99,165,19,'xetal',10,'#edf6ff',True)
            text(517,117,165,17,'Your desktop. Your space.',7,'#d7e6f6')
            panel(466,150,108,54,'AlternateBase',9)
            text(477,152,96,23,'21:10',14,'Accent',True)
            text(477,177,96,18,'Tuesday, October 27',6,'PlaceholderText')
            for i,icon in enumerate(self.icons[1:5]):
                x=583+i%2*57;y=150+i//2*29
                panel(x,y,51,25,'Button',8)
                if not icon.isNull():p.drawPixmap(QRectF(x+18,y+5,15,15),icon,QRectF(icon.rect()))
        else:
            text(432,61,246,12,'XETAL  /  SESSION TOOLS',6,'Accent')
            text(432,75,246,23,'Fusion Settings',12,'Text',True)
            panel(432,105,260,22,'Button')
            text(438,105,250,22,'Hotkeys   Audio   Displays   Theme',7)
            text(438,133,250,19,'Audio mixer',9,'Text',True)
            for i,label in enumerate(('Output','Microphone')):
                y=157+i*25;text(438,y,70,18,label,7,'PlaceholderText')
                panel(516,y+7,165,4,'Midlight');panel(516,y+7,110+i*24,4,'Accent')
                panel(622+i*24,y+3,7,12,'Accent',2)
        p.restore()
