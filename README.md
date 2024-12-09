# MTAG2 Deserializer
## Developer Install
Once pulled from GitHub, go to the root folder structure, and create the development environment with
`python 3 -m venv env`. Once this command runs, there will be an `env/` folder in the root directory. We need to activate using `source env/bin/activate` for Unix-based systems, and `source Scripts/env/activate` for Windows based systems. Now, we need to install the code dependencies for running the program. First, we can update pip with `pip install --upgrade pip`, and then install build with `pip install -U build`. With this, we are now ready to install the dependencies with `pip intall -e .` (see [Local Project Installs][editablesite]). This gives us access to running the source code. To install what is needed for development, additionally run `pip install pytest pytest-cov pytest-benchmark`.

To check if everything is working correctly, run pytest-v, and all the unit-tests should pass.

[editablesite]: https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs (Python: Editable Installs)

## Deserializing
From the root folder (the one containing the `env/`, `tests/`, and `src/` folder) we can run:
```
python src/animal_tag/serializer/deserializer.py [-H external_header_file] filename savefilename
```
We need to pass the filename that we want to deserialize, the filename to which we are saving (ending in .h5), and then optionally pass a `-H` flag (`-h` is for help) to give the external header file that we will use for deserializing the file if the file does not come with a header.

Example (if run from the root folder):
```
python src/animal_tag/serializer/deserializer.py ./tests/Data/MTAG2-Hua-LS.bin ./tests/Data/Test.h5 -H ./tests/Data/test_header.txt
```

Example (if run from the folder containing deserializer)
```
python -m deserializer [-H path_header_file] path_filename path_savefile
```
Note the `-m` flag in this example.

# Serialization Format
This defines the serialization format for the new animal tags. This will ensure a consistent interface across the board.

## Data Buffer
### Overall Structure
```
      HEADER                    DATA
[ __ ________ ____  | -------------------------- ]
  ID   TIME   NULL      Formatted Sampled Data
^                   ^                            ^
| -- Header Size -- |  ------ Data Size ------   |
|                                                |
| ---------------  Buffer Size  ---------------  |

```
  * __ID__: single byte, uniquely identifies the sampling device from which the data is from
  * __Time__: unsigned integer (uint_32), the time at which the entire buffer was written to the SD card, useful for both error checking (buffer time should monotonically increase, with no/limited jitter in timings, excluding overflows)
  * __Null__: Marks the end of the header, serves as a separator between header and data, useful to look for when looking at the binary data
  * __Data__: the raw data corresponding to this buffer. Note that data can be multiple samples long (and usually is in the hundreds if not thousands of samples). SD cards prefer powers of 2 sized buffers. A 6 byte header for an 8192 byte buffer will mean 8186 bytes for data storage. Important for hydrophone which is an int16, which will fit an even 4093 times into the data portion of the buffer.

### Data Format
The formatting of the data will be given in a format similar to Python's ```rawutils```/```struct``` library, using `X` for null bytes, and `T` being overloaded with `I` for a uint32 that is used for time.
Additionally, little endianness is assumed, and so the `<`, `>`, `@`, `=`, `!` characters are not needed for the specification.
(For reference, [rawutil][rawsite] and [struct][structsite] documentation.)
This means that the allowed characters for specifying the data format are:

[rawsite]: https://pypi.org/project/rawutil/ (Python: rawutil)
[structsite]: https://docs.python.org/3/library/struct.html (Python: struct)

