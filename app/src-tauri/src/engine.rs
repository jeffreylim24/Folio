//! Lifecycle of the Python engine sidecar: spawn, readiness, restart, shutdown.

use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use rand::RngExt;
use serde::Serialize;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tokio::sync::watch;

const READY_PREFIX: &str = "FOLIO_ENGINE_READY port=";
pub const READY_TIMEOUT: Duration = Duration::from_secs(20);

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineInfo {
    pub port: u16,
    pub token: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Status {
    Starting,
    Ready(EngineInfo),
    Failed(String),
}

/// Parses `FOLIO_ENGINE_READY port=<n>` and returns the port.
pub fn parse_ready_line(line: &str) -> Option<u16> {
    line.trim().strip_prefix(READY_PREFIX)?.trim().parse().ok()
}

/// Splits chunks of process output into complete lines, buffering partials.
#[derive(Default)]
pub struct LineBuffer {
    pending: Vec<u8>,
}

impl LineBuffer {
    pub fn push(&mut self, chunk: &[u8]) -> Vec<String> {
        self.pending.extend_from_slice(chunk);
        let mut lines = Vec::new();
        while let Some(i) = self.pending.iter().position(|&b| b == b'\n') {
            let raw: Vec<u8> = self.pending.drain(..=i).collect();
            lines.push(String::from_utf8_lossy(&raw).trim_end().to_string());
        }
        lines
    }
}

fn generate_token() -> String {
    let bytes: [u8; 32] = rand::rng().random();
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Waits until the engine is ready, failed, or `timeout` elapses.
pub async fn wait_ready(
    mut rx: watch::Receiver<Status>,
    timeout: Duration,
) -> Result<EngineInfo, String> {
    let wait = rx.wait_for(|s| !matches!(s, Status::Starting));
    match tokio::time::timeout(timeout, wait).await {
        Ok(Ok(status)) => match &*status {
            Status::Ready(info) => Ok(info.clone()),
            Status::Failed(msg) => Err(msg.clone()),
            Status::Starting => unreachable!(),
        },
        Ok(Err(_)) => Err("Engine state channel closed".to_string()),
        Err(_) => Err("The engine didn't start in time".to_string()),
    }
}

pub struct EngineState {
    status: watch::Sender<Status>,
    child: Mutex<Option<CommandChild>>,
    generation: AtomicU64,
}

impl Default for EngineState {
    fn default() -> Self {
        Self {
            status: watch::channel(Status::Starting).0,
            child: Mutex::new(None),
            generation: AtomicU64::new(0),
        }
    }
}

impl EngineState {
    fn set_if_current(&self, generation: u64, status: Status) {
        if self.generation.load(Ordering::SeqCst) == generation {
            self.status.send_replace(status);
        }
    }

    pub fn kill(&self) {
        if let Some(child) = self.child.lock().unwrap().take() {
            let _ = child.kill();
        }
    }

    /// Kills any running engine, bumps the generation, and resets to Starting.
    fn begin(&self) -> u64 {
        self.kill();
        let generation = self.generation.fetch_add(1, Ordering::SeqCst) + 1;
        self.status.send_replace(Status::Starting);
        generation
    }

    /// Records a startup failure so waiters get the real cause immediately.
    fn fail_start(&self, generation: u64, msg: String) {
        eprintln!("[engine] failed to start: {msg}");
        self.set_if_current(generation, Status::Failed(msg));
    }

    /// Starts the engine. Never fails: errors become `Status::Failed`.
    pub fn start(&self, app: &AppHandle) {
        let generation = self.begin();
        if let Err(msg) = self.try_start(app, generation) {
            self.fail_start(generation, msg);
        }
    }

    /// Spawns the sidecar (or applies the debug-only dev bypass).
    fn try_start(&self, app: &AppHandle, generation: u64) -> Result<(), String> {

        #[cfg(debug_assertions)]
        if let (Ok(port), Ok(token)) = (
            std::env::var("FOLIO_ENGINE_DEV_PORT"),
            std::env::var("FOLIO_ENGINE_DEV_TOKEN"),
        ) {
            let port = port
                .parse()
                .map_err(|_| "FOLIO_ENGINE_DEV_PORT is not a port number".to_string())?;
            self.set_if_current(generation, Status::Ready(EngineInfo { port, token }));
            return Ok(());
        }

        let token = generate_token();
        let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
        let (mut rx, child) = app
            .shell()
            .sidecar("folio-engine")
            .map_err(|e| e.to_string())?
            .env("FOLIO_ENGINE_TOKEN", &token)
            .args(["--exit-on-stdin-close".to_string(), "--data-dir".to_string(), data_dir.to_string_lossy().into_owned()])
            .spawn()
            .map_err(|e| e.to_string())?;
        *self.child.lock().unwrap() = Some(child);

        let handle = app.clone();
        tauri::async_runtime::spawn(async move {
            let state = handle.state::<EngineState>();
            let mut out = LineBuffer::default();
            let mut err = LineBuffer::default();
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(chunk) => {
                        for line in out.push(&chunk) {
                            if let Some(port) = parse_ready_line(&line) {
                                let info = EngineInfo { port, token: token.clone() };
                                state.set_if_current(generation, Status::Ready(info));
                            }
                        }
                    }
                    CommandEvent::Stderr(chunk) => {
                        for line in err.push(&chunk) {
                            eprintln!("[engine] {line}");
                        }
                    }
                    CommandEvent::Error(e) => {
                        eprintln!("[engine] process error: {e}");
                        state.set_if_current(generation, Status::Failed(format!("Engine error: {e}")));
                    }
                    CommandEvent::Terminated(p) => {
                        eprintln!("[engine] exited (code {:?})", p.code);
                        state.set_if_current(
                            generation,
                            Status::Failed(format!("The engine stopped (exit code {:?})", p.code)),
                        );
                        break;
                    }
                    _ => {}
                }
            }
        });
        Ok(())
    }

    pub async fn info(&self, timeout: Duration) -> Result<EngineInfo, String> {
        wait_ready(self.status.subscribe(), timeout).await
    }
}

