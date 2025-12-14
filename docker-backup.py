#!/usr/bin/env python3
import subprocess
import os
import sys
from datetime import datetime
from smtplib import SMTP_SSL
from email.message import EmailMessage

# --- CONFIGURATION (User-configurable parameters) ---
STACKS = ["stack1", "stack2", "stack3", "stack4", "stack5"] 
BASE_DIR = "/opt/stacks"
EXTRA_STACK_PATH = "/opt/dockge" 
BACKUP_DIR = "/var/backups/docker"
DAILY_RETENTION_DAYS = 28

# Email Configuration
SMTP_SERVER = 'in-v3.mailjet.com'
SMTP_PORT = 587
SMTP_USER = 'YOUR_API_KEY'
SMTP_PASS = 'YOUR_API_SECRET'
SENDER_EMAIL = 'sender@your-domain.com'
RECEIVER_EMAIL = 'recipient@email.com'
SUBJECT_TAG = "[DOCKER-BACKUP]"

# Log file path
LOG_FILE = "/var/log/docker-backup.log"

# --- GLOBAL VARIABLES ---
LOG_MESSAGES = []
BACKUP_SUCCESSFUL = True
NEW_ARCHIVES = []

# --- HELPER FUNCTIONS ---

def log(message, level="INFO"):
    """Logs a message to the console and the global log list."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}"
    print(log_entry)
    LOG_MESSAGES.append(log_entry)
    if level == "ERROR":
        global BACKUP_SUCCESSFUL
        BACKUP_SUCCESSFUL = False

def run_command(command, description):
    """Executes a shell command and logs the result."""
    try:
        log(f"Starting command: {description} ({' '.join(command)})")
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        log(f"Successfully finished: {description}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        log(f"Failed: {description}. Error:\n{e.stderr.strip()}", "ERROR")
        return None
    except FileNotFoundError:
        log(f"Error: Command not found or not in PATH.", "ERROR")
        return None

def compose_action(stack_path, action="down"):
    """Stops or starts a Docker Compose stack."""
    if not os.path.isdir(stack_path):
        log(f"Stack directory not found at {stack_path}. Skipping {action}.", "WARNING")
        return True
    
    action_text = "Stopping" if action == "down" else "Starting"
    log(f"{action_text} stack in {stack_path}...")
    
    compose_file = "compose.yaml" if os.path.exists(os.path.join(stack_path, "compose.yaml")) else "docker-compose.yml"
    
    cmd = ["docker", "compose", "-f", os.path.join(stack_path, compose_file), action]
    if action == "up":
        cmd.append("-d") 
        
    result = run_command(cmd, f"{action_text} {os.path.basename(stack_path)}")
    return result is not None

def create_archive(stack_name, base_dir, stack_path):
    """Creates an UNCOMPRESSED TAR archive."""
    global NEW_ARCHIVES
    
    TARGET_EXT = "tar"
    TAR_COMMAND = "tar -c -f" 
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if stack_path == EXTRA_STACK_PATH:
        archive_name = os.path.basename(stack_path)
        archive_root_dir = os.path.dirname(stack_path)
    else:
        archive_name = stack_name
        archive_root_dir = base_dir

    target_filename = os.path.join(BACKUP_DIR, f"{archive_name}_{timestamp}.{TARGET_EXT}")
    
    log(f"Creating uncompressed archive for '{archive_name}' at {target_filename}...")
    
    cmd = f"{TAR_COMMAND} {target_filename} -C {archive_root_dir} {archive_name}"
    
    command_list = cmd.split()
    
    if "-C" in command_list:
        c_index = command_list.index("-C")
        if c_index + 1 < len(command_list):
            result = run_command(command_list, f"Archiving {archive_name}")
        else:
            log(f"Internal Error: -C flag not followed by a directory.", "ERROR")
            return False
    else:
        result = run_command(command_list, f"Archiving {archive_name}")
    
    if result is not None:
        NEW_ARCHIVES.append(os.path.basename(target_filename))
    return result is not None


def cleanup_local_backups():
    """Deletes old local archives based on retention days."""
    TARGET_EXT = "tar"
    
    log(f"Starting local backup cleanup: deleting files older than {DAILY_RETENTION_DAYS} days.")
    
    find_cmd = [
        "find", BACKUP_DIR, 
        "-type", "f", 
        "-name", f"*.{TARGET_EXT}", 
        "-mtime", f"+{DAILY_RETENTION_DAYS}", 
        "-print0" 
    ]

    try:
        find_result = subprocess.run(find_cmd, capture_output=True, text=True, check=True)
        files_to_delete = find_result.stdout.strip().split('\0')
        
        deleted_count = 0
        for file_path in files_to_delete:
            if file_path:
                try:
                    os.remove(file_path)
                    log(f"Deleted old backup: {file_path}")
                    deleted_count += 1
                except OSError as e:
                    log(f"Error deleting file {file_path}: {e}", "ERROR")

        log(f"Local cleanup finished. Total files deleted: {deleted_count}")
    
    except subprocess.CalledProcessError as e:
        log(f"Error during find command execution: {e.stderr.strip()}", "ERROR")
    except Exception as e:
        log(f"An unexpected error occurred during cleanup: {e}", "ERROR")


def get_disk_usage():
    """Gets disk usage information for the BACKUP_DIR mount point."""
    try:
        df_result = run_command(["df", "-h", "--output=size,used,avail,pcent,target", BACKUP_DIR], "Checking disk usage")
        if df_result:
            lines = df_result.split('\n')
            if len(lines) > 1:
                data = lines[1].split()
                if len(data) >= 5:
                    return {
                        "total": data[0], 
                        "used": data[1], 
                        "free": data[2], 
                        "percent": data[3],
                        "mount": data[4]
                    }
        log("Could not parse disk usage data.", "WARNING")
        return None
    except Exception as e:
        log(f"Error getting disk usage: {e}", "ERROR")
        return None

def send_email_notification(disk_info):
    """Sends a summary email notification."""
    
    status = "SUCCESS" if BACKUP_SUCCESSFUL else "FAILURE"
    
    try:
        hostname = subprocess.check_output(['hostname']).decode('utf-8').strip()
    except:
        hostname = "UNKNOWN_HOST"
        
    current_date = datetime.now().strftime('%Y-%m-%d')
    subject = f"{SUBJECT_TAG} {status}: Docker Backup completed on {hostname} ({current_date})"
    
    archive_list = "\n".join([f"- {a}" for a in NEW_ARCHIVES]) if NEW_ARCHIVES else "- No new archives created."

    disk_body = ""
    if disk_info:
        disk_body = f"""
        --- Disk Usage ({disk_info['mount']}) ---
        Total: {disk_info['total']}
        Used: {disk_info['used']} ({disk_info['percent']})
        Free: {disk_info['free']}
        """
    else:
        disk_body = "Disk usage information not available."

    log_body = "\n".join(LOG_MESSAGES)
    
    email_content = f"""
    Docker Stacks Backup Script Report ({status})

    --- New Archives (Uncompressed .tar) ---
    {archive_list}
    
    --- Retention Policy ---
    Files older than {DAILY_RETENTION_DAYS} days were deleted.

    {disk_body}

    --- Full Log ---
    {log_body}
    """
    
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg.set_content(email_content)
    
    try:
        log("Sending email notification...")
        with SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        log("Email sent successfully.", "INFO")
    except Exception as e:
        log(f"Failed to send email: {e}", "ERROR")

# --- MAIN EXECUTION ---

def main():
    current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    initial_log_header = (
        "\n" + "="*50 + 
        f"\n--- DOCKER BACKUP SCRIPT START ---\nDate and Time: {current_time_str}\n" + 
        "="*50
    )
    LOG_MESSAGES.append(initial_log_header)

    log("Phase 0: Initializing directories.")
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    # 1. STOP CONTAINERS
    log("Phase 1: Stopping all Docker Compose stacks.")
    
    all_stacks = [os.path.join(BASE_DIR, s) for s in STACKS]
    if EXTRA_STACK_PATH:
        all_stacks.append(EXTRA_STACK_PATH)
        
    successfully_stopped_stacks = []
    
    for stack_path in all_stacks:
        if compose_action(stack_path, action="down"):
            successfully_stopped_stacks.append(stack_path)
    
    # 2. CREATE BACKUPS (Uncompressed .tar)
    log("Phase 2: Creating uncompressed TAR archives.")
    
    for stack_name in STACKS:
        create_archive(stack_name, BASE_DIR, os.path.join(BASE_DIR, stack_name))

    if EXTRA_STACK_PATH:
        create_archive(os.path.basename(EXTRA_STACK_PATH), os.path.dirname(EXTRA_STACK_PATH), EXTRA_STACK_PATH)

    # 3. START CONTAINERS
    log("Phase 3: Starting all successfully stopped Docker Compose stacks.")
    
    for stack_path in successfully_stopped_stacks:
        compose_action(stack_path, action="up")

    # 4. LOCAL CLEANUP
    log("Phase 4: Running local retention cleanup.")
    cleanup_local_backups()

    # 5. FINALIZATION AND NOTIFICATION
    disk_info = get_disk_usage()
    send_email_notification(disk_info)

    log("--- DOCKER BACKUP SCRIPT END ---")
    
    try:
        with open(LOG_FILE, 'a') as f:
            f.write('\n'.join(LOG_MESSAGES) + "\n\n")
    except Exception as e:
        print(f"FATAL: Could not write final log to file: {e}", file=sys.stderr)

    if not BACKUP_SUCCESSFUL:
        sys.exit(1)
    
    sys.exit(0)

if __name__ == "__main__":
    main()
