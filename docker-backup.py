#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ==============================================================================
# Docker Stack Backup Script
# ==============================================================================
# Description: Safely archives Docker Compose stacks (stop/tar/start),
#              enforces local retention, and sends detailed ASCII email reports.
# Author:      gimpfenlord (https://github.com/gimpfenlord)
# Version:     1.2.0 
# Created:     2025-12-15
# License:     MIT
# ==============================================================================

import subprocess
import os
import sys
from datetime import datetime
import smtplib
from email.message import EmailMessage

# --- CONFIGURATION (User-configurable parameters) ---
STACKS = ["stack1", "stack2", "stack3", "stack4", "stack5"] 

# Directory settings
BASE_DIR = "/opt/stacks"
EXTRA_STACK_PATH = "/opt/dockge" 

BACKUP_DIR = "/var/backups/docker"
DAILY_RETENTION_DAYS = 28

# Email Configuration
SMTP_SERVER = 'mailserver'
SMTP_PORT = 587
SMTP_USER = 'username'
SMTP_PASS = 'password'
SENDER_EMAIL = 'sender@your-domain.com'
RECEIVER_EMAIL = 'recipient@email.com'

SUBJECT_TAG = "[TAG]"

# Log file path
LOG_FILE = "/var/log/docker-backup.log"

# --- GLOBAL VARIABLES ---
LOG_MESSAGES = []
BACKUP_SUCCESSFUL = True
NEW_ARCHIVES = [] # List of tuples: [(full_path, size_human_readable, size_bytes), ...]
DELETED_FILES = [] # List of filenames deleted by retention
DELETED_SIZE_BYTES = 0 # Total size of all files deleted by retention

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
    """Creates an UNCOMPRESSED TAR archive inside a dedicated stack folder."""
    global NEW_ARCHIVES
    
    TARGET_EXT = "tar"
    TAR_COMMAND = "tar -c -f" 
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Determine the actual root directory and the name to archive
    if stack_path == EXTRA_STACK_PATH:
        archive_name = os.path.basename(stack_path)
        archive_root_dir = os.path.dirname(stack_path)
    else:
        archive_name = stack_name
        archive_root_dir = base_dir

    final_backup_path = os.path.join(BACKUP_DIR, archive_name)
    os.makedirs(final_backup_path, exist_ok=True)
    
    target_filename = os.path.join(final_backup_path, f"{archive_name}_{timestamp}.{TARGET_EXT}")
    
    log(f"Creating uncompressed archive for '{archive_name}' at {target_filename}...")
    
    # tar -c -f [target_filename] -C [archive_root_dir] [archive_name]
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
        # Get file size in bytes
        size_bytes = 0
        size_human = "N/A" 
        try:
            size_bytes = os.path.getsize(target_filename)
        except Exception:
            pass
        
        # Store the full path and both size formats
        relative_path = os.path.relpath(target_filename, "/") 
        NEW_ARCHIVES.append(('/' + relative_path, size_human, size_bytes))
    return result is not None


def cleanup_local_backups():
    """Deletes old local archives based on retention days and calculates freed space."""
    global DELETED_FILES
    global DELETED_SIZE_BYTES
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
        DELETED_SIZE_BYTES = 0 
        for file_path in files_to_delete:
            if file_path:
                try:
                    # Get size before deletion
                    size_bytes = os.path.getsize(file_path)
                    
                    os.remove(file_path)
                    DELETED_SIZE_BYTES += size_bytes
                    
                    # Store full path for retention summary
                    relative_path = os.path.relpath(file_path, "/")
                    DELETED_FILES.append('/' + relative_path)
                    log(f"Deleted old backup: {file_path}")
                    deleted_count += 1
                except OSError as e:
                    log(f"Error deleting file {file_path}: {e}", "ERROR")
                except FileNotFoundError:
                    log(f"File not found during cleanup: {file_path}", "WARNING")

        log(f"Local cleanup finished. Total files deleted: {deleted_count}. Freed space: {format_bytes(DELETED_SIZE_BYTES)}")
    
    except subprocess.CalledProcessError as e:
        log(f"Error during find command execution: {e.stderr.strip()}", "ERROR")
    except Exception as e:
        log(f"An unexpected error occurred during cleanup: {e}", "ERROR")


