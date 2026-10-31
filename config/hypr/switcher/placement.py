"""Resolve the switcher's first frame before it is mapped by Wayland."""
RULE='fusion-task-switcher'


def prepare(monitor,width,height,ctl):
    width,height=int(width),int(height);number=int(monitor['id'])
    scale=max(.25,monitor.get('scale',1));w,h=monitor['width']/scale,monitor['height']/scale
    if monitor.get('transform',0)%2:w,h=h,w
    left,top,right,bottom=monitor.get('reserved') or [0,0,0,0]
    x=round(left+(w-left-right-width)/2);y=round(top+(h-top-bottom-height)/2)
    if number<0 or min(width,height)<1 or max(width,height)>32000:raise ValueError('Invalid switcher geometry')
    reply=ctl('--batch',';'.join(f'keyword windowrule[{RULE}]:{key} {value}' for key,value in
               [('monitor',number),('size',f'{width} {height}'),('move',f'{x} {y}')]))
    if any(line.strip()!='ok' for line in reply.splitlines() if line.strip()):
        raise ValueError('Could not position task switcher: '+reply)
    return x,y
