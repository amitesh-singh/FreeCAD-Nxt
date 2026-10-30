"""The process's OpenGL library, on Linux, Windows or macOS.

Only OpenGL 1.1 entry points are used, which every platform's system
library exports directly: no extension loading needed.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import sys
from typing import Any

#: Where each platform keeps its OpenGL, in the order to try.
_CANDIDATES = {
    "win32": ("opengl32",),
    "darwin": ("/System/Library/Frameworks/OpenGL.framework/OpenGL",),
}
_LINUX = ("libOpenGL.so.0", "libGL.so.1")

_library: Any = None


def _names() -> list[str]:
    names = list(_CANDIDATES.get(sys.platform, _LINUX))
    found = ctypes.util.find_library("opengl32" if sys.platform == "win32"
                                     else "OpenGL" if sys.platform == "darwin"
                                     else "GL")
    if found and found not in names:
        names.append(found)
    return names


def library() -> Any:
    """OpenGL's entry points, loaded once; OSError if there is none."""
    global _library
    if _library is None:
        # Windows' opengl32 uses the stdcall convention (it matters on
        # 32-bit Python only); everything else is cdecl.
        loader = getattr(ctypes, "WinDLL", ctypes.CDLL) \
            if sys.platform == "win32" else ctypes.CDLL
        for name in _names():
            with contextlib.suppress(OSError):
                _library = loader(name)
                break
        else:
            raise OSError("no OpenGL library found")
    return _library
