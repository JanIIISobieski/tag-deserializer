import rawutil
import struct
from pathlib import Path
import os
import tqdm
from json import JSONDecoder

import numpy as np
import pytest

class FileReader:
    def __init__(self, filename: str | Path):
        self.name = filename
        self.size = os.path.getsize(filename)
        self.bytes_read = 0
        self.file_handle = 0
        self.loading_bar = tqdm.tqdm(initial=0, total=self.size,
                                     unit="B", unit_scale=True,
                                     unit_divisor=1024, leave=True)
        self.data_buffer_start = []

    def update_bytes_read(self, amount):
        self.bytes_read += amount
        self.loading_bar.update(amount)

    def open_file(self):
        self.file_handle = open(self.name, 'rb')

    def close_file(self):
        self.file_handle.close()

    def readline(self):
        content = self.file_handle.readline()
        self.update_bytes_read(len(content))
        self.data_buffer_start = len(content)
        return content

    def read(self, num_bytes):
        self.update_bytes_read(num_bytes)
        return self.file_handle.read(num_bytes)


class FileParser():
    def __init__(self, filename: str | Path,
                 savefilename: str | Path):
        self.file = FileReader(filename)
        self.header = {}

    def add_data_types(self, data_types):
        for data_type in data_types:
            self.data[data_type.key] = data_type

    def process_buffer(self, ID, count, time, data):
        if self.data[ID].add_raw_data(count, time, data):
            return self.data[ID].reconstruct(self.header)
        else:
            return None

    def open_file(self):
        self.file.open_file()

    def parse(self):
        self.file.open_file()
        self.header = self.read_file_header()
        while (self.file.bytes_read + 8192) <= self.file.size:
            ID, count, time, raw_data = self.read_data_buffer()
            reconstructed_data = self.process_buffer(ID, count, time, raw_data)
            if reconstructed_data is not None:
                self.saver.save_data(self.data[ID].name, reconstructed_data)

        # All file data read, consume whatever data remains unread
        for ID in self.data:
            reconstructed_data = self.data[ID].reconstruct(self.header)
            if reconstructed_data is not None:
                self.saver.save_data(self.data[ID].name, reconstructed_data)

        self.file.close_file()
        self.saver.close_file()
        self.file.update_bytes_read(0)

    def read_data_header(self, ID, format_dict):
        header_content = self.file.read(format_dict[ID].header_size)
        return struct.unpack(format_dict[ID].header_format,
                             header_content)

    def read_raw_data_buffer(self, ID, format_dict):
        return np.asarray(
            struct.unpack(format_dict[ID].data_size * "B",
                          self.file.read(format_dict[ID].data_size)),
            dtype=np.int32)

    def read_data_buffer(self):
        ID = self.read_id()
        [count, time] = self.read_data_header(ID, self.data)
        raw_data = self.read_raw_data_buffer(ID, self.data)
        return (ID, count, time, raw_data)

    def read_file_header(self):
        decoder = JSONDecoder()
        line = self.file.readline()
        self.header = decoder.decode(line.decode('utf-8', errors='replace')) 
        return self.header

    def read_id(self):
        return self.file.read(1)[0]