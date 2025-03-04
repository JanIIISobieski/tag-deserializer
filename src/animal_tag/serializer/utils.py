import numpy as np
from collections import deque 
from pathlib import Path
from os import stat
from json import JSONDecoder
from itertools import starmap, repeat, islice

# Stores the mapping from MTAG key to the size of the key
SIZE_DICT = {"B": 1, "b": 1, # uint_8 and int_8
             "H": 2, "h": 2, # uint_16 and int_16
             "U": 3, "u": 3, # uint_24 and int_24
             "I": 4, "i": 4, # uint_32 and int_32
             "f": 4,         # f32
             "L": 4, "l": 4, # uint_32 and int_32
             "X": 1, "x": 1, # padding byte, explicitly taken care of rather than relying on struct/rawutil pack, always 0
             "T": 4          # custom type, corresponds to L (uint_32) from struct/rawutil, corresponds to a time, which will have special treatment
             }

# Stores the mapping from the MTAG key to the datatype that can store the key
# For simplicity's sake, we will use the largest type that can still store the data, saving space in the h5 file for
# faster writing/reading from file (though we will pay a penalty on the reading side to convert INT values into floats/doubles)
TYPE_DICT = {"B": np.int8,
             "b": np.uint8,
             "H": np.int16,
             "h": np.uint16,
             "U": np.int32,
             "u": np.uint32,
             "f": np.single,
             "i": np.int32,
             "I": np.uint32,
             "L": np.int32,
             "l": np.uint32,
             "X": np.nan,
             "x": np.nan,
             "T": np.uint64}

MAX_TIME = 2**32 - 1
MICROSECONDS_IN_A_SECOND = 1e6

POPPER = lambda d, n: starmap(d.popleft, repeat((), n))

def get_packet_size(format : str):
    """Find the size of the data packet

    Args:
        format (str): Data packet format

    Returns:
        int: The size of the data packet in bytes
    """
    packet_size = 0
    for char in format:
        packet_size += SIZE_DICT[char]
    return packet_size


def get_packet_type(format : str):
    """Get the type of the data packet

    Args:
        format (str): Data pakcet format

    Returns:
        list: the type of the data packet for each channel
    """
    packet_type = []
    for char in format:
        packet_type.append(TYPE_DICT[char])
    return packet_type

def correct_format(format : str):
    """Replace custom format string with struct/rawutil compatible string

    What has to be done is every "T" for time to be replaced with "L" during unpacking.
    This allows us to read the time vector correctly as an unsigned int32. We have "T"
    in the custom format as the "T" allows the rest of the deserializer to know which
    element corresponds to time.

    Args:
        format (str): custom format string

    Returns:
        str: struct/rawutil compatible string
    """
    return format.replace("T", "I")


def count_data_channels(format : str):
    """Count the number of data and time channels in a format

    Args:
        format (str): Format string of the data

    Returns:
        tuple[int]: The number of data channels and number of time channels
    """
    data_channels = len(format)
    time_channels = 0
    if format.find("T") != -1:
        data_channels -= 1
        time_channels += 1
    return data_channels, time_channels


def consume(iter, n=None):
    """Consume as fast as possible the iterable

    Args:
        iter (Iterable[Any]): Iterable to consume.
        n (int, optional): Number of elements to consume. Defaults to None. If is None, entirety of the iterator will be consumed.
    """
    if n is None:
        deque(iter, maxlen=0)
    else:
        next(islice(iter, n, n), None)


