# Docker Stack Backup Script

A robust Python 3 script designed to safely archive Docker Compose application stacks, stop them during backup to ensure data consistency, and enforce a local retention policy. The script uses `tar` for archiving and sends a detailed ASCII-formatted summary via email.

This script is ideal for use in a cron job environment (e.g., daily runs).

## ✨ Features

* **Consistency Assurance:** Safely stops and restarts Docker stacks using `docker compose down/up -d`.
* **Archiving:** Creates uncompressed `.tar` archives of specified stack directories.
* **Retention:** Enforces a local retention policy (default: 28 days).
* **Detailed Email Reporting:** Sends a summary email containing:
    * A list and total size of all new archives created.
    * Disk usage statistics for the backup partition.
    * A list of files deleted by the retention policy.
* **Logging:** Appends all runtime steps and errors to a dedicated log file.

## ⚙️ Configuration

Before running the script, you must adjust the configuration parameters in the `--- CONFIGURATION ---` section.

| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| `STACKS` | `["beszel", ...]` | **Required.** List of stack directory names located inside `BASE_DIR`. |
| `BASE_DIR` | `/opt/stacks` | **Required.** The root directory containing most of your stacks. |
| `EXTRA_STACK_PATH` | `/opt/dockge` | Optional. Full path to a single stack located outside of `BASE_DIR`. |
| `BACKUP_DIR` | `/var/backups/docker` | **Required.** The target directory where archives will be stored. |
| `DAILY_RETENTION_DAYS` | `28` | The number of days to keep local backups before deletion. |
| `SMTP_SERVER`, `SMTP_PORT` | `mailjet.com`, `587` | Your SMTP server details for sending notifications. |
| `SMTP_USER`, `SMTP_PASS` | `YOUR_API_KEY` | Your SMTP credentials. |
| `SENDER_EMAIL`, `RECEIVER_EMAIL` | `sender@...`, `recipient@...` | Email addresses for reporting. |
| `LOG_FILE` | `/var/log/docker-backup.log` | Path to the output log file. |

## 🚀 Usage

### 1. Setup

1.  Save the code as a Python script (e.g., `docker_backup.py`).
2.  Make the script executable:
    ```bash
    chmod +x docker_backup.py
    ```
3.  Configure all parameters in the `--- CONFIGURATION ---` section.
4.  Ensure that Python 3, `tar`, and `docker` are in your system's PATH.

### 2. Execution

Run the script manually:

```bash
/path/to/docker_backup.py
