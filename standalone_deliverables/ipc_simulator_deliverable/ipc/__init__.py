"""
ipc/
-----
Zero-copy IPC bus: mmap-backed ring buffer + binary wire protocol for
passing Orders between processes without JSON, Pickle, or Python dicts
touching shared memory.
"""

from .protocol import pack_order, unpack_order, SLOT_SIZE, FORMAT
from .shared_memory import SharedRingMemory
from .ring_buffer import RingBuffer

__all__ = [
    "RingBuffer", "SharedRingMemory",
    "pack_order", "unpack_order", "SLOT_SIZE", "FORMAT",
]
