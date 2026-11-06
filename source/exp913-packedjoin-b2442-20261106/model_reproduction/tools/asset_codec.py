"""Standard-library-only access to the locally installed libzstd C ABI."""
import ctypes
from ctypes.util import find_library

_lib=ctypes.CDLL(find_library('zstd') or 'libzstd.so.1')
_lib.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
_lib.ZSTD_decompress.restype=ctypes.c_size_t
_lib.ZSTD_isError.argtypes=[ctypes.c_size_t]
_lib.ZSTD_isError.restype=ctypes.c_uint
_lib.ZSTD_getFrameContentSize.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
_lib.ZSTD_getFrameContentSize.restype=ctypes.c_ulonglong

def decode(frame,limit=1_000_000):
    src=ctypes.create_string_buffer(frame,len(frame))
    n=_lib.ZSTD_getFrameContentSize(src,len(frame))
    if n >limit:raise ValueError(f'frame decompression size invalid/exceeds maximum: {n}')
    dst=ctypes.create_string_buffer(n)
    got=_lib.ZSTD_decompress(dst,n,src,len(frame))
    if _lib.ZSTD_isError(got) or got!=n:raise ValueError('zstd decompression error')
    return dst.raw[:got]