def unwrapper(values, max_number, bad_frac=0.5):
    """
    Function to unwrap unsigned integers, like time or buffer counts (if buffer counts are used)

    Parameters
    ----------
    values : iterable
        Array of values to sort.
    max_number : int
        The maximum expected value before an overflow
    bad_frac : float, optional
        What is the consecutive negative difference to count as an overflow as
        a fraction of max_number. The default is 0.5. That is, -0.5*max_number
        difference from item i to item i+1 suggests that there was an overflow.
        Practically, such a large difference is not expected in the datasets

    Returns
    -------
    numpy array
        Sorted array values
    int
        Number of overflows
    """
    # Figure out overflow boundries
    items = np.asarray(values)
    # large positive diffs indicate wrong order around an overflow
    # (i.e. an ordering of [254 0 255] for the count indices)
    # This is an assumption, but a fairly valid one, as the hardware should
    # not miss 127 buffer writes.
    large_pos_diffs = np.where(np.diff(items) >= bad_frac * max_number)[0]

    # Now adjust for the errors that occur when the items were written
    # in the wrong order around an overflow
    # [254 0 255] -> [254 0 -1]
    # We also need to watch out for an ordering like
    # [253, 0, 254, 255, 1] -> [253, 0, -2, -1, 1]
    # Therefore, after finding  a large_pos_diffs, for each of these we need to
    # find where after a large_pos_diff we have a negative_pos_diff
    for index in large_pos_diffs:
        # subtract out max_number just from the element at this index and any
        # that are close by
        end_offset = np.where(
            np.diff(items[(index+1):]) <= -bad_frac*max_number)[0][0]
        items[(index+1):(index+1+end_offset+1)] -= max_number

    # large negative diffs indicate integer overflow
    large_neg_diffs = np.where(np.diff(items) <= -bad_frac * max_number)[0]

    # Only now correct for overflow
    # [254 0 255] -> [254 0 -1] (from large pos_dif) -> [254 256 255]
    # (from this large neg_diffs, meaning we are ready to sort
    for index in large_neg_diffs:
        # add max_number to each element from this index onwards
        items[(index+1):] += max_number

    return items, len(large_neg_diffs)


def import_external_header(filename : str | Path):
    """Imports external header for parsing

    Args:
        filename (str | Path): Filename of the new header

    Returns:
        dict: Dictionary representation of the header
    """
    file_size = stat(filename).st_size
    decoder = JSONDecoder()
    with open(filename, 'r') as f:
        data = f.read(file_size)
        header = decoder.decode(data)
    return header

class DataWrite:
    def __init__(self, time, data, chunk_size):
        self.time = time
        self.data = data
        self.chunk_size = chunk_size

    def sub_chunks(self):
        """Generate chunk sized array from the time and data that is to be written

        Yields:
            tuple(Iterable[Any], Iterable[Any]): time and data chunk of larger array
        """
        assert(len(self.time) % self.chunk_size == 0, "Length of time must be a multiple of chunk_size")
        num_chunks = len(self.time)//self.chunk_size
        for i in range(num_chunks):
            yield self.time[self.chunk_size*i : (self.chunk_size*(i+1))], self.data[self.chunk_size*i : (self.chunk_size*(i+1)), :] 


