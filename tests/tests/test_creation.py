import pytest
from pathlib import Path
from animal_tag.serializer.buffer_generator import DataBuffer
from animal_tag.serializer.deserializer import FileReader, FileParser
import itertools

ID        = [1]
HEADER    = ["BTX"]
DATA      = ["H", "HB"]
SIZE      = [10, 8192]
VAL       = [2]
TIME      = [4093]
CH_SP     = [True, False]
NUM_BUFF  = [1, 2, 3, 4]
METADATA  = [{"name": "Gabriel", "species": "Homo sapiens", "date": "1995-10-26 14:15:00"}]
BUFF_NAME = ["test"]

def get_buffer_combinations():
    """For the given global variables, give all possible permutations of the inputs

    Please do be careful with these inputs, make sure that all of these combinations are possible and valid,
    so that buffer size is equal to or greater than the sum of the header size and the data format.

    Yields:
        dict: test inputs for pytest, with the path to file and the buffer writer that originally created it.
              do note that parameter order does in fact matter here, so do not change the order without updating
              how these parameters are passed DataBuffer in write_bin_file().
    """
    for  file_num, (id, header, data, size, val, time, ch_sp,
         num_buff, metadata, buff_name) in enumerate(itertools.product(ID, HEADER, DATA, SIZE, VAL, TIME, CH_SP,
                                                                       NUM_BUFF, METADATA, BUFF_NAME)):
        filename = "TestFile{}.bin".format(file_num)
        ch_names = ["ch{}".format(i) for i in range(len(data))]
        yield {"filename": filename, "params": (id, time, header, data, size, val,
                                                ch_sp, num_buff, metadata, buff_name, ch_names)}

@pytest.fixture(scope="session", params=list(get_buffer_combinations()))
def write_bin_file(request, tmp_path_factory):
    tmp_folder = tmp_path_factory.mktemp("SingleBuffer")
    bin_file   = tmp_folder / (request.param["filename"])

    buffer = DataBuffer(bin_file, *request.param["params"])
    buffer.write_file()
    return {"file": Path(bin_file), "buffer": buffer}

def test_bin_file_size(write_bin_file):
    fr = FileReader(write_bin_file["file"])
    fr.open_file()
    header = fr.readline()
    file_size = fr.size

    buffer = write_bin_file["buffer"]

    assert (file_size - len(header)) == buffer.num_buffers*buffer.buffer_size

def test_bin_file_header_parsing(write_bin_file):
    fp = FileParser(write_bin_file["file"], 'Test.h5') 
    fp.open_file()
    fp.read_file_header()

    assert fp.header == write_bin_file["buffer"].header_dict
