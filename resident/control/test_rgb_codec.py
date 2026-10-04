import unittest
from rgb_codec import decode_rle
class CodecTests(unittest.TestCase):
    def test_run_and_literal_vectors(self):
        self.assertEqual(decode_rle(bytes([128,1,2,3,0,4,5,6]),9),bytes([1,2,3,1,2,3,4,5,6]))
        self.assertEqual(decode_rle(bytes([255,1,2,3]),129*3),bytes([1,2,3])*129)
    def test_malformed_packets_and_output_bounds(self):
        for packet,size in [(b'',3),(bytes([128,1]),6),(bytes([127,1,2,3]),384),(bytes([255,1,2,3]),3),(bytes([0,1,2,3,0]),3),(bytes([0,1,2,3]),6),(bytes([0,1,2,3]),0),(bytes([0,1,2,3]),480*272*3+3)]:
            with self.assertRaises(ValueError):decode_rle(packet,size)
if __name__=='__main__':unittest.main(verbosity=2)
