import pytest
from pathlib import Path

import itertools

from animal_tag.serializer.buffer_generator import DataBuffer
from animal_tag.serializer.deserializer import FileReader, FileParser
from animal_tag.serializer.utils import get_packet_size

ID        = [1]
HEADER    = ["BTx"]
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

    buffer = DataBuffer(bin_file, *request.param["params"])
    buffer.write_file()
    return {"file": Path(bin_file), "buffer": buffer}


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
    fp = FileParser(write_bin_file["file"], 'Test.h5') 
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

    fp = FileParser(write_bin_file["file"], 'Test.h5')
    fp.open_file()
    fp.read_file_header()
    fp.generate_decoder()

    # We are really abusing notation here. This will only _summary_work if we have a singular ID.
    # This unpacks the keys from the decoder is then captured in a list. The buffer.id is
    # likewise captured in a list so we can compare the two lists together. This then simply
    # compares to ensure the keys in the decoder matches the available ID
    assert [*fp.decoder.keys()] == [write_bin_file["buffer"].id]

def test_file_preparser(write_bin_file):
    """Test the pre-parsing to count the buffers

    Args:
        write_bin_file (pytest fixture): file and buffer to check
    """

    fp = FileParser(write_bin_file["file"], 'Test.h5')
    fp.open_file()
    fp.read_file_header()
    fp.generate_decoder()
    fp.count_buffers()

    assert fp.decoder[ID[0]]["num_buffers"] == write_bin_file["buffer"].num_buffers

def test_buffer_parse(write_bin_file):
    """Test the parsing of a buffer

    Args:
        write_bin_file (pytest fixture): file and buffer to check
    """
    fp = FileParser(write_bin_file["file"], 'Test.h5')
    fp.open_file()
    fp.read_file_header()
    fp.generate_decoder()
    fp.count_buffers()

    num_buffers = write_bin_file["buffer"].num_buffers

    for i in range(num_buffers):
        (id, header_data, header_time, data, time) = fp.read_data_buffer()
        assert header_time % write_bin_file["buffer"].time == 0
        assert len(data) == len(write_bin_file["buffer"].data_format)
        for channels in data:
            for element in channels:
                assert element == write_bin_file["buffer"].value
