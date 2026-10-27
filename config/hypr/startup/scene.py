#!/usr/bin/env python3
"""Four terminal scenes; no shell profiles or global terminal configuration."""
import argparse
import colorsys
import datetime
import math
import os
from pathlib import Path
import random
import re
import select
import shutil
import signal
import subprocess
import sys
import termios
import time
import tty

from PIL import Image, ImageDraw
import numpy as np

ROOT = Path(__file__).resolve().parent
ESC = '\033['
RESET = ESC+'0m'
TEAL = (115, 218, 205)
MUTED = (106, 133, 163)
PALE = (199, 216, 239)
FONT = {
'0':['01110','11011','11011','11011','11011','11011','01110'],
'1':['00110','01110','00110','00110','00110','00110','11111'],
'2':['01110','11011','00011','00110','01100','11000','11111'],
'3':['11110','00011','00011','01110','00011','00011','11110'],
'4':['11011','11011','11011','11111','00011','00011','00011'],
'5':['11111','11000','11000','11110','00011','00011','11110'],
'6':['01111','11000','11000','11110','11011','11011','01110'],
'7':['11111','00011','00110','00110','01100','01100','01100'],
'8':['01110','11011','11011','01110','11011','11011','01110'],
'9':['01110','11011','11011','01111','00011','00011','11110'],
':':['000','011','011','000','011','011','000'],
'X':['10001','10001','01010','00100','01010','10001','10001'],
'E':['11111','10000','10000','11110','10000','10000','11111'],
'T':['11111','00100','00100','00100','00100','00100','00100'],
'A':['01110','10001','10001','11111','10001','10001','10001'],
'L':['10000','10000','10000','10000','10000','10000','11111'],
'N':['10001','11001','11001','10101','10011','10011','10001'],
'G':['01111','10000','10000','10111','10001','10001','01110'],
'I':['11111','00100','00100','00100','00100','00100','11111'],
' ':['000']*7,
}


def color(rgb):
    return ESC+'38;2;%d;%d;%dm'%tuple(int(v) for v in rgb)


def visible(text):
    return len(re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]', '', text))


def clip(text, width):
    tokens = re.findall(r'\x1b\[[0-9;?]*[a-zA-Z]|.', text)
    out, used = [], 0
    for token in tokens:
        if token.startswith('\x1b'):
            out.append(token)
        elif used < width:
            out.append(token); used += 1
        else:
            break
    return ''.join(out)+RESET


