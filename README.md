# 🐳 Docker Stacks Backup Script

This is a robust Python script designed to automate the backup, compression (using Zstandard), and retention management of multiple Docker Compose stacks. It ensures data consistency by stopping services before backup and restarting them immediately afterwards.

## ✨ Features

* **Consistent Backups:** Stops Docker Compose stacks (`docker compose down`) before archiving to ensure data integrity and restarts them (`docker compose up -d`) afterwards.
* **Efficient Compression:** Uses the highly efficient Zstandard (`.tar.zst`) compression algorithm for smaller file sizes and faster compression/decompression compared to standard Gzip.
* **Comprehensive Logging:** Logs all steps, including start/stop actions, compression results, and cleanup to a dedicated log file (`/var/log/docker-backup.log`).
* **Detailed Email Notifications:** Sends an email notification (SUCCESS or FAILURE) containing a summary of the new archives, local disk usage of the backup volume, and the full run log.
* **Retention Management:** Automatically cleans up local backup archives older than a configurable number of days (default: 28 days).
* **Detailed Disk Info:** Includes total storage, used storage, and percentage usage of the backup volume in the final summary.

## ⚙️ Prerequisites

Before running the script, ensure your system has the following installed:

1.  **Python 3:** The script requires Python 3.6+ and standard libraries (`subprocess`, `os`, `sys`, `datetime`, `smtplib`, `email`).
2.  **`docker` and `docker compose`:** Necessary for stopping and starting the stacks.
3.  **`tar` with Zstandard Support:** The `tar` utility must support the `-I zstd` flag for Zstandard compression (common in modern Linux distributions).
4.  **`df` and `du` utilities:** Used for disk space checks and summary reporting.

## 🚀 Installation & Setup

### 1. Place the Script

Save the provided Python script (e.g., `docker-backup.py`) to a suitable location, like `/usr/local/bin/`.

```bash
sudo mv docker-backup.py /usr/local/bin/
sudo chmod +x /usr/local/bin/docker-backup.py
