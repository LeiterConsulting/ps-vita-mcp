"""Validate this project's conservative LiveArea PNG profile, not all Vita formats."""
import io
import struct
import zlib
from PIL import Image

def validate_livearea_png(data, expected_size):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Not a PNG")
    if len(data) < 33:
        raise ValueError("Truncated PNG")
    chunks = []
    offset = 8
    while offset < len(data):
        if offset+12 > len(data):
            raise ValueError("Truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset+4:offset+8]
        end = offset+12+length
        if end > len(data):
            raise ValueError("PNG chunk overruns file")
        payload = data[offset+8:offset+8+length]
        crc = struct.unpack_from(">I", data, offset+8+length)[0]
        if zlib.crc32(kind+payload)&0xffffffff != crc:
            raise ValueError("PNG chunk CRC mismatch")
        chunks.append((kind,payload))
        offset = end
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13 or chunks[-1][0] != b"IEND":
        raise ValueError("Missing/invalid PNG headers")
    width,height,depth,color,compression,filter_mode,interlace = struct.unpack(">IIBBBBB",chunks[0][1])
    if (width,height) != expected_size:
        raise ValueError("Incorrect LiveArea dimensions")
    if depth != 8 or color != 3:
        raise ValueError("LiveArea assets must use our 8-bit indexed PNG profile; RGBA was rejected by the console")
    if (compression,filter_mode,interlace) != (0,0,0):
        raise ValueError("Unexpected PNG encoding")
    kinds = [kind for kind,payload in chunks]
    if kinds.count(b"IHDR") != 1 or kinds.count(b"PLTE") != 1 or b"IDAT" not in kinds:
        raise ValueError("Invalid indexed PNG chunks")
    palette = dict(chunks)[b"PLTE"]
    if len(palette) != 768:
        raise ValueError("Expected a 256-entry RGB palette")
    if kinds.index(b"PLTE") > kinds.index(b"IDAT") or b"tRNS" in kinds:
        raise ValueError("This project's LiveArea assets must be opaque indexed PNGs")
    with Image.open(io.BytesIO(data)) as image:
        if image.mode != "P" or "transparency" in image.info:
            raise ValueError("Unexpected palette or transparency")
        image.verify()
    return {"size":[width,height],"bitDepth":depth,"colorType":color,"paletteEntries":256,"transparency":False}
