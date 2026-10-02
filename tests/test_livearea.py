import io
from pathlib import Path
import struct
import sys
import unittest
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from livearea_png import validate_livearea_png

def png(mode="P",size=(128,128),**options):
    image=Image.new(mode,size)
    if mode=="P":
        image.putpalette([n for n in range(256) for _ in range(3)])
    out=io.BytesIO()
    image.save(out,format="PNG",bits=8,**options)
    return out.getvalue()

class LiveAreaTests(unittest.TestCase):
    def test_accepts_opaque_indexed(self):
        self.assertEqual(validate_livearea_png(png(),(128,128))["colorType"],3)

    def test_rejects_original_rgba_even_when_opaque(self):
        image=Image.new("RGBA",(128,128),(13,24,39,255))
        out=io.BytesIO(); image.save(out,format="PNG")
        with self.assertRaisesRegex(ValueError,"indexed"):
            validate_livearea_png(out.getvalue(),(128,128))

    def test_rejects_wrong_dimensions(self):
        with self.assertRaisesRegex(ValueError,"dimensions"):
            validate_livearea_png(png(size=(64,64)),(128,128))

    def test_rejects_transparency_in_our_profile(self):
        with self.assertRaisesRegex(ValueError,"opaque"):
            validate_livearea_png(png(transparency=0),(128,128))

    def test_rejects_corruption(self):
        data=bytearray(png()); data[29]^=1
        with self.assertRaisesRegex(ValueError,"CRC"):
            validate_livearea_png(bytes(data),(128,128))

    def test_rejects_truncation(self):
        with self.assertRaises(ValueError):
            validate_livearea_png(png()[:-3],(128,128))

if __name__=="__main__":
    unittest.main(verbosity=2)
