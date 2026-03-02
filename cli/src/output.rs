use serde_json::Value;

/// Print the daemon response in human-readable or JSON format.
pub fn print_response(response: &Value, json_mode: bool) {
    if json_mode {
        println!("{}", serde_json::to_string_pretty(response).unwrap());
        return;
    }

    let success = response.get("success").and_then(|v| v.as_bool()).unwrap_or(false);

    if !success {
        let error = response
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("Unknown error");
        eprintln!("Error: {error}");
        std::process::exit(1);
    }

    // Print data fields
    if let Some(data) = response.get("data") {
        if let Some(snapshot) = data.get("snapshot").and_then(|v| v.as_str()) {
            println!("{snapshot}");
        } else if let Some(url) = data.get("url").and_then(|v| v.as_str()) {
            let title = data.get("title").and_then(|v| v.as_str()).unwrap_or("");
            println!("{title}");
            println!("{url}");
        } else if data.get("closed").is_some() {
            // close command - silent success
        } else {
            // Fallback: print the JSON data
            println!("{}", serde_json::to_string_pretty(data).unwrap());
        }
    }
}
