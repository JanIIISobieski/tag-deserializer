# Stores the mapping from MTAG key to the size of the key
DATA_DICT = {"B": 1, "b": 1,
             "H": 2, "h": 2, # int_16 and uint_16
             "U": 3, "u": 3, # int_24 and uint_24
             "f": 4,         # f32
             "L": 4, "l": 4, # int_32 and uint_32
             "X": 1, "x": 1, # padding byte, explicitly taken care of rather than relying on struct/rawutil pack, always 0
             "T": 4, "t": 4  # custom type, corresponds to L (uint_32) from struct/rawutil, corresponds to a time, which will have special treatment
             }

def get_packet_size(format : str):
    """Find the size of the data packet

    Args:
        format (str): Data packet format

    Returns:
        _type_: The size of the data packet in bytes
    """
    packet_size = 0
    for char in format:
        packet_size += DATA_DICT[char]
    return packet_size