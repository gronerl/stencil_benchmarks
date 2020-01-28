import ctypes
from typing import Any, Callable, Dict, Optional, Tuple, Union

import numpy as np

from .alloc import l1_dcache_assoc, l1_dcache_linesize, l1_dcache_size, malloc

_offset: int = l1_dcache_linesize()


def alloc_array(shape: Tuple[int, ...],
                dtype: Union[str, np.dtype],
                layout: Tuple[int, ...],
                alignment: int = 0,
                index_to_align: Optional[Tuple[int, ...]] = None,
                alloc: Optional[Callable[[int], Any]] = None,
                apply_offset: bool = False) -> np.ndarray:
    """Allocate aligned and padded numpy array.

    Parameters
    ----------
    shape : tuple of int
        Shape of the array.
    dtype : numpy.dtype
        Data type of the array.
    layout : tuple of int
        Layout map. Tuple of ints from `0` to `ndim - 1`, defines the size of
        the strides. The dimension with value `ndim - 1` will have unit stride,
        the dimension with value `0` will have the largest stride.
    alignment : int
        Alignment in bytes.
    index_to_align : tuple of int
        Index of the element that should be aligned (default: first element in
        the array).
    alloc : func
        Memory allocation function accepting a single argument, the size of the
        allocation in bytes. Has to return an object supporting Python’s buffer
        protocol (default: allocation with `malloc`).
    apply_offset : bool
        Apply an offset (multiple of alignment) to reduce chance of cache
        conflicts.
    max_offset : int
        Maximum offset to apply. Default is 2KB, half of the normal page size.

    Returns
    -------
    numpy.ndarray
        A numpy.ndarray instance, with memory allocated using `alloc`. Element
        with index `index_to_align` is aligned to `alignment` bytes. Padding is
        applied, such that all but the smallest strides are divisible by
        `alignment` bytes. Memory is unitialized

    Examples
    --------
    Allocating an int32 array with column-major layout:
    >>> x = alloc_array((2, 3), dtype='int32', layout=(1, 0))
    >>> x[:, :] = 0
    >>> x
    array([[0, 0, 0],
           [0, 0, 0]], dtype=int32)
    >>> x.strides
    (4, 8)

    Using layout specification to use row-major layout:
    >>> x = alloc_array((2, 3), dtype='int32', layout=(0, 1))
    >>> x.strides
    (12, 4)

    Use alignment (and thus padding) for an array:
    >>> x = alloc_array((2, 3), dtype='int32', layout=(0, 1), alignment=64)
    >>> x.strides
    (64, 4)

    First element of array should be aligned:
    >>> x.ctypes.data % 64
    0
    """
    shape = tuple(shape)
    ndim = len(shape)
    dtype = np.dtype(dtype)
    layout = tuple(layout)
    alignment = int(alignment)
    index_to_align = (0, ) * ndim if index_to_align is None else index_to_align
    alloc = malloc if alloc is None else alloc

    if tuple(sorted(layout)) != tuple(range(ndim)):
        raise ValueError('invalid layout specification')
    if alignment < 0:
        raise ValueError('alignment must be non-negative')
    if not ndim == len(shape) == len(layout) == len(index_to_align):
        raise ValueError('dimension mismatch')

    strides = [0 for _ in range(ndim)]

    strides_product = dtype.itemsize
    for layout_value in range(ndim - 1, -1, -1):
        dimension = layout.index(layout_value)
        strides[dimension] = strides_product
        strides_product *= shape[dimension]
        if layout_value == ndim - 1 and alignment:
            strides_product = (strides_product + alignment -
                               1) // alignment * alignment

    global _offset
    buffer = alloc(strides_product + alignment + _offset)
    if alignment:
        pointer_to_align = ctypes.addressof(
            ctypes.c_char.from_buffer(buffer)) + np.sum(
                np.array(strides) * np.array(index_to_align))
        aligned_pointer = (pointer_to_align + alignment -
                           1) // alignment * alignment
        offset = aligned_pointer - pointer_to_align
    else:
        offset = 0
    if apply_offset:
        offset += _offset
        _offset *= 2
        if _offset >= l1_dcache_size() / max(l1_dcache_assoc(), 1):
            _offset = l1_dcache_linesize()
    return np.ndarray(shape=shape,
                      dtype=dtype,
                      buffer=buffer,
                      offset=offset,
                      strides=strides)


def nbytes(data: np.ndarray) -> int:
    """Return number of data bytes stored in an array buffer.

    In contrast to data.nbytes, this includes padded data and is thus useable
    to determine the number of bytes that need to be copied when using a linear
    1D copy function (e.g. memcpy).

    Parameters
    ----------
    data : numpy.ndarray
        Numpy array.

    Returns
    -------
    int
        Number of bytes in the array buffer, including possible padding. Equals
        the number of bytes that have to be copied with a 1D copy operation.

    Examples
    --------
    >>> nbytes(np.zeros((2, 3), dtype='int32'))
    24
    >>> nbytes(alloc_array((2, 3), dtype='int32', layout=(0, 1)))
    24
    >>> nbytes(alloc_array((2, 3), dtype='int32', layout=(0, 1), alignment=64))
    76
    """
    last_index = np.sum((np.array(data.shape) - 1) * np.array(data.strides))
    return int(last_index + data.itemsize)
