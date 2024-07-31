import pytest
from pathlib import Path
from animal_tag.serialization.buffer_generator import DataBuffer

ID        = 1
HEADER    = "BTX"
DATA      = "HH"
SIZE      = 10
VAL       = 2
TIME      = 1000
CH_SP     = False
NUM_BUFF  = 1
METADATA  = {"name": "Gabriel", "species": "Homo sapiens", "date": "1995-10-26 14:15:00"}
CH_NAMES  = ["ch1", "ch2"]
BUFF_NAME = "test"

@pytest.fixture(scope="session", params=[
    {"folder"  : "Short",
     "fileroot": "TestFile1.bin"}
],
ids = [
    "Short File"
])
def write_bin_file(request, tmp_path_factory):
    tmp_folder = tmp_path_factory.mktemp(request.param["folder"])
    bin_file   = tmp_folder / (request.param["fileroot"] + ".bin")

    buffer = DataBuffer(output_file=bin_file,
                        id=ID,
                        time=TIME,
                        header_format=HEADER,
                        data_format=DATA,
                        buffer_size=SIZE,
                        value=VAL,
                        split_channel=CH_SP,
                        num_buffers=NUM_BUFF,
                        metadata=METADATA,
                        buffer_name=BUFF_NAME,
                        channel_names=CH_NAMES
                        )
    buffer.write_file()
    return {"file": bin_file}

def test_bin_file(write_bin_file):
    assert True