class DataBuffer():
    def __init__(self, header_data=deque(), header_time=deque(), data=deque(), time=deque(), pop_boundry=1280, chunk_size=1):
        self.header_data    = header_data
        self.header_time    = header_time
        self.time           = time
        self.data           = data
        self.time_offset    = 0
        self.num_buffers    = 0
        self.last_time      = 0
        self.pop_boundry    = pop_boundry
        self.chunk_size     = chunk_size

    def append_raw_data(self, header_data, header_time, data, time):
        """Extend the underlying data buffer with new data

        IMPORTANT: we assume here that we add one buffer at a time. This is the scheme
        of the current deserializer. If this ever changes, this function will have to
        change as well.

        Args:
            header_data (deque[Any]): Data coming from the header. Can be empty.
            header_time (deque[Any]): Time data coming from the header. Can be empty.
            time (deque[Any]): Time data associated with sampling. Can be empty.
            data (deque[Any]): Data associated with sampling. Can be empty.
        """
        if header_data:  # implicitly check if we passed this
            self.header_data.append(header_data)

        if header_time:
            self.header_time.append(header_time)

        if time:
            self.time.extend(time)

        if data:
            self.extend_data(data)

        self.num_buffers += 1
        
        if self.num_buffers != len(self.header_time):
            raise AssertionError("Num buffers should be equal to length of header_time")

        return self.num_buffers >= self.pop_boundry

    def extend_data(self, data):
        """Extends the individual data channels for this DataBuffer

        Args:
            data (Iterable[Iterable[Any]]): An array of arrays, with each internal array corresponding to the data channels
        """
        for (i, data_channel) in enumerate(data):
            self.data[i].extend(data_channel)

    def pop_data(self, num_buffer_to_pop: int, num_packets_per_buffer: int, num_channels : int) -> DataWrite:
        """Number of buffers to pop off the queue ready for writing

        We need to grab the data off of this queue. We will need to
        create a time vector to associate with the data. We will create
        it either from the buffer times or from time. Buffer time will
        give the time at intervals of num_packets (see decoder in
        deserializer). We will assume constant sampling rate in between
        the num_packets. If we are given time, then life is easy, as
        each packet already has time associated with it, so we just
        grab the time.

        Args:
            num_buffers_to_pop (int): Number of time indices to pop.
            num_packets_per_buffer(int): Number of packets per buffer
            num_channels(int): The number of data channels per sampling event

        Returns:
            DataWrite: An object from which we can grab data for running
        """
        len_data     = num_buffer_to_pop*num_packets_per_buffer

        data = np.zeros(shape=(len_data, num_channels))

        #if we only have header_time and not time, use header_time
        # self.header_time is true if self.header_time is not empty
        # self.time is true if self.time is not empty
        if self.header_time and not self.time:
            popped_times = [self.last_time]
            #popped_times.extend([self.header_time.popleft() for _ in range(num_buffer_to_pop)])
            popped_times.extend(POPPER(self.header_time, num_buffer_to_pop))
            # We have popped the times, but now we need to unwrap them if we overflowed
            pre_time, num_overflows = unwrapper(popped_times, max_number=MAX_TIME, bad_frac=0.5)            
            time     = np.zeros(shape=(num_packets_per_buffer*num_buffer_to_pop, ))
            # We assume a constant sampling rate in between the buffers. So we can reinterpolate between the time bounds
            for i in range(num_buffer_to_pop):
                time[i*num_packets_per_buffer : (i+1)*num_packets_per_buffer] = np.linspace(popped_times[i], popped_times[i+1], num_packets_per_buffer+1)[1:]
            self.last_time = time[-1]
        elif self.time: #if time is an empty deque, this will be false
            #pre_time = self.time_offset + np.asarray([ self.time.popleft() for _ in range(len_data) ] )
            pre_time = self.time_offset + np.asarray(list(POPPER(self.time, len_data)))
            # We have popped the times, but now we need to unwrap them if we overflowed
            time, num_overflows = unwrapper(pre_time, max_number=MAX_TIME, bad_frac=0.5)
            # IMPORTANT: for this case, it is possible to have header_time, we are just not using it.
            # And so, we must pop the times to ensure that we don't overfill the deque and take up
            # valuable space
            if self.header_time:
                consume(POPPER(self.header_time, num_buffer_to_pop))
        else:  # where has the time gone... it is not in the buffer
            raise("We have no way to get time, passed in neither header nor with data\n")

        # We get rid of header_data for now, as we are not using it in the current versions
        if self.header_data:
            consume(POPPER(self.header_time, num_buffer_to_pop))

        # Adjust the time offset based on overflows
        self.time_offset += num_overflows*MAX_TIME

        # Pop the data channels individually for the deserialization
        for (i, channel_data) in enumerate(self.data):
            #temp = [ channel_data.popleft() for _ in range(len_data) ]
            temp = list(POPPER(channel_data, len_data))
            data[:, i] = temp

        self.num_buffers -= num_buffer_to_pop  # update the number of buffers based on the amount that was popped

        return DataWrite(time=time/MICROSECONDS_IN_A_SECOND, data=data, chunk_size=self.chunk_size)
    
    def reset(self):
        """Resets the data in the DataBuffer to be empty

        For some reason it was needed to write this function so that pytest would run as expected.
        """
        self.header_time = deque()
        self.header_data = deque()
        self.time        = deque()
        for (i, _) in enumerate(self.data):
            self.data[i] = deque()
