use std::cmp;
use std::error;
use std::fmt;
use std::io::{BufReader, BufRead};
use std::io;
use std::path::Path;
use std::fs::{File, metadata};

const HEADER_MAX_SIZE: usize = 2*1024;     // This refers to the JSON file header. This value comes directly from the tag C++ code.

#[derive(Debug, Clone)]
pub enum HeaderError {
    HeaderMissing,
    ReadLineExceedsSize(usize),
}

impl error::Error for HeaderError {}

impl fmt::Display for HeaderError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match *self {
            HeaderError::HeaderMissing => write!(f, "Cannot find line to use as the header"),
            HeaderError::ReadLineExceedsSize(val) => write!(f, "First line of file ({val} characters) exceeds the maximum possible length of the header ({HEADER_MAX_SIZE} characters)"),
        }
    }
}

pub fn import_file(filename: &str) -> Result<BufReader<File>, io::Error> {
    let path = Path::new(filename);
    println!("Path to file is: {}", path.display());

    let file = File::open(&path)?;

    return Ok(BufReader::new(file))
}

pub fn read_file_header(reader: &mut BufReader<File>) -> Result<String, HeaderError> {
    let mut line: String = String::new();
    let len: usize = reader.read_line(&mut line)
        .map_err(|_| {
            HeaderError::HeaderMissing
        })?;

    match len {
        0..=HEADER_MAX_SIZE => Ok(line),
        _ => Err(HeaderError::ReadLineExceedsSize(len))
    }
}

pub fn get_file_size(filename: &str) -> Result<u64, io::Error> {
    let file_metadata = metadata(filename)?;

    return Ok(file_metadata.len())
}

#[derive(Debug, Eq, PartialEq, Ord, PartialOrd)]
pub struct DeviceFormat {
    id: u8,
    data_format: Vec<char>,
    header_format: Vec<char>,
}

#[derive(Debug, Eq, PartialEq)]
pub struct RawBuffer {
    id: u8,
    time: u32,
    data: Vec<u8>,
}

impl Ord for RawBuffer {
    fn cmp(&self, other: &Self) -> cmp::Ordering {  
        (self.time).cmp(&other.time)
    }
}

impl PartialOrd for RawBuffer {
    fn partial_cmp(&self, other: &Self) -> Option<cmp::Ordering> {
        Some(self.cmp(other))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn buffer_lt() {
        let buffer1 = RawBuffer {
            id: 1,
            time: 10,
            data: [0, 1, 2, 3].to_vec(),
        };

        let buffer2 = RawBuffer {
            id: 1,
            time: 15,
            data: [0, 1, 2, 3].to_vec(),
        };

        assert!(buffer1 <= buffer2);
    }

    #[test]
    fn buffer_gt() {
        let buffer1 = RawBuffer {
            id: 1,
            time: 10,
            data: [0, 1, 2, 3].to_vec(),
        };

        let buffer2 = RawBuffer {
            id: 1,
            time: 15,
            data: [0, 1, 2, 3].to_vec(),
        };

        assert!(buffer2 >= buffer1)
    }

    #[test]
    fn buffer_eq() {
        let buffer1 = RawBuffer {
            id: 1,
            time: 10,
            data: [0, 1, 2, 3].to_vec(),
        };

        let buffer2 = RawBuffer {
            id: 1,
            time: 10,
            data: [0, 1, 2, 3].to_vec(),
        };

        assert_eq!(buffer1, buffer2);
    }

    #[test]
    fn buffer_neq() {
        let buffer1 = RawBuffer {
            id: 1,
            time: 10,
            data: [0, 1, 2, 3].to_vec(),
        };

        let buffer2 = RawBuffer {
            id: 1,
            time: 15,
            data: [0, 1, 2, 3].to_vec(),
        };

        assert!(buffer1 != buffer2);
    }
}