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

    if let Some(data) = response.get("data") {
        // Single-value responses: snapshot, text, url, title, eval result
        if let Some(v) = data.get("snapshot").and_then(|v| v.as_str()) {
            println!("{v}");
        } else if let Some(v) = data.get("text").and_then(|v| v.as_str()) {
            println!("{v}");
        } else if let Some(v) = data.get("result") {
            // eval result — could be any JSON type
            match v {
                Value::String(s) => println!("{s}"),
                Value::Null => println!("null"),
                _ => println!("{v}"),
            }
        } else if data.get("closed").is_some() {
            // silent success
        } else if let Some(url) = data.get("url").and_then(|v| v.as_str()) {
            if let Some(title) = data.get("title").and_then(|v| v.as_str()) {
                println!("{title}");
            }
            println!("{url}");
        } else if let Some(title) = data.get("title").and_then(|v| v.as_str()) {
            println!("{title}");
        } else if data.as_object().map_or(false, |o| o.is_empty()) {
            // empty data = silent success (back, forward, scroll, etc.)
        } else {
            println!("{}", serde_json::to_string_pretty(data).unwrap());
        }
    }
}
