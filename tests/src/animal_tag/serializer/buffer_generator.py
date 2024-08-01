import struct
import argparse
import json

from animal_tag.serializer.utils import get_packet_size


class DataBuffer:
    def __init__(self, output_file : str, id : int, time : int, header_format : str,
                 data_format : str, buffer_size : int, value : int, split_channel : bool,
                 num_buffers : int, metadata : dict, buffer_name : str, channel_names : str):
        """Creates an instance of TestDataBuffer class that is responsible for creating test files based on specifications

        Args:
            output_file (str): The path where to write the output file
            id (int): The ID of the buffer to be passed
            time (int): The time in between buffer writes, written in the header
            header_format (str): The format of the header in the MTAG specification
            data_format (str): The format of the header in the MTAG specification
            buffer_size (int): The size of the whole buffer in bytes
            value (int): The value to write to each channel of the data
            split_channel (bool): Boolean flag for the parser to split the data channels into seperate h5 files
            num_buffers (int): The number of buffers to write
            metadata (dict): The file metadata for the file header
            buffer_name (str): The name of the buffers
            channel_name (str): The name of each data channel
        """
        self.output_file = output_file
        self.id = id
        self.time = time
        self.header_format = header_format
        self.data_format = data_format
        self.buffer_size = buffer_size
        self.value = value
        self.split_channel = split_channel
        self.num_buffers = num_buffers
        self.buffer_name = buffer_name
        self.metadata = metadata
        self.channel_names = channel_names
        self.data = b''
        self.header_dict = {}

    def create_file_header(self):
        """Creates the overall file header

        Returns:
            dict: The file header as a dictionary
        """
        header = {}
        header.update({"metadata": self.metadata})
        header.update({"buffers": {self.buffer_name: {"id": self.id,
                                                      "time": self.time,
                                                      "header": self.header_format,
                                                      "split_channel": self.split_channel,
                                                      "data": self.data_format,
                                                      "buffer_size": self.buffer_size,
                                                      "channel_names": self.channel_names}}})
        self.header_dict = header
        return header

    def create_buffer(self, id : int, time : int, header_format : str,
                      data_format : str, buffer_size : int, value : int):
        """Creates the data buffer based on the specified format and values

        Args:
            id (int): The ID of the device this buffer corresponds to
            time (int): The time at which this buffer was written
            header_format (str): The format of the header in the MTAG format
            data_format (str): The format of the data in the MTAG format
            buffer_size (int): The overall size of the buffer, in bytes
            value (int): The value to write to each data channel

        Returns:
            bytes: Data buffer with the specifications given by the inputs
        """
        header_size = get_packet_size(header_format)
        data_packet_size = get_packet_size(data_format)
        num_reps = (buffer_size - header_size)//data_packet_size  # shorthand division operator to cast to int: a//b is equivalent to floor(a/b) or int(a/b)    
        bytes_underflow = buffer_size - header_size - num_reps*data_packet_size

        buffer = self.create_buffer_header(header_format, id, time)

        for i in range(num_reps):
            temp_data = [value if char != 'X' else 0 for char in data_format]
            if data_format.find('T') != -1:  # this function gives -1 on failure, which if it does we can ignore the case
                temp_data[data_format.find('T')] = int(time + (i+1)*self.time/num_reps)
            buffer += struct.pack("<"+self._correct_format(data_format), *temp_data)  # we need to go from the MTAG format to the struct/rawutils format
            # we need to pass as seperate arguments each element of temp_data, thus the use of the * operator
        buffer += struct.pack("<"+bytes_underflow*"B", *([0 for _ in range(bytes_underflow)]))  # similar as above, keeps the code concise here

        return buffer

    def create_buffer_header(self, header_format : str, id : int, time: int):
        """Create the binary header for each data buffer in the MTAG format

        Args:
            header_format (str): The buffer header format
            id (int): The ID of the device that this header corresponds to
            time (int): The time at which this buffer was written

        Returns:
            _type_: _description_
        """
        data_pack = [0 for _ in header_format]
        data_pack[header_format.find("B")] = id
        data_pack[header_format.find("T")] = time
        return struct.pack("<" + self._correct_format(header_format), *data_pack)

    def write_file(self):
        """Write an MTAG file that satisfies the class inputs
        """

       # with open(self.output_file, 'w') as f:
       #     json.dump(self.create_file_header(), f, separators=(',', ':'))
       #     f.write('\n')  # get a newline to terminate the header
            
        with open(self.output_file, 'wb') as f:
            header = json.dumps(self.create_file_header(), ensure_ascii=False).encode('utf-8')  # binary file, so we have to encode the string
            header += '\n'.encode('utf-8')  # this is a binary file, we need to encode the string

            self.data += header
            f.write(header)

            for i in range(self.num_buffers):
                buffer = self.create_buffer(id=self.id, time=(i+1)*self.time, header_format=self.header_format,
                                           data_format=self.data_format, buffer_size=self.buffer_size,
                                           value=self.value)
                self.data += buffer
                f.write(buffer)
   
    def _correct_format(self, format : str):
        """Takes in mtag deserializer format and returns rawutil/struct formatting

        Args:
            format (str): MTAG format string to convert

        Returns:
            str: MTAG format string converted into struct/rawutil format to allow for packing/unpacking
        """
        actual_format = format.replace("X", "B")
        actual_format = actual_format.replace("T", "L")
        return actual_format


