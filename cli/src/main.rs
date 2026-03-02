mod commands;
mod connection;
mod output;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();

    let (flags, command) = match commands::parse_args(args) {
        Ok(v) => v,
        Err(msg) => {
            eprintln!("{msg}");
            std::process::exit(1);
        }
    };

    let response = match connection::send_command(&flags, &command) {
        Ok(v) => v,
        Err(msg) => {
            eprintln!("Error: {msg}");
            std::process::exit(1);
        }
    };

    output::print_response(&response, flags.json_output);
}