def get_disk_usage():
    """Gets disk usage information for the BACKUP_DIR mount point and the actual backup content size."""
    disk_info = None
    backup_content_size = "N/A"

    # 1. Get Mountpoint Disk Usage (df -h)
    try:
        df_result = run_command(["df", "-h", "--output=size,used,avail,pcent,target", BACKUP_DIR], "Checking disk usage")
        if df_result:
            lines = df_result.split('\n')
            if len(lines) > 1:
                data = lines[1].split()
                if len(data) >= 5:
                    disk_info = {
                        "total": data[0], 
                        "used": data[1], 
                        "free": data[2], 
                        "percent": data[3],
                        "mount": data[4]
                    }
    except Exception as e:
        log(f"Error getting disk usage via df: {e}", "ERROR")

    # 2. Get Backup Directory Content Size (du -sh)
    try:
        if os.path.isdir(BACKUP_DIR):
            du_cmd = ["du", "-sh", BACKUP_DIR]
            du_output = subprocess.check_output(du_cmd, text=True).split()
            if du_output:
                backup_content_size = du_output[0]
        else:
             log(f"Backup directory {BACKUP_DIR} not found for size calculation.", "WARNING")

    except subprocess.CalledProcessError as e:
        log(f"Error getting directory size via du: {e.stderr.strip()}", "ERROR")
    except Exception as e:
        log(f"An unexpected error occurred during du size check: {e}", "ERROR")
    
    return disk_info, backup_content_size


