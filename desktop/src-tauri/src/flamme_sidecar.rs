//! Flamme Python sidecar — spawn uvicorn on 127.0.0.1:8765 (Flamme 3.0 Phase 1).

use std::path::{Path, PathBuf};
use std::process::{Child, Stdio};
use std::time::{Duration, Instant};

use crate::hidden_command;

const FLAMME_PORT: u16 = 8765;
const HEALTH_URL: &str = "http://127.0.0.1:8765/";
const DEFAULT_HEALTH_WAIT: Duration = Duration::from_secs(15);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(400);

/// When set to `1`, Rust does not spawn Python (dev: manual uvicorn).
pub fn flamme_dev_skip_spawn() -> bool {
    std::env::var("FLAMME_DEV")
        .ok()
        .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
        .unwrap_or(false)
}

pub fn flamme_backend_root() -> Result<PathBuf, String> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let desktop_root = manifest_dir.join("..");
    let candidates = [
        desktop_root.join("flamme-backend"),
        desktop_root.join(".."), // monorepo root: Flamme/{src,plugin,...}
    ];
    for root in candidates {
        if root.join("src").join("api").join("app.py").is_file() {
            return Ok(root.canonicalize().unwrap_or(root));
        }
    }
    Err(format!(
        "Flamme backend not found (expected {} or monorepo root with src/api/app.py)",
        desktop_root.join("flamme-backend").display()
    ))
}

fn validate_python_executable(path: &Path) -> Result<PathBuf, String> {
    if !path.is_file() {
        return Err(format!("Python executable not found: {}", path.display()));
    }

    let output = hidden_command(path)
        .arg("--version")
        .output()
        .map_err(|e| format!("Failed to run {}: {e}", path.display()))?;
    if !output.status.success() {
        return Err(format!("{} --version failed", path.display()));
    }
    Ok(path.to_path_buf())
}

fn backend_venv_candidates(backend_root: &Path) -> [PathBuf; 2] {
    #[cfg(windows)]
    {
        [
            backend_root.join(".venv").join("Scripts").join("python.exe"),
            backend_root.join("venv").join("Scripts").join("python.exe"),
        ]
    }
    #[cfg(not(windows))]
    {
        [
            backend_root.join(".venv").join("bin").join("python3"),
            backend_root.join("venv").join("bin").join("python3"),
        ]
    }
}

fn read_python_path_file(backend_root: &Path) -> Option<PathBuf> {
    let path_file = backend_root.join(".python-path");
    let content = std::fs::read_to_string(path_file).ok()?;
    let trimmed = content.lines().next()?.trim();
    if trimmed.is_empty() {
        return None;
    }
    let path = PathBuf::from(trimmed);
    if path.is_file() {
        Some(path)
    } else {
        None
    }
}

fn find_python(backend_root: &Path) -> Result<PathBuf, String> {
    if let Ok(from_env) = std::env::var("FLAMME_PYTHON") {
        let trimmed = from_env.trim();
        if !trimmed.is_empty() {
            return validate_python_executable(Path::new(trimmed));
        }
    }

    if let Some(from_file) = read_python_path_file(backend_root) {
        if let Ok(path) = validate_python_executable(&from_file) {
            return Ok(path);
        }
    }

    for candidate in backend_venv_candidates(backend_root) {
        if let Ok(path) = validate_python_executable(&candidate) {
            return Ok(path);
        }
    }

    find_system_python()
}

fn find_system_python() -> Result<PathBuf, String> {
    #[cfg(windows)]
    {
        for candidate in ["py", "python", "python3"] {
            if let Ok(path) = which_python(candidate) {
                return Ok(path);
            }
        }
        return Err(
            "Python not found. Install Python 3.10+ and ensure py/python is on PATH.".into(),
        );
    }

    #[cfg(not(windows))]
    {
        for candidate in ["python3", "python"] {
            if let Ok(path) = which_python(candidate) {
                return Ok(path);
            }
        }
        return Err(
            "Python not found. Install Python 3.10+ and ensure python3 is on PATH.".into(),
        );
    }
}

fn which_python(name: &str) -> Result<PathBuf, String> {
    #[cfg(windows)]
    let mut command = if name == "py" {
        let mut cmd = hidden_command(name);
        cmd.arg("-3");
        cmd
    } else {
        hidden_command(name)
    };

    #[cfg(not(windows))]
    let mut command = hidden_command(name);

    command.arg("--version");
    let output = command
        .output()
        .map_err(|e| format!("Failed to run {name}: {e}"))?;
    if !output.status.success() {
        return Err(format!("{name} --version failed"));
    }
    Ok(PathBuf::from(name))
}

fn validate_vault_path(vault_path: &Path) -> Result<PathBuf, String> {
    let resolved = vault_path
        .canonicalize()
        .map_err(|e| format!("Invalid vault path {}: {e}", vault_path.display()))?;
    if !resolved.is_dir() {
        return Err(format!("Vault path is not a directory: {}", resolved.display()));
    }
    Ok(resolved)
}

/// Spawn uvicorn for Flamme backend; does not wait for health.
pub fn spawn_flamme_sidecar(vault_path: impl AsRef<Path>) -> Result<Child, String> {
    if flamme_dev_skip_spawn() {
        return Err("FLAMME_DEV=1: sidecar spawn skipped (start uvicorn manually)".into());
    }

    let vault_path = validate_vault_path(vault_path.as_ref())?;
    let backend_root = flamme_backend_root()?;
    let python = find_python(&backend_root)?;
    let wiki_dir = vault_path.join(".wiki");

    let mut command = hidden_command(&python);
    command
        .current_dir(&backend_root)
        .args([
            "-m",
            "uvicorn",
            "src.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            &FLAMME_PORT.to_string(),
        ])
        .env("FLAMME_VAULT_PATH", &vault_path)
        .env("FLAMME_WIKI_DIR", &wiki_dir)
        .env("LLM_WIKI_VAULT", vault_path.as_os_str())
        .env("FLAMME_DESKTOP", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let child = command
        .spawn()
        .map_err(|e| format!("Failed to spawn Flamme sidecar: {e}"))?;

    log::info!(
        "Flamme sidecar spawned (pid: {}, vault: {}, backend: {}, python: {})",
        child.id(),
        vault_path.display(),
        backend_root.display(),
        python.display()
    );
    Ok(child)
}

pub fn stop_flamme_sidecar(child: &mut Option<Child>) {
    let Some(mut active) = child.take() else {
        return;
    };
    let pid = active.id();
    let _ = active.kill();
    let _ = active.wait();
    log::info!("Flamme sidecar stopped (pid: {pid})");
}

/// Poll root health endpoint until 200 or timeout.
pub fn wait_healthy(max_wait: Duration) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))?;

    let deadline = Instant::now() + max_wait;
    while Instant::now() < deadline {
        match client.get(HEALTH_URL).send() {
            Ok(resp) if resp.status().is_success() => return Ok(()),
            Ok(resp) => {
                log::debug!("Flamme health returned {}", resp.status());
            }
            Err(e) => {
                log::debug!("Flamme health poll: {e}");
            }
        }
        std::thread::sleep(HEALTH_POLL_INTERVAL);
    }
    Err(format!(
        "Flamme sidecar did not become healthy within {}s",
        max_wait.as_secs()
    ))
}

pub fn default_health_wait() -> Duration {
    DEFAULT_HEALTH_WAIT
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flamme_dev_skip_spawn_reads_env() {
        std::env::set_var("FLAMME_DEV", "1");
        assert!(flamme_dev_skip_spawn());
        std::env::remove_var("FLAMME_DEV");
    }
}