def centered(text, width):
    return ' '*max(0,(width-visible(text))//2)+clip(text,width)


def heading(title, cols, suffix=''):
    rule = '─'*max(0,cols-len(title)-len(suffix)-5)
    return color(TEAL)+' '+title+' '+color((48,70,96))+rule+color(MUTED)+' '+suffix+RESET


def blocks(text, scale=1, tick=0, solid=True):
    rows = [' '.join(FONT.get(ch,FONT[' '])[y] for ch in text) for y in range(7)]
    output=[]
    for y,row in enumerate(rows):
        line=''
        for x,ch in enumerate(row):
            hue=.47 + .17*(.5+.5*math.sin(tick*.75-x*.07+y*.17))
            rgb=tuple(int(c*255) for c in colorsys.hsv_to_rgb(hue,.38,.87))
            line+=color(rgb)+(('█' if solid else '▓')*scale if ch=='1' else ' '*scale)
        output.append(line+RESET)
    return output


def mascot(t, width, height):
    """Original animated cyber-cat character, rasterized into colored ASCII cells."""
    im=Image.new('RGB',(360,400))
    d=ImageDraw.Draw(im)
    bob=round(math.sin(t*1.7)*4)
    # HUD halo, orbiting pixels and stars.
    d.ellipse((37,35,323,321),outline=(30,64,86),width=2)
    for n in range(20):
        a=n*math.tau/20+t*.18
        x=180+146*math.cos(a);y=182+146*math.sin(a)
        d.rectangle((x,y,x+2,y+2),fill=(90,150,172))
    for n in range(12):
        x=20+(n*53)%320;y=40+(n*79+int(t*12))%315
        d.line((x-2,y,x+2,y),fill=(55,90,112));d.line((x,y-2,x,y+2),fill=(55,90,112))
    # Tail, long hair and ears.
    sway=round(math.sin(t*1.3)*13)
    d.arc((228+sway,224,334+sway,363),270,125,fill=(93,141,173),width=16)
    d.arc((233+sway,229,329+sway,358),270,125,fill=(29,44,64),width=8)
    d.polygon([(102,136+bob),(62,288),(100,272),(84,319),(130,294),(251,304),(277,320),(266,272),(296,289),(258,137+bob)],fill=(29,40,68),outline=(112,139,187),width=3)
    d.polygon([(95,123+bob),(91,39+bob),(144,78+bob)],fill=(39,58,87),outline=(164,191,222),width=4)
    d.polygon([(105,94+bob),(103,58+bob),(130,84+bob)],fill=(116,115,163))
    d.polygon([(215,78+bob),(271,38+bob),(267,123+bob)],fill=(39,58,87),outline=(164,191,222),width=4)
    d.polygon([(230,84+bob),(259,56+bob),(255,96+bob)],fill=(116,115,163))
    # Boots, jacket, gloves and scarf.
    d.rounded_rectangle((129,316+bob,172,374+bob),12,fill=(31,47,68),outline=(140,170,198),width=3)
    d.rounded_rectangle((190,316+bob,232,374+bob),12,fill=(31,47,68),outline=(140,170,198),width=3)
    d.line((132,359+bob,168,359+bob),fill=(102,210,204),width=5)
    d.line((194,359+bob,229,359+bob),fill=(102,210,204),width=5)
    d.polygon([(133,224+bob),(102,265+bob),(107,313+bob),(139,299+bob),(128,334+bob),(232,334+bob),(221,299+bob),(253,313+bob),(258,263+bob),(227,224+bob)],fill=(38,54,81),outline=(144,174,209),width=3)
    d.line((140,260+bob,141,322+bob),fill=(79,116,151),width=3)
    d.line((218,260+bob,220,322+bob),fill=(79,116,151),width=3)
    d.line((158,272+bob,201,306+bob),fill=(112,231,212),width=6)
    d.line((201,272+bob,158,306+bob),fill=(112,231,212),width=6)
    d.polygon([(210,225+bob),(251+sway,227+bob),(280+sway,253+bob),(247,252+bob),(214,240+bob)],fill=(56,142,152),outline=(139,230,213))
    # Face and headphones.
    d.ellipse((93,77+bob,268,238+bob),fill=(83,102,128),outline=(181,201,222),width=3)
    d.rounded_rectangle((85,133+bob,105,200+bob),8,fill=(33,53,76),outline=(118,218,214),width=3)
    d.rounded_rectangle((257,133+bob,277,200+bob),8,fill=(33,53,76),outline=(118,218,214),width=3)
    d.ellipse((110,110+bob,251,231+bob),fill=(157,177,189),outline=(188,204,217),width=2)
    # Swept hair, thick anime eyes, a blink every six seconds.
    d.polygon([(99,133+bob),(110,88+bob),(153,70+bob),(216,76+bob),(256,111+bob),(264,164+bob),(235,141+bob),(231,169+bob),(204,133+bob),(193,151+bob),(164,116+bob),(158,147+bob),(140,128+bob),(114,160+bob)],fill=(51,68,101),outline=(179,191,222),width=3)
    if t%5.8 < .18:
        for x in [131,207]:d.arc((x-13,163+bob,x+15,185+bob),0,180,fill=(22,35,54),width=4)
    else:
        for x in [140,219]:
            d.ellipse((x-14,161+bob,x+13,197+bob),fill=(18,34,49))
            d.ellipse((x-10,167+bob,x+9,194+bob),fill=(74,201,196))
            d.ellipse((x-5,169+bob,x+3,190+bob),fill=(24,53,78))
            d.ellipse((x-8,165+bob,x-2,174+bob),fill=(235,249,246))
            d.line((x-15,163+bob,x+12,160+bob),fill=(22,33,53),width=4)
    d.line((119,200+bob,132,202+bob),fill=(179,120,156),width=3)
    d.line((225,202+bob,239,200+bob),fill=(179,120,156),width=3)
    d.arc((169,201+bob,190,217+bob),10,170,fill=(45,60,82),width=2)
    d.polygon([(128,224+bob),(179,236+bob),(232,222+bob),(226,242+bob),(180,253+bob),(137,243+bob)],fill=(44,135,148),outline=(151,224,221),width=3)
    grid=np.asarray(im.resize((width,height),Image.Resampling.LANCZOS))
    alphabet=' .,:;=+*#%@'
    output=[]
    for row in grid:
        line='';previous=None
        for pixel in row:
            brightness=int(max(pixel))
            if brightness<14:
                line+=' ';continue
            rgb=tuple((int(x)//24)*24+12 for x in pixel)
            if rgb!=previous:line+=color(rgb);previous=rgb
            line+=alphabet[min(len(alphabet)-1,brightness*len(alphabet)//256)]
        output.append(line+RESET)
    return output


class Scene:
    def __init__(self,mode):
        self.mode=mode;self.start=time.monotonic();self.last_fetch=-100;self.fetch=[]
        self.rng=random.Random(29);self.drops=[];self.dimensions=None
        self.last_visibility=0;self.is_visible=True

    def shown(self):
        if time.monotonic()-self.last_visibility>2:
            self.last_visibility=time.monotonic()
            try:
                import json
                monitors=json.loads(subprocess.check_output(['hyprctl','-j','monitors'],timeout=1,stderr=subprocess.DEVNULL))
                self.is_visible=any(m.get('specialWorkspace',{}).get('name')=='special:xetal-startup' for m in monitors)
            except Exception:self.is_visible=True
        return self.is_visible

    def frame(self,cols,rows,t=None):
        t=time.monotonic()-self.start if t is None else t
        if self.mode=='hero':
            lines=[heading('04 / XETAL ENGINE',cols,'ONLINE'),'']
            scale=2 if cols>=132 else 1
            lines += [centered(s,cols) for s in blocks('XETAL ENGINE',scale,t,False)]
            lines += ['',centered(color(MUTED)+'C R E A T E   /   B U I L D   /   E X P L O R E'+RESET,cols)]
            h=max(8,rows-len(lines)-4);w=min(cols-4,round(h*1.8))
            lines += [centered(s,cols) for s in mascot(t,w,h)]
            lines += [centered(color(TEAL)+'X E T A L   /   S Y S T E M   C O M P A N I O N'+RESET,cols),
                      centered(color(MUTED)+'Super + D  hide dashboard   ·   Super + Space  apps'+RESET,cols)]
            return lines
        if self.mode=='clock':
            now=datetime.datetime.now()
            scale=2 if cols>=57 else 1
            lines=[heading('03 / LOCAL TIME',cols,now.strftime('%Z'))]
            lines += ['']*max(1,(rows-14)//2)
            lines += [centered(s,cols) for s in blocks(now.strftime('%H:%M'),scale,t)]
            lines += ['',centered(color(PALE)+now.strftime('%A  /  %d %B %Y').upper()+RESET,cols)]
            width=min(cols-6,50);filled=round(now.second/60*width)
            lines += [centered(color(TEAL)+'━'*filled+color((41,62,83))+'─'*(width-filled)+RESET,cols)]
            lines += [centered(color(MUTED)+now.astimezone().tzname()+f'  ·  {now.second:02d}s'+RESET,cols)]
            return lines
        if self.mode=='info':
            if t-self.last_fetch>30 or not self.fetch:
                self.last_fetch=t
                try:
                    proc=subprocess.run(['fastfetch','--config',str(ROOT/'fastfetch.jsonc'),'--pipe','false'],text=True,capture_output=True,timeout=5)
                    self.fetch=(proc.stdout if proc.returncode==0 else proc.stderr).splitlines()
                except Exception as exc:self.fetch=[str(exc)]
            lines=[heading('01 / SYSTEM',cols,'XETAL'),'']
            lines+=['']*max(0,(rows-len(self.fetch)-5)//2)
            lines += [clip(s,cols-2) for s in self.fetch]
            lines += ['',color(MUTED)+'  Hyprland  ·  '+datetime.datetime.now().strftime('%a %d %b')+RESET]
            return lines
        height=max(1,rows-3)
        if self.dimensions!=(cols,height):
            self.dimensions=(cols,height)
            self.drops=[(self.rng.uniform(-height,height),self.rng.uniform(3,8),self.rng.randint(5,15)) for _ in range(cols)]
        lines=[heading('02 / THE CONSTRUCT',cols,'LIVE'),'']
        for y in range(height):
            line=''
            for x,(offset,speed,trail) in enumerate(self.drops):
                head=(offset+t*speed)%(height+trail)
                distance=int(head)-y
                if 0<=distance<trail and x%2==0:
                    intensity=1-distance/trail
                    rgb=(186,246,221) if distance==0 else (38+40*intensity,65+133*intensity,63+83*intensity)
                    char='0123456789abcdef:+/|<>[]'[(x*31+y*17+int(t*4+x))%23]
                    line+=color(rgb)+char
                else:line+=' '
            lines.append(line+RESET)
        return lines


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['info','matrix','clock','hero'])
    parser.add_argument('--frame',action='store_true')
    args=parser.parse_args()
    scene=Scene(args.mode)
    if args.frame:
        cols,rows=shutil.get_terminal_size((120,52))
        print('\n'.join(scene.frame(cols,rows,2)))
        return
    old=termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    for sig in [signal.SIGTERM,signal.SIGHUP,signal.SIGINT]:signal.signal(sig,stop)
    sys.stdout.write(ESC+'?1049h'+ESC+'?25l'+ESC+'?7l')
    try:
        while not stopped:
            start=time.monotonic()
            if select.select([sys.stdin],[],[],0)[0]:
                key=os.read(sys.stdin.fileno(),32)
                if key in (b'\x1b',b'q',b'Q'):
                    subprocess.run(['hyprctl','dispatch','togglespecialworkspace','xetal-startup'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if scene.shown():
                cols,rows=shutil.get_terminal_size()
                lines=scene.frame(cols,rows)
                frame=ESC+'H'+''.join(clip(line,cols-1)+ESC+'K'+('\r\n' if n<rows-1 else '') for n,line in enumerate((lines+['']*rows)[:rows]))
                sys.stdout.write(frame);sys.stdout.flush()
            interval=.1 if args.mode in ('hero','matrix') and scene.is_visible else .5
            time.sleep(max(.01,interval-(time.monotonic()-start)))
    except (BrokenPipeError,OSError):pass
    finally:
        try:
            sys.stdout.write(RESET+ESC+'?7h'+ESC+'?25h'+ESC+'?1049l');sys.stdout.flush()
            termios.tcsetattr(sys.stdin,termios.TCSADRAIN,old)
        except (OSError,termios.error):pass


if __name__=='__main__':main()
