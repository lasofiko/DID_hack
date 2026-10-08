"""Static ROS packaging validation only; no claim of colcon/runtime verification."""
import ast
from pathlib import Path
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
package=root/'ros2/did_robot'
manifest=ET.parse(package/'package.xml').getroot()
assert manifest.findtext('name')=='did_robot'
assert manifest.findtext('export/build_type')=='ament_python'
for path in [package/'setup.py',* (package/'did_robot').glob('*.py'),* (package/'launch').glob('*.py')]:
    ast.parse(path.read_text(),filename=str(path))
assert (package/'resource/did_robot').is_file()
assert (package/'setup.cfg').is_file()
for name in ('map.yaml','map.pgm','LICENSE'):
    assert (root/'configs/maps'/name).is_file()
print('ROS source syntax/manifest/resource/config/map: OK (not colcon or ROS runtime)')
