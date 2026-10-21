use serde_json::{json, Value};
use std::{io::{BufRead, BufReader, Write}, process::{Child, ChildStdin, Command, Stdio}, sync::{Arc, Mutex}};
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::sync::oneshot;

struct Bridge {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    pending: Arc<Mutex<std::collections::HashMap<u64, oneshot::Sender<Value>>>>,
    next_id: Mutex<u64>,
}

impl Bridge {
    fn start(app: &AppHandle) -> Result<Self, String> {
        let resource = app.path().resource_dir().map_err(|e| e.to_string())?;
        let base = if cfg!(debug_assertions) { std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..") } else { resource.join("engine") };
        // Windows releases carry a frozen Python bridge so users do not need
        // to install Python or configure PATH. Development keeps using Python.
        let bundled_name = format!("openrpa-bridge-{}{}", env!("CARGO_PKG_VERSION"), if cfg!(windows) { ".exe" } else { "" });
        let bundled_bridge = resource.join("engine").join(bundled_name);
        let bundled = !cfg!(debug_assertions) && bundled_bridge.is_file();
        let python = if bundled { bundled_bridge.to_string_lossy().into_owned() } else if let Ok(p) = std::env::var("OPENRPA_PYTHON") { p } else if cfg!(windows) { "python".into() } else { "python3".into() };
        let mut cmd = Command::new(&python);
        if !bundled { cmd.args(["-m", "openrpa.bridge"]); }
        // A console-subsystem Python/bridge executable otherwise opens a
        // terminal window when launched by the Windows GUI application. Its
        // stdin/stdout/stderr remain available through the explicit pipes.
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }
        cmd.current_dir(&base).env("PYTHONIOENCODING", "utf-8").env("PYTHONUNBUFFERED", "1").env("PYTHONNOUSERSITE", "1").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
        let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
        std::fs::create_dir_all(&data_dir).map_err(|e| format!("Cannot create application data directory: {e}"))?;
        cmd.env("OPENRPA_DATA_DIR", data_dir);
        for name in ["PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"] { cmd.env_remove(name); }
        let mut child = cmd.spawn().map_err(|e| format!("Cannot start workflow engine ({python}): {e}"))?;
        let stdin = child.stdin.take().ok_or("bridge stdin unavailable")?;
        let stdout = child.stdout.take().ok_or("bridge stdout unavailable")?;
        let stderr = child.stderr.take().ok_or("bridge stderr unavailable")?;
        std::thread::Builder::new().name("openrpa-bridge-stderr".into()).spawn(move || {
            // Drain child diagnostics so a noisy Python failure cannot fill the OS pipe and hang runs.
            for line in BufReader::new(stderr).lines().flatten() { eprintln!("[OpenRPA engine] {line}"); }
        }).map_err(|e| e.to_string())?;
        let pending: Arc<Mutex<std::collections::HashMap<u64, oneshot::Sender<Value>>>> = Arc::new(Mutex::new(std::collections::HashMap::new()));
        let p = pending.clone();
        let handle = app.clone();
        std::thread::Builder::new().name("openrpa-bridge-reader".into()).spawn(move || {
            for line in BufReader::new(stdout).lines().flatten() {
                if let Ok(value) = serde_json::from_str::<Value>(&line) {
                    if value.get("event").and_then(Value::as_str) == Some("run.event") { let _ = handle.emit("run-event", value["data"].clone()); continue; }
                    if let Some(id) = value.get("id").and_then(|v| v.as_u64()) { if let Some(tx) = p.lock().unwrap().remove(&id) { let _ = tx.send(value); } }
                }
            }
            for (_, tx) in p.lock().unwrap().drain() { let _ = tx.send(json!({"error":{"message":"Workflow engine process exited"}})); }
        }).map_err(|e| e.to_string())?;
        Ok(Self { child: Mutex::new(Some(child)), stdin: Mutex::new(Some(stdin)), pending, next_id: Mutex::new(1) })
    }
    async fn request(&self, method: &str, params: Value) -> Result<Value, String> {
        let id = { let mut n = self.next_id.lock().unwrap(); let id=*n; *n+=1; id };
        let (tx, rx)=oneshot::channel(); self.pending.lock().unwrap().insert(id, tx);
        let mut line=serde_json::to_vec(&json!({"id":id,"method":method,"params":params})).map_err(|e|e.to_string())?; line.push(b'\n');
        if let Err(e)=self.stdin.lock().unwrap().as_mut().ok_or("workflow engine is closed")?.write_all(&line) { self.pending.lock().unwrap().remove(&id); return Err(format!("Cannot write to workflow engine: {e}")); }
        let response=rx.await.map_err(|e|e.to_string())?;
        if let Some(error)=response.get("error") { return Err(error.get("message").and_then(Value::as_str).unwrap_or("workflow engine error").to_owned()); }
        response.get("result").cloned().ok_or("workflow engine returned no result".to_owned())
    }
}
impl Drop for Bridge { fn drop(&mut self) { if let Some(mut child)=self.child.lock().ok().and_then(|mut c|c.take()) { let _=child.kill(); let _=child.wait(); } } }

#[tauri::command] async fn bridge_request(bridge: State<'_, Bridge>, method: String, params: Value) -> Result<Value,String> { bridge.request(&method,params).await }

pub fn run() {
    tauri::Builder::default().plugin(tauri_plugin_dialog::init()).setup(|app| { let bridge=Bridge::start(app.handle()).map_err(std::io::Error::other)?; app.manage(bridge); Ok(()) }).invoke_handler(tauri::generate_handler![bridge_request]).run(tauri::generate_context!()).expect("error while running Open RPA Studio");
}


