import rawutil
import struct
from pathlib import Path
import os
import tqdm
from json import JSONDecoder

import numpy as np
from animal_tag.serializer.utils import get_packet_size

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
        self.saved_loc = 0

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
    
    def save_current_loc(self):
        self.save_current_loc = self.file_handle.tell()
    
    def seek(self, offset, whence):
        """Seek a new file location

        See also seek() in Python, that this wraps
        Args:
            offset (int): Offset location
            whence (int): File location to start at. 0 is beginning of file, 1 is current file location, and 2 is from end of file.
        """
        self.file_handle.seek(offset, whence)
    
    def tell(self):
        """Get the current file location

        Returns:
            int: Current file location from start of file
        """
        return self.file_handle.tell()


class FileParser():
    def __init__(self, filename: str | Path,
                 savefilename: str | Path):
        self.file = FileReader(filename)
        self.header = {}
        self.decoder = {}  # is populated when file header is read

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
        self.generate_decoder()
        while self.file.bytes_read < self.file.size:
            id, count, time, raw_data = self.read_data_buffer()
            reconstructed_data = self.process_buffer(id, count, time, raw_data)
            if reconstructed_data is not None:
                self.saver.save_data(self.data[id].name, reconstructed_data)

        # All file data read, consume whatever data remains unread
        for id in self.data:
            reconstructed_data = self.data[id].reconstruct(self.header)
            if reconstructed_data is not None:
                self.saver.save_data(self.data[id].name, reconstructed_data)

        self.file.close_file()
        self.saver.close_file()
        self.file.update_bytes_read(0)

    def read_data_header(self, ID, format_dict):
        header_content = self.file.read(get_packet_size(self.decoder[ID])-1)
        data = struct.unpack(self.decoder[ID].header, header_content)
        if self.decoder[ID]["format_has_time"]:
            time = data[header_content.index("T")]
            data = ()

        return {"time": data[header_content.index("T")] if self.decoder[ID]["format_has_time"] else None,
                "bytes": data[:header_content.index("T")] + data[header_content.index("T")+1:] if self.decoder[ID]["format_has_time"] else data}

    def read_raw_data_buffer(self, ID, format_dict):
        return np.asarray(
            struct.unpack(format_dict[ID].data_size * "B",
                          self.file.read(format_dict[ID].data_size)),
            dtype=np.int32)

    def read_data_buffer(self):
        id = self.read_id()
        [count, time] = self.read_data_header(id, self.data)
        raw_data = self.read_raw_data_buffer(id, self.data)
        return (id, count, time, raw_data)

    def read_file_header(self):
        decoder = JSONDecoder()
        line = self.file.readline()
        self.header = decoder.decode(line.decode('utf-8', errors='replace')) 
        return self.header

    def generate_decoder(self):
        decoder = {}
        for (device_name, formatting) in self.header["buffers"].items():
            temp = formatting.copy()  # = as assignment is a refernce copy (editing temp also edits formatting), rather than a deep copy allowing for seperate editing of temp and formatting
            temp.update({"device": device_name})
            del temp["id"]
            temp.update({"format_has_time": "T" in formatting["header"]})
            temp.update({"data_has_time": "T" in formatting["data"]})
            temp.update({"header_size": get_packet_size(formatting["header"])})
            temp.update({"data_packet_size": get_packet_size(formatting["data"])})
            temp.update({"num_packets": (formatting["buffer_size"]-(temp["header_size"]))//temp["data_packet_size"]})
            temp.update({"num_overflow_bytes": formatting["buffer_size"]-temp["num_packets"]*temp["data_packet_size"]-temp["header_size"]})
            temp.update({"data_read_format": "<" + temp["num_packets"]*temp["data"] + temp["num_overflow_bytes"]*"x"})
            temp.update({"num_buffers": 0})  # allocate space to count the number of buffers

            decoder.update({formatting["id"]: temp})
        self.decoder = decoder

    def read_id(self):
        """Read the ID byte of the buffer

        We need the first byte which identifies from which dataset this data has come.
        This is just a single read operation, though will return a list of bytes.
        We thus need to get the first (and only) element of this list to get the ID.
        This ID byte is then used by the decoder to get the right information for reading the data.

        Returns:
            int: ID byte of the buffer
        """
        return self.file.read(1)[0]
    
    def count_buffers(self):
        """Count the number of buffers across the file for pre-allocation.

        We can assume that we have already read the file header and have generated a decoder.
        Otherwise, we would have no idea how to parse the file. Knowing the number of buffers
        will allow for pre-allocating a file with sizes, and is useful for testing.
        """
        self.file.save_current_loc()  #save the current file location for parsing after

        file_loc = self.file.tell()
        while file_loc < self.file.size:
            id = self.read_id()  #what is the current ID
            if id not in self.decoder.keys():
                raise Exception("ID is not in decoder, failed to pre-parse file")
            self.decoder[id]["num_buffers"] += 1
            self.file.seek(self.decoder[id]["buffer_size"]-1, 1)  #skip over the remaining bytes to get to the next ID
            file_loc = self.file.tell()

        self.file.seek(self.file.saved_loc, 0)  #go back to the saved file location to read the file data
