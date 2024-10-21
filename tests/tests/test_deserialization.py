import pytest
import pytest_benchmark
import struct
import rawutil
from animal_tag.serializer.utils import import_external_header
from animal_tag.serializer.deserializer import FileParser

def test_simple_parser():
    test_bytes = b'\x01\x02'
    parsing = 'bb'
    vals = struct.unpack(parsing, test_bytes)
    assert vals == (1, 2)

def test_simple_parser_padded():
    test_bytes = b'\x01\x02'
    parsing = 'bx'
    vals = struct.unpack(parsing, test_bytes)
    assert vals == (1, )

def test_simple_serialize():
    vals = struct.pack("<BB", 1, 2)
    assert vals == b'\x01\x02'

def test_simple_serialize_padded():
    vals = struct.pack("<Bx", 1)
    assert vals == b'\x01\x00'

def struct_unpack(parsing, test_bytes):
    vals = struct.unpack(parsing, test_bytes)
    return vals

def rawutils_unpack(parsing, test_bytes):
    vals = rawutil.unpack(parsing, test_bytes)
    return vals

def test_simple_struct_benchmark(benchmark):    # given the benchmark results, we really want to use struct over rawutils.
    parsing = "<"+2048*"H"
    orig_vals = [1995 for _ in range(2048)]
    test_bytes = struct.pack(parsing, *orig_vals)
    vals = benchmark(struct_unpack, parsing, test_bytes)
    assert list(vals) == orig_vals

def test_simple_rawutils_benchmark(benchmark):
    parsing = "<"+2048*"H"
    orig_vals = [1995 for _ in range(2048)]
    test_bytes = struct.pack(parsing, *orig_vals)
    vals = benchmark(rawutils_unpack, parsing, test_bytes)
    assert vals == orig_vals

def test_external_header():
    file_path = "/home/gabriel/Documents/mtag-deserializinator-inator/tests/src/animal_tag/serializer/test_header.txt"
    header = import_external_header(file_path)

    assert len(header.keys()) == 2