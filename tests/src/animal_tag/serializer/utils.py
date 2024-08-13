import numpy as np

# Stores the mapping from MTAG key to the size of the key
SIZE_DICT = {"B": 1, "b": 1,
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