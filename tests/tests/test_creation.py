import pytest
from pathlib import Path

import itertools
import h5py
import numpy as np

from animal_tag.serializer.buffer_generator import DataBuffer
from animal_tag.serializer.deserializer import FileReader, FileParser
from animal_tag.serializer.utils import get_packet_size, count_data_channels, import_external_header

ID        = [1]
HEADER    = ["BTx"]
DATA      = ["H", "HB", "TH"]
SIZE      = [12, 8192]
VAL       = [2]
TIME      = [4093]
CH_SP     = [True, False]
NUM_BUFF  = [1, 2, 3, 4]
METADATA  = [{"name": "Gabriel", "species": "Homo sapiens", "date": "1995-10-26 14:15:00"}]
BUFF_NAME = ["test"]

THIS_DIR = Path(__file__).parent

def get_buffer_combinations():
    """For the given global variables, give all possible permutations of the inputs

    If passed size is not enough to store the full buffer, it will be replaced by the actual minimum size.
    IMPORTANT: ID CAN ONLY BE A SINGULAR VALUE, THIS BASIC FUNCTION WAS NOT WRITTEN TO HANDLE MULTIPLE IDS.

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
        correct_size = max(size, get_packet_size(header)+get_packet_size(data))  # ensures passed size is valid

        yield {"filename": filename, "params": (id, time, header, data, correct_size, val,
                                                ch_sp, num_buff, metadata, buff_name, ch_names)}


@pytest.fixture(scope="session", params=list(get_buffer_combinations()))
def write_bin_file(request, tmp_path_factory):
    """Generate temporary files with assorted settings

    Args:
        request (dict): pytest request structure, with params as a key
        tmp_path_factory (pytest tmp_path_factory): automatically takes care of generating a temporary path for the test

    Returns:
        dict: file path and buffer used to create file for further test use
    """
    tmp_folder = tmp_path_factory.mktemp("SingleBuffer")
    bin_file   = tmp_folder / (request.param["filename"])
    h5_file    = tmp_folder / "Test.h5"

    buffer = DataBuffer(bin_file, *request.param["params"])
    buffer.write_file()
    return {"file": Path(bin_file), "savefile": h5_file, "buffer": buffer}


def test_bin_file_size(write_bin_file):
    """Ensure file is of the correct size

    Args:
        write_bin_file (pytest fixture): file/buffer to check
    """
    fr = FileReader(write_bin_file["file"])
    fr.open_file()
    header = fr.readline()
    file_size = fr.size

    buffer = write_bin_file["buffer"]

    assert (file_size - len(header)) == buffer.num_buffers*buffer.buffer_size


def test_bin_file_header_parsing(write_bin_file):
    """Ensure header is correctly parsed and imported

    Args:
        write_bin_file (pytest fixture): file/buffer to check
    """
    fp = FileParser(write_bin_file["file"], write_bin_file["savefile"]) 
    fp.open_file()
    fp.read_file_header()

    assert fp.header == write_bin_file["buffer"].header_dict


def test_bin_file_decoder_creation(write_bin_file):
    """Test the ability of the file parser to create a decoder based on the header

    This mostly reformats the header from the JSON where keys must be strings (device names)
    to a dictionary where the key is a value, namely the ID. The decoder has additional fields
    as well to aid in deserialization

    Args:
        write_bin_file (pytest fixture): file and buffer to check
    """

    fp = FileParser(write_bin_file["file"], write_bin_file["savefile"])
    fp.open_file()
    fp.read_file_header()
    fp.generate_decoder()

    # We are really abusing notation here. This will only _summary_work if we have a singular ID.
    # This unpacks the keys from the decoder is then captured in a list. The buffer.id is
    # likewise captured in a list so we can compare the two lists together. This then simply
    # compares to ensure the keys in the decoder matches the available ID
    assert [*fp.decoder.keys()] == [write_bin_file["buffer"].id]

def test_file_buffer_counter(write_bin_file):
    """Test the pre-parsing to count the buffers

    Args:
        write_bin_file (pytest fixture): file and buffer to check
    """

    fp = FileParser(write_bin_file["file"], write_bin_file["savefile"])
    fp.open_file()
    fp.read_file_header()
    fp.generate_decoder()
    fp.count_buffers()

    assert fp.decoder[ID[0]]["num_buffers"] == write_bin_file["buffer"].num_buffers

def test_buffer_data_initialize(write_bin_file):
    """Test the parsing of a buffer

    Args:
        write_bin_file (pytest fixture): file and buffer to check
    """
    fp = FileParser(write_bin_file["file"], write_bin_file["savefile"])
    fp.open_file()
    fp.read_file_header()
    fp.generate_decoder()
    fp.count_buffers()
    fp.initialize_data()

    num_buffers = write_bin_file["buffer"].num_buffers
    expected_num_data_channels, _ = count_data_channels(write_bin_file["buffer"].data_format)

    for i in range(num_buffers):
        (id, header_data, header_time, data, time) = fp.read_data_buffer()
        assert header_time % write_bin_file["buffer"].time == 0
        assert len(data) == expected_num_data_channels
        for channels in data:
            for element in channels:
                assert element == write_bin_file["buffer"].value

def test_buffer_parsing(write_bin_file):
    """Test the parsing of a buffer

    Args:
        write_bin_file (pytest fixture): file and buffer to check
    """
    parser = FileParser(write_bin_file["file"],
                        write_bin_file["savefile"])
    parser.parse()

    with h5py.File(write_bin_file["savefile"], "r") as f:
        time = f['test']['time'][:]
        data = f['test']['data'][:]
        assert len(time) > 0
        assert len(data) > 0
        assert all(np.diff(time) > 0)
        for d in data.flat:
            assert d == write_bin_file["buffer"].value

def test_external_header_parsing(write_bin_file):
    file_path = THIS_DIR / "Data/test_header.txt"

    # A little dirty since we repeat this test an unnecessary amount of times, but gooed enough for now
    fp = FileParser(write_bin_file["file"], write_bin_file["savefile"]) # we just want a dummy file here to see if we can import a decoder
    fp.header = import_external_header(file_path)
    fp.generate_decoder()

    assert True

def test_real_file():
    file_root = "/home/gabriel/Documents/TestMTAG2/"
    file      = "HawaiiTest2.bin"
    header    = "test_header.txt"
    save_file = "Deserialized.h5"

    fp = FileParser(file_root + file,
                    file_root + save_file)
    fp.parse(file_root + header)

    assert True

def test_longer_real_file_external_header(tmp_path_factory):
    file      = THIS_DIR / "Data/MTAG2-Hua-LS.bin"
    header    = THIS_DIR / "Data/test_header.txt"
    save_file = tmp_path_factory.mktemp("real_file_external_header") / "MTAG2-Hua-LS.h5"

    fp = FileParser(file, save_file)
    fp.parse(header)

    assert True