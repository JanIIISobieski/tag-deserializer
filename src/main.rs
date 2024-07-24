use clap::Parser;
use serde_json::Value;
use std::process;
use mtag_deserializinator_inator::{import_file, get_file_size, read_file_header};

/// Program to parse and correct the binary output data of the MTAG 2.0 and related tags
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
pub struct Args {
    /// The path and name of the file to parse
    #[arg(short, long)]
    source: String,

    /// The path and the file of the h5 py file to write
    #[arg(short, long)]
    destination: String,
}

fn main() {
    let args = Args::parse();
    println!("{:#?}", args);

    let file_size = get_file_size(&args.source)
        .unwrap_or_else(|err| {
           println!("Could not get file size: {err}");
           process::exit(0); 
        });
    
    println!("File size: {file_size} bytes");

    let mut reader = import_file(&args.source)
        .unwrap_or_else(|err| {
            println!("Could not open the file: {err}");
            process::exit(1);
        });

    let line = read_file_header(&mut reader)
        .unwrap_or_else(|err| {
            println!("Could not read header: {err}");
            process::exit(2);
        });

    println!("{}", &line);

    let parsed_header: Value = serde_json::from_str(&line)
        .unwrap_or_else(|err|{
            println!("Failed to parse header: {err}");
            process::exit(3);
        });
    
    println!("{:#?}", parsed_header);

    for (key, value) in parsed_header["data"].as_object().unwrap() {
        println!("{:#?}", key);
        println!("{:#?}", value);
    }
}
