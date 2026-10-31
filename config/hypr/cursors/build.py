#!/usr/bin/env python3
"""Compile original SVG shapes to Hyprcursor and XCursor, entirely in this profile."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import fcntl

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import art


def build(root=ROOT):
    cache=root/'.build';cache.mkdir(parents=True,exist_ok=True)
    fingerprint=hashlib.sha256((ROOT/'art.py').read_bytes()+(ROOT/'build.py').read_bytes()).hexdigest()
    with (cache/'build.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (cache/'version').exists() and (cache/'version').read_text()==fingerprint:return cache/'data'
        from PyQt6.QtCore import QByteArray, QRectF
        from PyQt6.QtGui import QImage,QPainter
        from PyQt6.QtSvg import QSvgRenderer
        # QSvgRenderer works without a display; no live session is touched here.
        with tempfile.TemporaryDirectory(dir=cache) as temp:
            tmp=Path(temp);icons=tmp/'data/icons';icons.mkdir(parents=True)
            for style in art.STYLES:
                name='Xetal-Cursor-'+style;source=tmp/name;source.mkdir()
                (source/'manifest.hl').write_text(f'name = {name}\ndescription = Xetal original cursor collection\nversion = 1\ncursors_directory = hyprcursors\n')
                target=icons/name;target.mkdir();(target/'cursors').mkdir()
                (target/'index.theme').write_text(f'[Icon Theme]\nName={art.STYLES[style][0]}\nInherits=Adwaita\n')
                for shape,aliases in art.ALIASES.items():
                    folder=source/'hyprcursors'/shape;folder.mkdir(parents=True)
                    drawing,hot=art.svg(style,shape)
                    meta=f'resize_algorithm = bilinear\nhotspot_x = {hot[0]/36}\nhotspot_y = {hot[1]/36}\n'
                    meta+=''.join('define_override = '+a+'\n' for a in aliases)
                    entries=[]
                    for frame in range(12 if shape in ('watch','left_ptr_watch') else 1):
                        drawing,_=art.svg(style,shape,frame);filename=f'frame{frame}.svg';(folder/filename).write_text(drawing)
                        meta+=f'define_size = 36, {filename}, 80\n'
                        renderer=QSvgRenderer(QByteArray(drawing.encode()))
                        for size in (24,32,48,64,96):
                            image=QImage(size,size,QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
                            painter=QPainter(image);renderer.render(painter,QRectF(0,0,size,size));painter.end()
                            png=folder/f'{size}-{frame}.png';image.save(str(png))
                            entries.append(f'{size} {round(hot[0]*size/36)} {round(hot[1]*size/36)} {png} 80')
                    (folder/'meta.hl').write_text(meta)
                    config=folder/'xcursor.conf';config.write_text('\n'.join(entries)+'\n')
                    subprocess.run(['xcursorgen',str(config),str(target/'cursors'/shape)],check=True,capture_output=True)
                    for alias in aliases:(target/'cursors'/alias).symlink_to(shape)
                subprocess.run(['hyprcursor-util','--create',str(source),'--output',str(tmp)],check=True,capture_output=True)
                compiled=tmp/('theme_'+name)
                if not compiled.exists():raise RuntimeError('Cursor compiler did not produce '+str(compiled))
                for item in compiled.iterdir():
                    if item.is_dir():shutil.copytree(item,target/item.name)
                    else:shutil.copy2(item,target/item.name)
            old=cache/'previous';shutil.rmtree(old,ignore_errors=True)
            if (cache/'data').exists():os.replace(cache/'data',old)
            os.replace(tmp/'data',cache/'data');shutil.rmtree(old,ignore_errors=True)
            (cache/'version').write_text(fingerprint)
    return cache/'data'

if __name__=='__main__':
    # Fonts used in a few auxiliary shapes require a GUI application, offscreen.
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PyQt6.QtGui import QGuiApplication
    app=QGuiApplication([])
    print(build())
