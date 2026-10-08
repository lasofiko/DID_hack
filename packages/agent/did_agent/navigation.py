"""Occupancy grid, coordinate conversion and weighted 8-connected A*."""
from __future__ import annotations
import heapq
import math
from dataclasses import dataclass


def distance(a, b):
    return math.hypot(a['x'] - b['x'], a['y'] - b['y'])


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


@dataclass(frozen=True)
class CoordinateTransform:
    x: float = -2.0
    y: float = -0.5
    yaw: float = 0.0

    def apply(self, x, y, yaw=0.0):
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return {'x': self.x + c*x - s*y, 'y': self.y + s*x + c*y}, wrap(yaw + self.yaw)


class NavigationPlanner:
    def __init__(self, width, height, resolution, origin, occupied=(), costs=None, origin_yaw=0.0):
        if isinstance(width,bool) or isinstance(height,bool) or not isinstance(width,int) or not isinstance(height,int) or width <= 0 or height <= 0 or not math.isfinite(resolution) or resolution <= 0:
            raise ValueError('Invalid map dimensions')
        if not all(math.isfinite(v) for v in (origin['x'], origin['y'], origin_yaw)):
            raise ValueError('Invalid map origin')
        self.width, self.height, self.resolution = width, height, resolution
        self.origin, self.origin_yaw = dict(origin), origin_yaw
        self.occupied = set(occupied)
        self.costs = dict(costs or {})
        if any(not math.isfinite(v) or v < 1 for v in self.costs.values()):
            raise ValueError('Cell costs must be finite and >= 1')

    @classmethod
    def from_occupancy(cls, width, height, resolution, origin, data, clearance=0.20, origin_yaw=0.0):
        cls(width,height,resolution,origin,origin_yaw=origin_yaw)
        if not math.isfinite(clearance) or clearance < 0:
            raise ValueError('Invalid clearance')
        if len(data) != width*height:
            raise ValueError('Occupancy data length mismatch')
        blocked = {(i % width, i // width) for i, value in enumerate(data) if value < 0 or value >= 50}
        # Cell-square extent plus robot radius: conservative metric inflation.
        r = math.ceil(clearance / resolution)
        inflated = set(blocked)
        boundary = [(x,y) for x,y in blocked if any(
            0 <= x+dx < width and 0 <= y+dy < height and (x+dx,y+dy) not in blocked
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)))]
        for x, y in boundary:
            for dx in range(-r, r+1):
                for dy in range(-r, r+1):
                    if math.hypot(max(0, abs(dx)-0.5), max(0, abs(dy)-0.5))*resolution <= clearance:
                        inflated.add((x+dx, y+dy))
        # Also inflate the outside of the map: footprint cannot extend beyond it.
        for x in range(width):
            for y in range(height):
                if min(x+0.5, y+0.5, width-x-0.5, height-y-0.5)*resolution < clearance:
                    inflated.add((x, y))
        return cls(width, height, resolution, origin, inflated, origin_yaw=origin_yaw)

    def cell(self, point):
        x, y = point['x'], point['y']
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (x, y)):
            raise ValueError('Invalid point')
        x, y = x-self.origin['x'], y-self.origin['y']
        c, s = math.cos(self.origin_yaw), math.sin(self.origin_yaw)
        return math.floor((c*x+s*y)/self.resolution), math.floor((-s*x+c*y)/self.resolution)

    def point(self, cell):
        x, y = (cell[0]+0.5)*self.resolution, (cell[1]+0.5)*self.resolution
        c, s = math.cos(self.origin_yaw), math.sin(self.origin_yaw)
        return {'x': self.origin['x']+c*x-s*y, 'y': self.origin['y']+s*x+c*y}

    def free(self, cell):
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height and cell not in self.occupied

    def plan(self, start, target):
        source, goal = self.cell(start), self.cell(target)
        if not self.free(source) or not self.free(goal):
            raise ValueError('INVALID_TARGET: blocked or outside map')
        queue = [(0.0, source)]
        g, previous = {source: 0.0}, {}
        closed = set()
        while queue:
            _, current = heapq.heappop(queue)
            if current in closed:
                continue
            if current == goal:
                cells = [goal]
                while cells[-1] != source:
                    cells.append(previous[cells[-1]])
                cells.reverse()
                # Keep adjacent cell centres; no unsafe line-of-sight shortcut.
                return [dict(start)] + [self.point(c) for c in cells[1:]] + [dict(target)]
            closed.add(current)
            x, y = current
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                nxt = x+dx, y+dy
                if not self.free(nxt):
                    continue
                if dx and dy and (not self.free((x+dx, y)) or not self.free((x, y+dy))):
                    continue
                candidate = g[current] + math.hypot(dx,dy)*self.resolution*(self.costs.get(current,1)+self.costs.get(nxt,1))/2
                if candidate < g.get(nxt, math.inf):
                    g[nxt], previous[nxt] = candidate, current
                    h = math.hypot(nxt[0]-goal[0], nxt[1]-goal[1])*self.resolution
                    heapq.heappush(queue, (candidate+h, nxt))
        raise ValueError('No path')

    def segment_free(self, start, end):
        # Supercover: include orthogonal neighbours at diagonal cell crossings.
        count=max(1,math.ceil(distance(start,end)/(self.resolution*0.2)))
        previous=self.cell(start)
        if not self.free(previous):return False
        for i in range(1,count+1):
            fraction=i/count
            point={'x':start['x']+(end['x']-start['x'])*fraction,
                   'y':start['y']+(end['y']-start['y'])*fraction}
            cell=self.cell(point)
            if not self.free(cell):return False
            if cell[0]!=previous[0] and cell[1]!=previous[1]:
                if not self.free((cell[0],previous[1])) or not self.free((previous[0],cell[1])):
                    return False
            previous=cell
        return True

    def block_at(self, point, radius=0.15):
        x, y = self.cell(point)
        n = math.ceil(radius/self.resolution)
        for dx in range(-n,n+1):
            for dy in range(-n,n+1):
                if math.hypot(dx,dy)*self.resolution <= radius:
                    self.occupied.add((x+dx,y+dy))

    @staticmethod
    def length(path):
        return sum(distance(a,b) for a,b in zip(path,path[1:]))


class MotionController:
    def __init__(self, config):
        self.config = config

    def command(self, pose, yaw, target, tolerance=None):
        d = distance(pose, target)
        if not math.isfinite(d) or not math.isfinite(yaw):
            return 0.0, 0.0
        if d <= (self.config.goal_tolerance if tolerance is None else tolerance):
            return 0.0, 0.0
        error = wrap(math.atan2(target['y']-pose['y'], target['x']-pose['x']) - yaw)
        angular = max(-self.config.max_angular, min(self.config.max_angular, 2*error))
        linear = min(self.config.max_linear, 0.8*d)*max(0.0, math.cos(error)) if abs(error) < 0.35 else 0.0
        return linear, angular
