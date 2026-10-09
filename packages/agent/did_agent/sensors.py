"""ROS-independent decoding; invalid forward lidar is unknown space."""
import math


def quaternion_yaw(x,y,z,w):
    if not all(math.isfinite(v) for v in (x,y,z,w)):
        return math.nan
    norm = math.sqrt(x*x+y*y+z*z+w*w)
    if norm < 1e-9 or abs(norm-1) > 0.05:
        return math.nan
    x,y,z,w = x/norm,y/norm,z/norm,w/norm
    return math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))


def scan_distances(ranges, angle_min, angle_increment, range_min, range_max):
    if not all(math.isfinite(v) for v in (angle_min,angle_increment,range_min,range_max)) or angle_increment == 0 or not 0 <= range_min < range_max:
        return math.nan, math.nan
    front, valid_ranges = [], []
    for i,value in enumerate(ranges):
        angle=math.atan2(math.sin(angle_min+i*angle_increment),math.cos(angle_min+i*angle_increment))
        valid = (math.isfinite(value) and range_min <= value <= range_max) or value == math.inf
        if valid:
            valid_ranges.append(value)
            if abs(angle) < 0.50:
                front.append(value)
        else:
            return math.nan,math.nan  # Unknown side/rear beams also make rotation unsafe.
    if not front or not valid_ranges:
        return math.nan,math.nan
    return min(front), min(valid_ranges)
