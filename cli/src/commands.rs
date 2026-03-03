use serde_json::{json, Value};

/// Global flags extracted before subcommand parsing.
pub struct GlobalFlags {
    pub session: String,
    pub headed: bool,
    pub timeout: u32,
    pub json_output: bool,
    pub persistent: Option<String>,
}

impl Default for GlobalFlags {
    fn default() -> Self {
        Self {
            session: "default".into(),
            headed: false,
            timeout: 1800,
            json_output: false,
            persistent: None,
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
            "--persistent" => {
                i += 1;
                flags.persistent = Some(args.get(i).ok_or("--persistent requires a path")?.clone());
            }
            _ => rest.push(args[i].clone()),
        }
        i += 1;
    }

    if rest.is_empty() {
        return Err(USAGE.to_string());
    }

    let action = rest[0].as_str();
    let cmd = match action {
        // --- Navigation ---
        "open" => {
            let url = rest.get(1).ok_or("Usage: camoufox-cli open <url>")?;
            json!({"id": "r1", "action": "open", "params": {"url": url}})
        }
        "back" => json!({"id": "r1", "action": "back", "params": {}}),
        "forward" => json!({"id": "r1", "action": "forward", "params": {}}),
        "reload" => json!({"id": "r1", "action": "reload", "params": {}}),
        "url" => json!({"id": "r1", "action": "url", "params": {}}),
        "title" => json!({"id": "r1", "action": "title", "params": {}}),
        "close" => {
            let all = rest.iter().any(|a| a == "--all");
            json!({"id": "r1", "action": "close", "params": {"all": all}})
        }

        // --- Snapshot ---
        "snapshot" => {
            let interactive = rest.iter().any(|a| a == "-i");
            let selector = rest.iter().position(|a| a == "-s")
                .and_then(|i| rest.get(i + 1))
                .cloned();
            let mut params = json!({"interactive": interactive});
            if let Some(sel) = selector {
                params["selector"] = json!(sel);
            }
            json!({"id": "r1", "action": "snapshot", "params": params})
        }

        // --- Interaction ---
        "click" => {
            let ref_str = rest.get(1).ok_or("Usage: camoufox-cli click @e1")?;
            json!({"id": "r1", "action": "click", "params": {"ref": ref_str}})
        }
        "fill" => {
            let ref_str = rest.get(1).ok_or("Usage: camoufox-cli fill @e1 \"text\"")?;
            let text = rest.get(2).ok_or("Usage: camoufox-cli fill @e1 \"text\"")?;
            json!({"id": "r1", "action": "fill", "params": {"ref": ref_str, "text": text}})
        }
        "type" => {
            let ref_str = rest.get(1).ok_or("Usage: camoufox-cli type @e1 \"text\"")?;
            let text = rest.get(2).ok_or("Usage: camoufox-cli type @e1 \"text\"")?;
            json!({"id": "r1", "action": "type", "params": {"ref": ref_str, "text": text}})
        }
        "select" => {
            let ref_str = rest.get(1).ok_or("Usage: camoufox-cli select @e1 \"option\"")?;
            let value = rest.get(2).ok_or("Usage: camoufox-cli select @e1 \"option\"")?;
            json!({"id": "r1", "action": "select", "params": {"ref": ref_str, "value": value}})
        }
        "check" => {
            let ref_str = rest.get(1).ok_or("Usage: camoufox-cli check @e1")?;
            json!({"id": "r1", "action": "check", "params": {"ref": ref_str}})
        }
        "hover" => {
            let ref_str = rest.get(1).ok_or("Usage: camoufox-cli hover @e1")?;
            json!({"id": "r1", "action": "hover", "params": {"ref": ref_str}})
        }
        "press" => {
            let key = rest.get(1).ok_or("Usage: camoufox-cli press Enter")?;
            json!({"id": "r1", "action": "press", "params": {"key": key}})
        }

        // --- Data extraction ---
        "text" => {
            let target = rest.get(1).ok_or("Usage: camoufox-cli text @e1 | camoufox-cli text body")?;
            json!({"id": "r1", "action": "text", "params": {"target": target}})
        }
        "eval" => {
            let expr = rest.get(1).ok_or("Usage: camoufox-cli eval \"document.title\"")?;
            json!({"id": "r1", "action": "eval", "params": {"expression": expr}})
        }
        "screenshot" => {
            let mut params = json!({});
            let mut i = 1;
            while i < rest.len() {
                match rest[i].as_str() {
                    "--full" => { params["full_page"] = json!(true); }
                    arg => { params["path"] = json!(arg); }
                }
                i += 1;
            }
            json!({"id": "r1", "action": "screenshot", "params": params})
        }
        "pdf" => {
            let path = rest.get(1).ok_or("Usage: camoufox-cli pdf output.pdf")?;
            json!({"id": "r1", "action": "pdf", "params": {"path": path}})
        }

        // --- Scroll & Wait ---
        "scroll" => {
            let direction = rest.get(1).ok_or("Usage: camoufox-cli scroll down [px]")?;
            let amount: u32 = rest.get(2)
                .and_then(|v| v.parse().ok())
                .unwrap_or(500);
            json!({"id": "r1", "action": "scroll", "params": {"direction": direction, "amount": amount}})
        }
        "wait" => {
            let target = rest.get(1).ok_or("Usage: camoufox-cli wait @e1 | camoufox-cli wait 2000 | camoufox-cli wait --url \"pattern\"")?;
            if target == "--url" {
                let pattern = rest.get(2).ok_or("Usage: camoufox-cli wait --url \"*/dashboard\"")?;
                json!({"id": "r1", "action": "wait", "params": {"url": pattern}})
            } else if target.starts_with('@') || target.chars().next().map_or(false, |c| c.is_alphabetic()) {
                // ref like @e1 or CSS selector
                if target.starts_with('@') {
                    json!({"id": "r1", "action": "wait", "params": {"ref": target}})
                } else {
                    json!({"id": "r1", "action": "wait", "params": {"selector": target}})
                }
            } else {
                // numeric milliseconds
                let ms: u32 = target.parse().map_err(|_| format!("Invalid wait target: {target}"))?;
                json!({"id": "r1", "action": "wait", "params": {"ms": ms}})
            }
        }

        // --- Tab management ---
        "tabs" => json!({"id": "r1", "action": "tabs", "params": {}}),
        "switch" => {
            let index = rest.get(1).ok_or("Usage: camoufox-cli switch <tab-index>")?;
            let idx: u32 = index.parse().map_err(|_| "Tab index must be a number")?;
            json!({"id": "r1", "action": "switch", "params": {"index": idx}})
        }
        "close-tab" => json!({"id": "r1", "action": "close-tab", "params": {}}),

        // --- Session & Cookies ---
        "sessions" => json!({"id": "r1", "action": "sessions", "params": {}}),
        "cookies" => {
            match rest.get(1).map(|s| s.as_str()) {
                Some("import") => {
                    let path = rest.get(2).ok_or("Usage: camoufox-cli cookies import file.json")?;
                    json!({"id": "r1", "action": "cookies", "params": {"op": "import", "path": path}})
                }
                Some("export") => {
                    let path = rest.get(2).ok_or("Usage: camoufox-cli cookies export file.json")?;
                    json!({"id": "r1", "action": "cookies", "params": {"op": "export", "path": path}})
                }
                _ => json!({"id": "r1", "action": "cookies", "params": {"op": "list"}}),
            }
        }

        _ => return Err(format!("Unknown command: {action}\n{USAGE}")),
    };

