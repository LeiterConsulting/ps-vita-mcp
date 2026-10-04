"""Strict, bounded decoding of the allocation-free Vita RGB packet format."""
def decode_rle(data: bytes, size: int) -> bytes:
    if type(size) is not int or not 0 < size <= 480*272*3 or size % 3:
        raise ValueError('Invalid decoded frame length')
    if not data or len(data) > size + (size//3+127)//128:
        raise ValueError('Encoded frame exceeds its bound')
    out=bytearray(); index=0
    while index<len(data):
        tag=data[index]; index+=1
        count=tag+1 if tag<128 else tag-128+2
        take=3*count if tag<128 else 3
        if index+take>len(data) or len(out)+3*count>size:
            raise ValueError('Truncated or overflowing frame packet')
        packet=data[index:index+take]; index+=take
        out.extend(packet if tag<128 else packet*count)
    if len(out)!=size: raise ValueError('Decoded frame length differs')
    return bytes(out)
