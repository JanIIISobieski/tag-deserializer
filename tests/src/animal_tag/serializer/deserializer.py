import rawutil
import struct
from pathlib import Path
import os
import tqdm
from json import JSONDecoder
from collections import deque
import h5py

import numpy as np
from animal_tag.serializer.utils import (get_packet_size, correct_format,
                                         count_data_channels, import_external_header,
                                         DataBuffer, DataWrite)


class SaveFileLoc():
    def __init__(self, size):
        self.size = size
        self.ind = 0

    def set_size(self, val):
        self.size = val

    def add_ind(self, val):
        self.ind += val


class FileSaver():
    def __init__(self, filename: str, decoder: dict = {}):
        if filename:
            self.file = h5py.File(filename, 'w')
        else:
            self.file = ""

        self.locs = {}
        if decoder:
            self.create_datasets(decoder)  # sets self.locs internally            

    def close_file(self):
        for key in self.locs:
            if self.locs[key].ind < self.locs[key].size:
                self.file[key]['time'].resize(self.locs[key].ind, axis=0)
                self.file[key]['data'].resize(self.locs[key].ind, axis=0)
        self.file.close()

    def save_header(self, header):
        self._save_header(self.file, header)

    def save_data(self, ID, to_save : DataWrite):
        for time, data in to_save.sub_chunks():
            self.save_data_chunk(ID, time, data, len(time))
            
    def save_data_chunk(self, ID, time, data, chunk_size):
        time_set = self.file[ID]['time']
        data_set = self.file[ID]['data']
        if self.locs[ID].size < self.locs[ID].ind + chunk_size:
            new_size = 2*time_set.shape[0]
            time_set.resize(new_size, axis=0)
            data_set.resize(new_size, axis=0)
            self.locs[ID].set_size(new_size)
        self.file[ID]['time'][self.locs[ID].ind:
                              (self.locs[ID].ind+chunk_size)] = time
        self.file[ID]['data'][self.locs[ID].ind:
                              (self.locs[ID].ind+chunk_size), :] = data
        self.locs[ID].add_ind(chunk_size)

    def _save_header(self, hf, header_dict):
        for k, v, in header_dict.items():
            if isinstance(v, dict):
                g = hf.create_group(k)
                self._save_header(g, v)
            else:
                if v is None:
                    # need to change None to make it saveable by h5py
                    v = np.nan
                hf.create_dataset(k, data=v)

    def create_datasets(self, decoder: dict):
        dataset_dict = dict()
        for dicts in decoder.values():
            num_samples = dicts["num_packets"]*dicts["num_buffers"]

            if num_samples == 0:
                continue  #skip if we don't actually have this in the buffer system

            # TODO: Assign a specific data type to each channel to save space
            g = self.file.create_group(dicts["device"])
            d1 = g.create_dataset('time', shape=(num_samples, ),
                                  maxshape=(num_samples, ),
                                  chunks=(dicts["num_packets"], ),
                                  dtype='d')
            #TODO: Add units
            #d1.attrs['units'] = 'sec'

            num_data_channels = len(dicts["channel_names"])

            d2 = g.create_dataset('data', shape=(num_samples,
                                                 num_data_channels),
                                  maxshape=(num_samples, num_data_channels),
                                  chunks=(dicts["num_packets"], num_data_channels),
                                  dtype='d')
            #d2.attrs['units'] = dicts.units

            dataset_dict[dicts["device"]] = SaveFileLoc(size=num_samples) #we know what the size is
        self.locs = dataset_dict


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
        self.saved_loc = self.file_handle.tell()
    
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
                 savefilename : str | Path,
                 num_to_pop : int = 1024,
                 buffer_pop_boundry : int = 1280):
        self.file    : FileReader      = FileReader(filename)
        self.saver   : FileSaver       = FileSaver(savefilename)
        self.header  : dict[str, dict] = {}
        self.decoder : dict[int, dict] = {}  # is populated when file header is read
        self.data    : dict[int, DataBuffer] = {}
        self.num_to_pop : int = num_to_pop
        self.buffer_pop_boundry : int = buffer_pop_boundry
        self.tot_buffers = 0

    def process_buffer(self, ID, header_data, header_time, data, time):
        if self.data[ID]["data"].append_raw_data(header_data, header_time, data, time):
            num_popped = min(self.num_to_pop, self.data[ID]["num_buffs"])
            reconstructed_data = self.data[ID]["data"].pop_data(num_popped,
                                                                self.decoder[ID]["num_packets"],
                                                                self.decoder[ID]["num_channels"])
            self.data[ID]["num_buffs"] -= num_popped
            return reconstructed_data
        else:
            return None

    def initialize_data(self):
        """Initialize the data buffer based on the decoder for each device

        We need to get the proper channel_size for each decoder. By the way
        our decoder scheme works, we are able to fully parse each buffer to get
        the values, no data sample ever stretches across a buffer boundry. This
        allows us to maximize the rate at which we sample on the hardware, and
        allows for a simpler deserializing scheme (especially relative to a
        deserializing scheme that overflows over buffer boundries). As such,
        all we need to do is to assign data to each channel, and keep track
        of the number of buffers that were added
        """
        for key, value in self.decoder.items():
            empty_buffer = DataBuffer(data=[deque() for char in value["data"] if char.lower() != "x" and char.lower() != "t"],
                                      pop_boundry=self.buffer_pop_boundry,
                                      chunk_size=value["num_packets"])
            empty_buffer.reset()  # forcefully clear any data, suspect some scoping error within pytest perhaps
                                  # or how the variables are created, occassionally these would contain data
                                  # With these lines incorporated, tests do not really have an issue of passing
            self.data.update({key: {"data": empty_buffer,
                                    "num_buffs": 0}
                             })

    def open_file(self):
        self.file.open_file()

    def parse(self, header_file : str | Path = ""):
        self.file.open_file()
        if header_file: # check if passed, then we grab header file from here
            self.header = import_external_header(header_file)
        else:
            self.header = self.read_file_header() 
        self.generate_decoder()
        self.count_buffers()
        self.saver.create_datasets(self.decoder)
        self.initialize_data()
        buffers_read = 0
        while buffers_read < self.tot_buffers:
            id, header_data, header_time, data, time = self.read_data_buffer()
            reconstructed_data = self.process_buffer(id, header_data, header_time, data, time)
            buffers_read += 1
            if reconstructed_data is not None:
                self.saver.save_data(self.decoder[id]["device"], reconstructed_data)

        # All file data read, consume whatever data remains unread
        for id in self.data.keys():
            if self.data[id]["num_buffs"] > 0:  #ensure there actually is data to pop here, otherwise error would be thrown
                reconstructed_data = self.data[id]["data"].pop_data(self.data[id]["num_buffs"],
                                                                    self.decoder[id]["num_packets"],
                                                                    self.decoder[id]["num_channels"])
                self.saver.save_data(self.decoder[id]["device"], reconstructed_data)

        self.file.close_file()
        self.saver.close_file()
        self.file.update_bytes_read(0)

    def read_data_header(self, ID):
        header_content = self.file.read(get_packet_size(self.decoder[ID]["header"])-1)
        data = struct.unpack(correct_format(self.decoder[ID]["header"][1:]), header_content)
        if self.decoder[ID]["header_has_time"]:
            t_index = self.decoder[ID]["header"][1:].index("T")
            time = data[t_index]
            data = data[:t_index] + data[t_index+1:]
        else:
            time = []
            data = data

        return data, time

    def read_raw_data_buffer(self, ID):
        # Read the data from the buffer in
        all_bytes = self.file.read(self.decoder[ID]["buffer_size"] - self.decoder[ID]["header_size"])
        if "u" in self.decoder[ID]["data"].lower():  # for handling 24-bit numbers, we need rawutil
            raw_data = rawutil.unpack(correct_format(self.decoder[ID]["data_read_format"]), all_bytes)
        else:  # struct is faster for all other types
            raw_data = struct.unpack(correct_format(self.decoder[ID]["data_read_format"]), all_bytes)
        # Now based on the data, seperate out the channels and use the smallest numpy type to fit it in
        #TODO: allow for null bytes to be handled elegantly here (right now we can only handle data types that do not contain null bytes in sampling)
        data = [raw_data[i::len(self.decoder[ID]["data"])] for i, channel in enumerate(self.decoder[ID]["data"])]  #index the list
        
        if self.decoder[ID]["data_has_time"]:
            t_index = self.decoder[ID]["data"].index("T")
            time = data[t_index]
            data = data[:t_index] + data[(t_index+1):]
        else:
            time = []
            data = data
        
        return data, time

    def read_data_buffer(self):
        id = self.read_id()
        [header_data, header_time] = self.read_data_header(id)
        [data, time] = self.read_raw_data_buffer(id)
        self.data[id]["num_buffs"] += 1  #increment num_buffs
        return (id, header_data, header_time, data, time)

    def read_file_header(self):
        decoder = JSONDecoder()
        line = self.file.readline()
        self.header = decoder.decode(line.decode('utf-8', errors='replace')) 
        return self.header

    def generate_decoder(self):
        decoder = {}
        for device_name, formatting in self.header["buffers"].items():
            temp = formatting.copy()  # = as assignment is a refernce copy (editing temp also edits formatting), rather than a deep copy allowing for seperate editing of temp and formatting
            temp.update({"device": device_name})
            del temp["id"]
            temp.update({"header_has_time": "T" in formatting["header"]})
            temp.update({"data_has_time": "T" in formatting["data"]})
            temp.update({"header_size": get_packet_size(formatting["header"])})
            temp.update({"data_packet_size": get_packet_size(formatting["data"])})
            temp.update({"num_packets": (formatting["buffer_size"]-(temp["header_size"]))//temp["data_packet_size"]})
            temp.update({"num_overflow_bytes": formatting["buffer_size"]-temp["num_packets"]*temp["data_packet_size"]-temp["header_size"]})
            temp.update({"data_read_format": "<" + temp["num_packets"]*temp["data"] + temp["num_overflow_bytes"]*"x"})
            temp.update({"num_buffers": 0})  # allocate space to count the number of buffers
            num_data_channels, _ = count_data_channels(formatting["data"])
            temp.update({"num_channels": num_data_channels})

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
            self.tot_buffers += 1
            self.file.seek(self.decoder[id]["buffer_size"]-1, 1)  #skip over the remaining bytes to get to the next ID
            file_loc = self.file.tell()

        self.file.seek(self.file.saved_loc, 0)  #go back to the saved file location to read the file data