if __name__ == '__main__':
    """This function will generate a header and multiples of one buffer type
    
    The command line parsing is not set up to gracefully handle multiple different buffer types with different specifications.
    For such usage, it is recommended to instead programatically call TestDataBuffer in a Python program.
    The command line parsing could be changed to support such structure, but it may not be worth the development time, since the
    tests will be written to be generated from a Python program anyways. Furthermore, it may be easier to test the Rust deserializer
    (or other deserializers) using tools in that language rather than a Python one.
    But for now this is being provided to support a baseline for serializing simple files to use for testing.
    At the very least, it gives a baseline for what the programs written in another language should look like.
    """

    parser = argparse.ArgumentParser(
        prog='generate_test_file.py',
        description='Creates file for testing the Rust deserializer',
        epilog='Gabriel Antoniak (gjantoniak@gmail.com)')

    parser.add_argument('-i','--id', type=int, default= 1, help='The ID of the buffer to add to the file')
    parser.add_argument('-v', '--val', type=int, default=1, help='The value to write to the file for all of the channels')
    parser.add_argument('-t', '--time', type=int, default=1000, help='The time in between each buffer write')
    parser.add_argument('-f', '--format', type=str, default='<H', help='Data format using struct/rawutil strings')
    parser.add_argument('-d', '--data_size', type=int, default=8192, help='Size of data buffer')
    parser.add_argument('-H', '--header_format', type=str, default='BLX', help='The format of the header to add')
    parser.add_argument('-s', '--split_channel', type=bool, default=False, help='Split the named channels into seperate files')
    parser.add_argument('-o', '--output_file', type=str, default='test_output.bin', help='Set output file for the data')
    parser.add_argument('-I', '--buffer_name', type=str, default='device', help='The name of the buffer being parsed')
    parser.add_argument('-n', '--num_buffers', type=int, default=1, help='Number of buffers to write')
    parser.add_argument('-N', '--name', type=str, default="Lono", help="Name of the animal")
    parser.add_argument('-S', '--species', type=str, default="Tursiops truncatus", help="Animal species")
    parser.add_argument('-D', '--date', type=str, default="1995/10/26 14:15:00", help="Experiment time")
    parser.add_argument('-c', '--channel_names', nargs='+', type=str, default='ch1', help="The name of each data channel")

    args = parser.parse_args()

    metadata = {"name": args.name,
                "species": args.species,
                "date": args.date}

    test_buffer = DataBuffer(output_file=args.output_file, id=args.id, time=args.time,
                             header_format=args.header_format, data_format=args.format, buffer_size=args.data_size,
                             value=args.val, split_channel=args.split_channel, num_buffers=args.num_buffers,
                             metadata=metadata, buffer_name=args.buffer_name, channel_names=args.channel_names)
    test_buffer.write_file()