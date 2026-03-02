use serde_json::{json, Value};

/// Global flags extracted before subcommand parsing.
pub struct GlobalFlags {
    pub session: String,
    pub headed: bool,
    pub timeout: u32,
    pub json_output: bool,
}

impl Default for GlobalFlags {
    fn default() -> Self {
        Self {
            session: "default".into(),
            headed: false,
            timeout: 1800,
            json_output: false,
        }
    }
}

/// Parse CLI args into (GlobalFlags, JSON command Value).
/// Returns None if args are invalid / help requested.
pub fn parse_args(args: Vec<String>) -> Result<(GlobalFlags, Value), String> {
    let mut flags = GlobalFlags::default();
    let mut rest: Vec<String> = Vec::new();

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--session" => {
                i += 1;
                flags.session = args.get(i).ok_or("--session requires a value")?.clone();
            }
            "--headed" => flags.headed = true,
            "--timeout" => {
                i += 1;
                flags.timeout = args
                    .get(i)
                    .ok_or("--timeout requires a value")?
                    .parse()
                    .map_err(|_| "--timeout must be a number")?;
            }
            "--json" => flags.json_output = true,
            _ => rest.push(args[i].clone()),
        }
        i += 1;
    }

    if rest.is_empty() {
        return Err(USAGE.to_string());
    }

    let action = rest[0].as_str();
    let cmd = match action {
        "open" => {
            let url = rest.get(1).ok_or("Usage: cfox open <url>")?;
            json!({"id": "r1", "action": "open", "params": {"url": url}})
        }
        "snapshot" => {
            let interactive = rest.iter().any(|a| a == "-i");
            json!({"id": "r1", "action": "snapshot", "params": {"interactive": interactive}})
        }
        "click" => {
            let ref_str = rest.get(1).ok_or("Usage: cfox click @e1")?;
            json!({"id": "r1", "action": "click", "params": {"ref": ref_str}})
        }
        "fill" => {
            let ref_str = rest.get(1).ok_or("Usage: cfox fill @e1 \"text\"")?;
            let text = rest.get(2).ok_or("Usage: cfox fill @e1 \"text\"")?;
            json!({"id": "r1", "action": "fill", "params": {"ref": ref_str, "text": text}})
        }
        "close" => {
            json!({"id": "r1", "action": "close", "params": {}})
        }
        _ => return Err(format!("Unknown command: {action}\n{USAGE}")),
    };

    Ok((flags, cmd))
}

const USAGE: &str = "\
Usage: cfox [flags] <command> [args]

Commands:
  open <url>           Navigate to URL
  snapshot [-i]        Aria tree snapshot (-i for interactive only)
  click @e1            Click element by ref
  fill @e1 \"text\"     Fill input by ref
  close                Close browser and daemon

Flags:
  --session <name>     Session name (default: \"default\")
  --headed             Show browser window
  --timeout <secs>     Daemon idle timeout (default: 1800)
  --json               Output as JSON";