| Character |  Type  | Size | Description   |
| :-------: |  :--:  | :--: | :---------    |
|     b     |  int8  |   1  | 8 bits signed  int  |
|     B     | uint8  |   1  | 8 bits unsigned int |
|     h     |  int16 |   2  | 16 bit signed int   |
|     H     | uint16 |   2  | 16 bit unsigned int |
|     u     |  int24 |   3  | 24 bit signed int (two's complement) |
|     U     | uint24 |   3  | 24 bit unsigned int (two's complement) |
|     i     |  int32 |   4  | 32 bit signed int |
|     I     | uint32 |   4  | 32 bit unsigned int |
|     f     | float  |   4  | IEEE 754 single-precision |
|     d     | double |   8  | IEEE 754 double-precision |
|     F     |  quad  |  16  | IEEE 754 quadruple-precision |
|     c     |  char  |   1  | Character (1-byte bytes object) |
|     X     |  null  |   1  | Null byte (0x00) at the location/ignore byte |
|     T     | uint32 |   4  | Time of sampling as uint32 |

The data format describes the data taken from one instance of sampling of any device.
Some examples of data formats:

  * __BTX__: format of a header, as an ID byte, time, and a null byte
  * __H__: format of a single channel hydrophone, as one uint16
  * __Thhhhhhhhh__: Format for the IMU, time as a uint32 followed by 9 int16 numbers (3 for the accelerometer, 3 for the gyroscope, 3 for the magnetometer)
  * __TBBBuuuuuuuu__: Format for the EEG, time as a uint32, 3 byte header for the eeg data, followed by 8 channels of EEG data as an int24
  * __TffH__: Format for ancillary data, time (uint32), followed by a float for the pressure, float for the temperature, and a count for the number of impeller spin counts

## Header
The goal of the header is to provide an in-file representation of how to parse the file.
This allows for a much more generalized deserializer that will see reuse, rather than each new tag necessitating its own deserializer, as long as each tag maintains these conventions.

```
{"metadata": {"name": "Gabriel", "species": "Homo sapiens", "date": "1995-10-26 14:15:00"}, "buffers": {"test": {"id": 1, "time": 4093, "header": "BTX", "split_channel": false, "data": "H", "buffer_size": 8192, "channel_names": ["ch0"]}}}
```

Which with line seperators would look like:

```
{"metadata":    { "name": "Gabriel",
                  "species": "Homo sapiens",
                  "date": "1995-10-26 14:15:00"
                },
 "buffers":     {
                "test": {"id": 1,
                         "time": 4093,
                         "header": "BTX",
                         "split_channel": false,
                         "data": "H",
                         "buffer_size": 8192,
                         "channel_names": ["ch0"]
                         }
                }
}
```

## Header Structure
```
{"metadata": JSONObject, "buffers": JSONObject}
```
The header contains two main parts:
  * __metadata__: the experiment metadata, which can be of variable length.
  The most common is is going to be name, species, and a date.
  This frees up the filename for more human parsable names, should the default datetime filename not be wished.
  This also ensures the metadata for each run is stored with the original data
  * __buffers__: this defines the parsing scheme for each buffer of data. From this data, the reconstruction can be fully identified. The name of the device will be followed by a JSON with the following:
    * __id__: The ID of the buffer
    * __time__: Time the buffer was filled and sent to the SD card for saving
    * __header__: format for the header
    * __data__: format of the data
    * __split_channel__: boolean, either True or False. If True, each data channel will be split into a seperate groups in the final h5 file. If false, all the channels will be placed into a seperate file. NOT CURRENTLY IMPLEMENTED.
    * __channel_names__: The name of each channel of data
    * __buffer_size__: The overall buffer size, i.e. size of the header + size of the data

For example, take the previous header.
We know that the header format is `BTX` (6 bytes), and the buffer size is 8192 bytes.
We then know the size of data is 8186 bytes (8186 + 6 = 8192).
This means that there are 4093 (8186/2, since `H` takes up 2 bytes) unique samples inside of the data buffer.

Let's instead take the same buffer with header format `BTX`, data format `H`, but instead make the buffer_size 8.
This means that the resulting buffer will only have 1 sample associated with this header (`buffer_size` is 8, header size is 6, which leaves 2 bytes, which is incidentally the size of `H`).

If `buffer_size` were to be 9, it would be exactly the same case as previous, except that there would be a null byte following the one sample of data. __IMPORTANTLY: BUFFERS CAN HAVE LEFTOVER BYTES THAT DO NOT STORE DATA, AND ARE MERELY THERE TO KEEP BUFFER WRITES POWERS OF 2.__ Should a buffer of some size not be able to fit an integer multiple of the data format, the last remaining bytes will be null. These null bytes will be ignored during deserialization.

# Python Notes
One of the packags we are using here is pytest-benchmark, which allows for benchmarking specific tests to figure out speed of functions.
We can run these checks by running `pytest -v`, which is a verbose output of pytest.
This will run both all the unit tests, and also the benchmarks.
Benchmarks can be easily identified in the code by taking a look at any functions beginning with `test_` that have `benchmark` as a function input. 

## Python Profiling
`pytest --profile` will run function profiling to see where the time is being spent for running the functions. Useful for identifying bottlenecks in running the tag functions.

## Python Benchmarking:
  * starmap pop is faster than using list comprehension for larger numbers of pops (>=512) from a deque. For smaller numbers of pops, array comprehension is faster (see `test_popping.py`)

## Python Test Profiling Results
Might have to rewrite the tests to pre-make the files so that they exist and are already written, otherwise we will waste time remaking files that are quite costly to create each test run... On the other hand, only takes about 5 min.
```
Profiling (from /home/gabriel/Documents/mtag-deserializinator-inator/tests/prof/combined.prof):
Mon Oct 28 21:56:50 2024    /home/gabriel/Documents/mtag-deserializinator-inator/tests/prof/combined.prof

         301825221 function calls (301825049 primitive calls) in 492.455 seconds

   Ordered by: cumulative time
   List reduced from 724 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      4/3    0.000    0.000  492.452  164.151 runner.py:226(call_and_report)
    21/11    0.000    0.000  492.452   44.768 _hooks.py:498(__call__)
    20/11    0.000    0.000  492.451   44.768 _manager.py:111(_hookexec)
    20/11    0.000    0.000  492.451   44.768 _callers.py:53(_multicall)
      4/3    0.000    0.000  492.451  164.150 runner.py:319(from_call)
      4/3    0.000    0.000  492.451  164.150 runner.py:242(<lambda>)
        1    0.000    0.000  492.443  492.443 runner.py:158(pytest_runtest_setup)
        1    0.000    0.000  492.443  492.443 runner.py:498(setup)
        1    0.000    0.000  492.443  492.443 python.py:1629(setup)
        1    0.000    0.000  492.443  492.443 fixtures.py:692(_fillfixtures)
      6/3    0.000    0.000  492.443  164.148 fixtures.py:509(getfixturevalue)
      9/3    0.000    0.000  492.443  164.148 fixtures.py:548(_get_active_fixturedef)
      2/1    0.000    0.000  492.443  492.443 fixtures.py:1036(execute)
        2    0.000    0.000  492.443  246.221 fixtures.py:1128(pytest_fixture_setup)
        2    0.000    0.000  492.443  246.221 fixtures.py:881(call_fixture_func)
        1    0.000    0.000  492.443  492.443 test_creation.py:47(write_bin_file)
        1   47.786   47.786  492.440  492.440 buffer_generator.py:112(write_file)
     4096   62.808    0.015  444.586    0.109 buffer_generator.py:62(create_buffer)
 16764928  219.399    0.000  347.108    0.000 function_base.py:25(linspace)
 16764928   71.974    0.000   71.974    0.000 {built-in method numpy.arange}
```