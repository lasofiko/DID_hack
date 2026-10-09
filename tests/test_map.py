import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bootstrap
from did_agent.maps import load_map, read_pgm

class MapTests(unittest.TestCase):
    def test_official_map_path(self):
        p=load_map(bootstrap.ROOT/'configs/maps/map.yaml')
        self.assertAlmostEqual(p.resolution,.05)
        self.assertEqual((p.width,p.height),(384,384))
        start={'x':-2,'y':-.5}
        path=p.plan(start,{'x':-1.5,'y':-.5})
        self.assertTrue(all(p.free(p.cell(point)) for point in path))

    def test_pgm_binary_whitespace_pixel_and_row_flip(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/'map.pgm').write_bytes(b'P5\n#comment\n2 2\n255\n'+bytes([10,255,255,0]))
            self.assertEqual(read_pgm(root/'map.pgm')[3],[10,255,255,0])
            (root/'map.yaml').write_text('image: map.pgm\nresolution: 1\norigin: [0, 0, 0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
            p=load_map(root/'map.yaml',clearance=0)
            self.assertTrue(p.free((0,0)))
            self.assertFalse(p.free((1,0)))
            self.assertFalse(p.free((0,1)))
            self.assertTrue(p.free((1,1)))

    def test_truncated_pgm_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name)/'bad.pgm';p.write_bytes(b'P5\n2 2\n255\n\0')
            with self.assertRaises(ValueError):read_pgm(p)