#[tauri::command]
pub async fn engine_info(state: State<'_, EngineState>) -> Result<EngineInfo, String> {
    state.info(READY_TIMEOUT).await
}

#[tauri::command]
pub async fn restart_engine(app: AppHandle, state: State<'_, EngineState>) -> Result<(), String> {
    state.start(&app);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_ready_line() {
        assert_eq!(parse_ready_line("FOLIO_ENGINE_READY port=51234"), Some(51234));
        assert_eq!(parse_ready_line("FOLIO_ENGINE_READY port=51234\r\n"), Some(51234));
    }

    #[test]
    fn rejects_other_lines() {
        assert_eq!(parse_ready_line("hello"), None);
        assert_eq!(parse_ready_line("FOLIO_ENGINE_READY port=abc"), None);
        assert_eq!(parse_ready_line("FOLIO_ENGINE_READY port=99999"), None);
    }

    #[test]
    fn line_buffer_joins_split_chunks() {
        let mut buf = LineBuffer::default();
        assert!(buf.push(b"FOLIO_ENGINE_RE").is_empty());
        assert_eq!(buf.push(b"ADY port=1\nnext"), vec!["FOLIO_ENGINE_READY port=1"]);
        assert_eq!(buf.push(b" line\r\n\n"), vec!["next line", ""]);
    }

    #[test]
    fn tokens_are_64_hex_chars_and_unique() {
        let (a, b) = (generate_token(), generate_token());
        assert_eq!(a.len(), 64);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }

    #[tokio::test]
    async fn ready_timeout_returns_error() {
        let (_tx, rx) = watch::channel(Status::Starting);
        let err = wait_ready(rx, Duration::from_millis(50)).await.unwrap_err();
        assert!(err.contains("didn't start"), "{err}");
    }

    #[tokio::test]
    async fn ready_signal_returns_info() {
        let (tx, rx) = watch::channel(Status::Starting);
        let info = EngineInfo { port: 1234, token: "t".into() };
        let sent = info.clone();
        tokio::spawn(async move { tx.send_replace(Status::Ready(sent)) });
        assert_eq!(wait_ready(rx, Duration::from_secs(2)).await, Ok(info));
    }

    #[tokio::test]
    async fn start_failure_is_reported_immediately() {
        let state = EngineState::default();
        let generation = state.begin();
        state.fail_start(generation, "no sidecar".to_string());
        let started = std::time::Instant::now();
        let err = state.info(Duration::from_secs(5)).await.unwrap_err();
        assert_eq!(err, "no sidecar");
        assert!(started.elapsed() < Duration::from_secs(1));
    }
}