def format_bytes(size_bytes):
    """Converts bytes to human-readable format (like du -h)."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "K", "M", "G", "T", "P", "E", "Z", "Y")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.
        i += 1
    if i == 0:
        return f"{int(size_bytes)}{size_name[i]}"
    return f"{size_bytes:.1f}{size_name[i]}"


def send_email_notification(disk_info, backup_content_size):
    """Sends a summary email notification."""
    
    status = "SUCCESS" if BACKUP_SUCCESSFUL else "FAILURE"
    
    try:
        hostname = subprocess.check_output(['hostname']).decode('utf-8').strip()
    except:
        hostname = "UNKNOWN_HOST"
        
    current_date = datetime.now().strftime('%Y-%m-%d')
    subject = f"{SUBJECT_TAG} {status}: Docker Backup completed on {hostname} ({current_date})"
    
    # --- 1. NEW ARCHIVES TABLE (Compact format with Total Size) ---
    
    NEW_ARCHIVES.sort(key=lambda x: x[0])
    
    FILE_WIDTH = 50 
    SIZE_WIDTH = 8
    SEPARATOR = "-" * (FILE_WIDTH + SIZE_WIDTH + 6)
    
    total_size_bytes = sum(item[2] for item in NEW_ARCHIVES)
    total_size_human = format_bytes(total_size_bytes)

    if NEW_ARCHIVES:
        archive_rows = "\n".join([
            # Format human size using the format_bytes function and the stored bytes
            f"{format_bytes(size_bytes):>{SIZE_WIDTH}}    {name:<{FILE_WIDTH}}" 
            for name, size_human, size_bytes in NEW_ARCHIVES
        ])
        
        total_line = f"{total_size_human:>{SIZE_WIDTH}}    {'TOTAL SIZE OF NEW ARCHIVES':<{FILE_WIDTH}}"

        archive_table = (
            "SUMMARY OF CREATED ARCHIVES (Alphabetical by filename):\n"
            f"{SEPARATOR}\n"
            f"{'SIZE':<{SIZE_WIDTH}}    {'FILENAME':<{FILE_WIDTH}}\n"
            f"{SEPARATOR}\n"
            f"{archive_rows}\n"
            f"{SEPARATOR}\n"
            f"{total_line}\n"
            f"{SEPARATOR}\n"
        )
    else:
        archive_table = "SUMMARY OF CREATED ARCHIVES (Alphabetical by filename):\n- No new archives created.\n"

    # --- 2. DISK USAGE CHECK (Compact format) ---
    disk_summary = ""
    if disk_info:
        disk_line_df = (
            f"Disk: {disk_info['mount'].split('/')[-1] if disk_info['mount'] != '/' else '/'} | "
            f"Total: {disk_info['total']} | "
            f"Used: {disk_info['used']} | "
            f"Usage: {disk_info['percent']}"
        )
        disk_line_du = f"Backup Content Size ({BACKUP_DIR}): {backup_content_size}"

        disk_summary = (
            f"DISK USAGE CHECK (on {disk_info['mount']}):\n"
            f"{SEPARATOR}\n"
            f"{disk_line_df}\n"
            f"{disk_line_du}\n"
            f"{SEPARATOR}\n"
        )
    else:
        disk_summary = "DISK USAGE CHECK:\n- Disk usage information not available.\n"

    # --- 3. RETENTION TABLE (Compact Format with Freed Space) ---
    retention_table = (
        f"RETENTION CLEANUP (Older than {DAILY_RETENTION_DAYS} days):\n"
        f"{SEPARATOR}\n"
    )
    
    RETENTION_WIDTH = FILE_WIDTH + SIZE_WIDTH + 5
    
    if DELETED_FILES:
        DELETED_FILES.sort()
        
        retention_rows = "\n".join([
            f"{name:<{RETENTION_WIDTH}}" 
            for name in DELETED_FILES
        ])
        
        freed_space_line = f"{format_bytes(DELETED_SIZE_BYTES):>{SIZE_WIDTH}}    {'TOTAL SPACE FREED':<{FILE_WIDTH}}"

        retention_table += (
            f"{'DELETED FILENAME':<{RETENTION_WIDTH}}\n"
            f"{SEPARATOR}\n"
            f"{retention_rows}\n"
            f"{SEPARATOR}\n"
            f"{freed_space_line}\n" 
            f"{SEPARATOR}\n"
        )
    else:
        retention_table += f"No files older than {DAILY_RETENTION_DAYS} days were deleted.\n{SEPARATOR}\n"
    
    
    log_body = "\n".join(LOG_MESSAGES)
    
    email_content = f"""
    Docker Stacks Backup Script Report ({status})
    
    {archive_table}

    {disk_summary}

    {retention_table}
    
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
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
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

    # Prepare list of stacks to process sequentially: (name, base_dir, path)
    stacks_to_process = []
    for stack_name in STACKS:
        stack_path = os.path.join(BASE_DIR, stack_name)
        stacks_to_process.append({
            "name": stack_name, 
            "base_dir": BASE_DIR, 
            "path": stack_path
        })

    # Add extra stack if configured
    if EXTRA_STACK_PATH:
        stacks_to_process.append({
            "name": os.path.basename(EXTRA_STACK_PATH),
            "base_dir": os.path.dirname(EXTRA_STACK_PATH),
            "path": EXTRA_STACK_PATH
        })

    # 1. PROCESS STACKS SEQUENTIALLY (Stop -> Archive -> Start)
    log("Phase 1: Processing stacks sequentially (Stop -> Archive -> Start).")
    
    for stack_info in stacks_to_process:
        stack_name = stack_info["name"]
        stack_base_dir = stack_info["base_dir"]
        stack_path = stack_info["path"]
        
        log(f"\n--- Starting backup for stack: {stack_name} ---")
        
        # 1.1 STOP
        if compose_action(stack_path, action="down"):
            # 1.2 ARCHIVE
            if create_archive(stack_name, stack_base_dir, stack_path):
                log(f"Archive created successfully for {stack_name}.")
            else:
                log(f"Archiving failed for {stack_name}. Attempting to restart.", "ERROR")
            
            # 1.3 START (Always attempt to restart if stop was successful)
            compose_action(stack_path, action="up")
        else:
            log(f"Skipping archive and start for {stack_name} due to failure or directory issue.", "WARNING")

    # 2. LOCAL CLEANUP
    log("\nPhase 2: Running local retention cleanup.")
    cleanup_local_backups()

    # 3. FINALIZATION AND NOTIFICATION
    log("\nPhase 3: Finalizing report and sending notification.")
    disk_info, backup_content_size = get_disk_usage()
    send_email_notification(disk_info, backup_content_size)

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