    Ok((flags, cmd))
}

const USAGE: &str = "\
Usage: camoufox-cli [flags] <command> [args]

Navigation:
  open <url>              Navigate to URL
  back                    Go back
  forward                 Go forward
  reload                  Reload page
  url                     Print current URL
  title                   Print page title
  close [--all]           Close browser and daemon (--all: all sessions)

Snapshot:
  snapshot [-i] [-s sel]  Aria tree (-i interactive, -s scoped)

Interaction:
  click @ref              Click element
  fill @ref \"text\"        Clear + type into input
  type @ref \"text\"        Type without clearing
  select @ref \"option\"    Select dropdown option
  check @ref              Toggle checkbox
  hover @ref              Hover over element
  press <key>             Press key (e.g. Enter, Control+a)

Data:
  text @ref|selector      Get text content
  eval \"js expression\"    Execute JavaScript
  screenshot [--full] [f] Screenshot to file or stdout
  pdf <file>              Save page as PDF

Scroll & Wait:
  scroll <dir> [px]       Scroll up/down (default 500px)
  wait <ms|@ref|--url p>  Wait for time/element/URL

Tabs:
  tabs                    List open tabs
  switch <index>          Switch to tab
  close-tab               Close current tab

Session:
  sessions                List active sessions
  cookies [import|export] Manage cookies

Flags:
  --session <name>     Session name (default: \"default\")
  --headed             Show browser window
  --timeout <secs>     Daemon idle timeout (default: 1800)
  --json               Output as JSON
  --persistent <path>  Use persistent browser profile";
