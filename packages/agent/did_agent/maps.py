"""Dependency-free reader for static ROS map YAML with P2/P5 grayscale PGM."""
import ast
from pathlib import Path
from .navigation import NavigationPlanner


def read_pgm(path):
    data=Path(path).read_bytes()
    cursor=0
    def token():
        nonlocal cursor
        while cursor < len(data):
            if data[cursor] in b' \t\r\n':cursor+=1
            elif data[cursor] == 35:
                end=data.find(b'\n',cursor)
                if end<0:raise ValueError('Truncated PGM comment')
                cursor=end+1
            else:break
        start=cursor
        while cursor<len(data) and data[cursor] not in b' \t\r\n#':cursor+=1
        if start==cursor:raise ValueError('Truncated PGM header')
        return data[start:cursor]
    magic=token()
    width,height,maximum=int(token()),int(token()),int(token())
    if width<=0 or height<=0 or not 0 < maximum <= 255 or magic not in (b'P2',b'P5'):
        raise ValueError('Unsupported PGM format')
    if magic==b'P5':
        if cursor>=len(data) or data[cursor] not in b' \t\r\n':raise ValueError('PGM header separator missing')
        if data[cursor:cursor+2]==b'\r\n':cursor+=2
        else:cursor+=1
        values=list(data[cursor:])
    else:
        values=[int(token()) for _ in range(width*height)]
    if len(values)!=width*height or any(v<0 or v>maximum for v in values):
        raise ValueError('PGM pixel count/range invalid')
    return width,height,maximum,values


def load_map(path, clearance=0.20):
    path=Path(path)
    # Only the documented static map fields; no generic YAML dependency/execution.
    options={}
    for line in path.read_text().splitlines():
        line=line.split('#',1)[0].strip()
        if line:
            key,value=line.split(':',1)
            options[key.strip()]=value.strip()
    resolution=float(options['resolution'])
    origin=ast.literal_eval(options['origin'])
    if len(origin)!=3:raise ValueError('Map origin must have three values')
    negate=int(options.get('negate','0'))
    occupied=float(options.get('occupied_thresh','.65'))
    free=float(options.get('free_thresh','.196'))
    if negate not in (0,1) or not 0<=free<occupied<=1:
        raise ValueError('Invalid map thresholds')
    image=path.parent/options['image'].strip('"\'')
    w,h,maximum,pixels=read_pgm(image)
    cells=[]
    for y in range(h-1,-1,-1):  # Images run top-to-bottom; ROS grid runs bottom-to-top.
        for value in pixels[y*w:(y+1)*w]:
            probability=value/maximum if negate else 1-value/maximum
            cells.append(100 if probability>occupied else 0 if probability<free else -1)
    return NavigationPlanner.from_occupancy(w,h,resolution,{'x':origin[0],'y':origin[1]},cells,clearance,origin[2])
