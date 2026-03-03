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

    let action = command.get("action").and_then(|v| v.as_str()).unwrap_or("");

    // Commands that need client-side handling
    match action {
        "sessions" => {
            let sessions = connection::list_sessions();
            if flags.json_output {
                println!("{}", serde_json::to_string_pretty(&sessions).unwrap());
            } else if sessions.is_empty() {
                println!("No active sessions.");
            } else {
                for s in &sessions {
                    println!("{s}");
                }
            }
            return;
        }
        "close" => {
            let all = command
                .get("params")
                .and_then(|p| p.get("all"))
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            if all {
                let sessions = connection::list_sessions();
                if sessions.is_empty() {
                    println!("No active sessions.");
                    return;
                }
                let close_cmd =
                    serde_json::json!({"id": "r1", "action": "close", "params": {}});
                for session in &sessions {
                    let mut session_flags = commands::GlobalFlags::default();
                    session_flags.session = session.clone();
                    if let Err(e) = connection::send_command(&session_flags, &close_cmd) {
                        eprintln!("Failed to close session {session}: {e}");
                    }
                }
                return;
            }
        }
        _ => {}
    }

    let response = match connection::send_command(&flags, &command) {
        Ok(v) => v,
        Err(msg) => {
            eprintln!("Error: {msg}");
            std::process::exit(1);
        }
    };

    output::print_response(&response, flags.json_output);
}
