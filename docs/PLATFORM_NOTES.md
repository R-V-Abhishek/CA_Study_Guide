# Platform Notes & Troubleshooting

Guidance and known platform-specific considerations for running the CA Final Study Companion on **Windows**, **macOS**, and **Linux**.

---

## Windows (10 / 11)

### 1. Prerequisites
- **Python 3.12+**: Download the official installer from [python.org](https://www.python.org/downloads/windows/).
  > **Crucial**: On the first screen of the installer, check the box: **"Add python.exe to PATH"**.
- **Docker Desktop**: Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
  - Ensure **WSL 2 backend** is enabled in Docker Desktop settings.

### 2. Double-Click Launchers
We provide convenient `.bat` scripts in the root directory:
- `setup.bat`: Double-click once for initial setup.
- `start.bat`: Double-click daily to start studying.
- `stop.bat`: Double-click to stop all background processes.

### 3. PowerShell Script Execution Policy
If running PowerShell directly and encountering a script execution error:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 4. Volume Paths
The PostgreSQL container mounts `./data/pg` as a volume. Docker Desktop for Windows handles host-to-container volume mapping automatically. Ensure Docker has file-sharing permission for your project drive.

---

## macOS (Apple Silicon M1/M2/M3/M4 & Intel)

### 1. Prerequisites
- **Python 3.12+**: Install via Homebrew:
  ```bash
  brew install python@3.12
  ```
  Or download from [python.org](https://www.python.org/downloads/macos/).
- **Docker Desktop**: Download the Apple Silicon or Intel build of [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/).

### 2. Permissions
If launching from terminal or double-clicking `.sh` files, verify execution permissions:
```bash
chmod +x setup.sh start.sh stop.sh
```

### 3. Port Conflicts
- PostgreSQL maps host port `5433` (configured in `.env` as `PG_PORT=5433`) to container port `5432`. This avoids conflict with any local PostgreSQL instance you might have on default port `5432`.
- The web server runs on port `8000`. If port 8000 is occupied, launch via `uv run caf serve --port 8080`.

---

## Linux (Ubuntu, Debian, Fedora, Arch)

### 1. Prerequisites
- **Python 3.12+**:
  ```bash
  # Ubuntu / Debian (using deadsnakes PPA if on older distribution)
  sudo apt update
  sudo apt install python3.12 python3.12-venv python3-pip
  ```
- **Docker & Docker Compose**:
  ```bash
  sudo apt install docker.io docker-compose-v2
  ```

### 2. Docker Without Sudo
Add your current user to the `docker` group so `docker compose` can run without root:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

### 3. Systemd & Firewall
Verify that port `8000` is open if accessing from a different machine on your local network:
```bash
sudo ufw allow 8000/tcp
```
