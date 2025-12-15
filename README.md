# Docker Stack Backup Script

## Description

This Python script automates the backup process for multiple Docker Compose stacks. It is designed to execute a **stop-archive-start cycle** for each stack to ensure data consistency while minimizing downtime. Archives are saved as **uncompressed `.tar` files** to enhance efficiency and reduce restoration time.

Upon successful completion, the script performs local data cleanup (`Retention`) and sends a detailed ASCII email report containing all relevant information, including the total space freed during cleanup.

## Features

* **Zero-Downtime Strategy:** Stops and starts each stack individually to maximize overall availability.
* **Uncompressed Archives:** Creates `.tar` archives without additional compression to speed up the process and minimize restoration time.
* **Local Retention:** Automatically deletes backups older than the configured value (default 28 days) and calculates the total disk space freed.
* **Detailed Reporting:** Sends a comprehensive email report that includes the status, a list of newly created archives (incl. size), the total space freed, and the current storage usage of the backup volume.

## Configuration

Adjust the following variables within the script (`docker-backup.py`) to match your environment:

### Paths and Stacks
| Variable | Description | Default Value |
| :--- | :--- | :--- |
| `STACKS` | List of stack names located in the `BASE_DIR`. | `["beszel", ...]` |
| `BASE_DIR` | Base directory containing your Docker Compose stacks. | `/opt/stacks` |
| `EXTRA_STACK_PATH` | Path to a stack located outside the `BASE_DIR` (optional). | `/opt/dockge` |
| `BACKUP_DIR` | Destination directory for the backup archives. | `/var/backups/docker` |
| `DAILY_RETENTION_DAYS` | Number of days to keep local backups before deletion. | `28` |
| `LOG_FILE` | Path to the output log file. | `/var/log/docker-backup.log` |

### Email Notification
Configure your SMTP settings to receive reports.

| Variable | Description |
| :--- | :--- |
| `SMTP_SERVER` / `SMTP_PORT` | SMTP server address and port. |
| `SMTP_USER` / `SMTP_PASS` | Credentials for the SMTP server. |
| `SENDER_EMAIL` / `RECEIVER_EMAIL` | Sender and recipient email addresses. |
| `SUBJECT_TAG` | Prefix for the email subject line. |

## Usage

1.  **Permissions:** Ensure the script is executable and has the necessary permissions to access Docker, the stacks, and the backup directory.
    ```bash
    chmod +x docker-backup.py
    ```

2.  **Set up Cron Job:** Schedule the script to run daily (or as needed) using a cron job.
    ```bash
    # Example: Run daily at 02:00 AM
    0 2 * * * /usr/bin/env python3 /path/to/your/docker-backup.py
    ```
