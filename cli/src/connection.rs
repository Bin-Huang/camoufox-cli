use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;
use std::thread;
use std::time::Duration;

use serde_json::Value;

use crate::commands::GlobalFlags;

/// Get the socket path for a session.
pub fn get_socket_path(session: &str) -> PathBuf {
    PathBuf::from(format!("/tmp/camoufox-cli-{session}.sock"))
}

/// Ensure daemon is running, connect, send command, return response.
pub fn send_command(flags: &GlobalFlags, command: &Value) -> Result<Value, String> {
    let socket_path = get_socket_path(&flags.session);

    // If socket doesn't exist, spawn daemon
    if !socket_path.exists() {
        spawn_daemon(flags)?;
    }

    // Retry loop: connect and send
    let max_retries = 5;
    let mut last_err = String::new();

    for attempt in 1..=max_retries {
        match try_send(&socket_path, command) {
            Ok(resp) => return Ok(resp),
            Err(e) => {
                last_err = e;
                if attempt < max_retries {
                    let delay = Duration::from_millis(200 * attempt as u64);
                    thread::sleep(delay);
                }
            }
        }
    }

    Err(format!("Failed to connect to daemon after {max_retries} attempts: {last_err}"))
}

fn try_send(socket_path: &PathBuf, command: &Value) -> Result<Value, String> {
    let mut stream =
        UnixStream::connect(socket_path).map_err(|e| format!("Connect failed: {e}"))?;

    let payload = serde_json::to_string(command).unwrap() + "\n";
    stream
        .write_all(payload.as_bytes())
        .map_err(|e| format!("Write failed: {e}"))?;

    // Shutdown write side so server knows we're done
    stream
        .shutdown(std::net::Shutdown::Write)
        .map_err(|e| format!("Shutdown write: {e}"))?;

    let mut buf = Vec::new();
    stream
        .read_to_end(&mut buf)
        .map_err(|e| format!("Read failed: {e}"))?;

    let text = String::from_utf8_lossy(&buf);
    serde_json::from_str(text.trim()).map_err(|e| format!("Invalid response JSON: {e}"))
}

fn spawn_daemon(flags: &GlobalFlags) -> Result<(), String> {
    let python = find_python()?;

    let mut cmd = Command::new(&python);
    cmd.args(["-m", "camoufox_cli"])
        .arg("--session")
        .arg(&flags.session)
        .arg("--timeout")
        .arg(flags.timeout.to_string());

    if flags.headed {
        cmd.arg("--headed");
    }

    if let Some(ref path) = flags.persistent {
        cmd.arg("--persistent").arg(path);
    }

    // Set PYTHONPATH to include project src/
    if let Ok(exe) = std::env::current_exe() {
        if let Some(project_root) = exe.parent().and_then(|p| p.parent()).and_then(|p| p.parent()).and_then(|p| p.parent()) {
            let src_path = project_root.join("src");
            if src_path.exists() {
                let existing = std::env::var("PYTHONPATH").unwrap_or_default();
                let new_path = if existing.is_empty() {
                    src_path.to_string_lossy().to_string()
                } else {
                    format!("{}:{existing}", src_path.to_string_lossy())
                };
                cmd.env("PYTHONPATH", new_path);
            }
        }
    }

    // Detach: redirect stdio, use setsid via pre_exec
    cmd.stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped());

    unsafe {
        cmd.pre_exec(|| {
            libc::setsid();
            Ok(())
        });
    }

    cmd.spawn().map_err(|e| format!("Failed to spawn daemon: {e}"))?;

    // Wait for socket to appear
    let socket_path = get_socket_path(&flags.session);
    for _ in 0..50 {
        if socket_path.exists() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(100));
    }

    Err("Daemon did not start within 5 seconds".to_string())
}

/// List active sessions by scanning /tmp/camoufox-cli-*.sock files.
pub fn list_sessions() -> Vec<String> {
    let mut sessions = Vec::new();
    if let Ok(entries) = std::fs::read_dir("/tmp") {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if let Some(session) = name.strip_prefix("camoufox-cli-").and_then(|s| s.strip_suffix(".sock")) {
                sessions.push(session.to_string());
            }
        }
    }
    sessions.sort();
    sessions
}

fn find_python() -> Result<String, String> {
    // Try python3 first, then python
    for name in &["python3", "python"] {
        if let Ok(output) = Command::new(name).arg("--version").output() {
            if output.status.success() {
                return Ok(name.to_string());
            }
        }
    }
    Err("Python 3 not found. Install Python 3.10+.".to_string())
}
