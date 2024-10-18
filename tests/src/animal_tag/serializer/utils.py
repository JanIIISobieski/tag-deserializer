import numpy as np
from collections import deque 

# Stores the mapping from MTAG key to the size of the key
SIZE_DICT = {"B": 1, "b": 1, # int_8 and uint_8
             "H": 2, "h": 2, # int_16 and uint_16
             "U": 3, "u": 3, # int_24 and uint_24
             "f": 4,         # f32
             "L": 4, "l": 4, # int_32 and uint_32
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
             "L": np.int32,
             "l": np.uint32,
             "X": np.nan,
             "x": np.nan,
             "T": np.uint64}

MAX_TIME = 2**32 - 1
MICROSECONDS_IN_A_SECOND = 1e6

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

def unwrapper(values, max_number, bad_frac=0.5):
    """
    Function to unwrap unsigned integers

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


class DataBuffer():
    def __init__(self, header_data=deque(), header_time=deque(), data=deque(), time=deque(), pop_boundry=1280):
        self.header_data    = header_data
        self.header_time    = header_time
        self.time           = time
        self.data           = data
        self.time_offset    = 0
        self.num_buffers    = 0
        self.num_indices    = 0
        self.pop_boundry    = pop_boundry

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
            self.extend_header_data(header_data)

        if header_time:
            self.extend_header_time(header_time)

        if time:
            self.extend_time([self.time])

        if data:
            self.extend_data(data)

        self.num_buffers += 1
        
        return self.num_buffers >= self.pop_boundry

    def extend_header_data(self, header_data):
        self.header_data.append(header_data)

    def extend_header_time(self, header_time):
        self.header_time.append(header_time)

    def extend_time(self, time):
        self.time.extend(time)

    def extend_data(self, data):
        for (i, data_channel) in enumerate(data):
            self.extend_data_channel(data_channel, i)

    def extend_data_channel(self, data, channel):
        self.data[channel].extend(data)

    def pop_data(self, num_buffer_to_pop: int, num_packets_per_buffer: int) -> dict[float, float]:
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

        Returns:
            dict: A dictionary with the time and data of the popped buffers
        """
        len_data     = num_buffer_to_pop*num_packets_per_buffer
        num_channels = len(self.data)

        data = np.zeros(shape=(len_data, num_channels))

        #if we only have header_time and not time, use header_time
        # self.header_time is true if self.header_time is not empty
        # self.time is true if self.time is not empty
        if self.header_time and not self.time:
            #TODO: implement header_buffer calculation for time. Only needed for hydrophone-like things
            pre_time = self.time_offset + np.repeat( [self.header_time.popleft() for _ in range(num_buffer_to_pop)], num_packets_per_buffer)
            pass

        #if time is an empty deque, this will be false
        if self.time:
            pre_time = self.time_offset + np.asarray([ self.time.popleft() for _ in range(len_data) ] )

        # We have popped the times, but now we need to unwrap them if we overflowed
        time, num_overflows = unwrapper(pre_time, max_number=MAX_TIME, bad_frac=0.5)
        self.time_offset += num_overflows*MAX_TIME

        for (i, channel_data) in enumerate(self.data):
            temp = [ channel_data.popleft() for _ in range(len_data) ]
            data[:, i] = temp

        return {"time": time/MICROSECONDS_IN_A_SECOND, "data": data}