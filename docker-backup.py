#!/usr/bin/env python3

import subprocess
import os
import sys
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
# List of stacks located in BASE_DIR
STACKS = ["stack1", "stack2", "stack3", "stack4", "stack5"]

# Main data paths
BASE_DIR = "/opt/stacks"
BACKUP_DIR = "/var/backups/docker"

# Special path for the external stack (e.g., Dockge, Portainer, etc.)
EXTRA_STACK_PATH = "/opt/dockge"

# Backup target paths (will be created automatically)
EXTRA_STACK_BACKUP_TARGET = os.path.join(BACKUP_DIR, os.path.basename(EXTRA_STACK_PATH))
STACKS_BACKUP_TARGET = os.path.join(BACKUP_DIR, "stacks")

LOG_FILE = "/var/log/docker-backup.log"

# Email Configuration (PLEASE REPLACE PLACEHOLDERS)
SMTP_SERVER = 'in-v3.mailjet.com'
SMTP_PORT = 587
SMTP_USER = 'YOUR_API_KEY'
SMTP_PASS = 'YOUR_API_SECRET'
SENDER_EMAIL = 'sender@your-domain.com'
RECEIVER_EMAIL = 'recipient@email.com'

SUBJECT_TAG = "[DOCKER-BACKUP]"

DAILY_RETENTION_DAYS = 28 # Local retention period

# GLOBAL STATE VARIABLES
GLOBAL_EXIT_CODE = 0
ARCHIVE_PATHS = []
LOG_MESSAGES = []
FILES_DELETED_COUNT = 0 
# ----------------------

def log_message(message, is_error=False):
    """Writes a message to the log file and stores it in memory."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    log_line = f"[{timestamp}] {message}"
    
    if is_error:
        global GLOBAL_EXIT_CODE
        GLOBAL_EXIT_CODE = 1
        log_line = f"❌ {log_line}"
        
    LOG_MESSAGES.append(log_line)
    
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + "\n")

def run_command(command, cwd=None, error_msg="Command failed"):
    """Executes a shell command and logs the output."""
    try:
        result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True, encoding='utf-8')
        for line in result.stdout.strip().split('\n'):
            if line:
                log_message(f"stdout: {line}")
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"🛑 {error_msg} ({' '.join(command)}):", is_error=True)
        log_message(f"stdout: {e.stdout.strip()}", is_error=True)
        log_message(f"stderr: {e.stderr.strip()}", is_error=True)
        return False
    except FileNotFoundError:
        log_message(f"🛑 Command not found: {command[0]}", is_error=True)
        return False

def stop_stack(stack_path):
    """Stops a Docker stack using docker compose down."""
    stack_name = os.path.basename(stack_path)
    log_message(f"--- 🛑 Stopping: {stack_name} ---")
    
    if not os.path.isdir(stack_path):
        log_message(f"⚠️ ERROR: Directory {stack_path} does not exist. Skipping.", is_error=True)
        return
        
    run_command(["docker", "compose", "down"], cwd=stack_path, 
                error_msg=f"'docker compose down' for {stack_name} failed")
    
def start_stack(stack_path):
    """Starts a Docker stack using docker compose up -d."""
    stack_name = os.path.basename(stack_path)
    log_message(f"--- ▶️ Starting: {stack_name} ---")
    
    if not os.path.isdir(stack_path):
        log_message(f"⚠️ ERROR: Directory {stack_path} does not exist. Skipping.", is_error=True)
        return
        
    run_command(["docker", "compose", "up", "-d"], cwd=stack_path, 
                error_msg=f"'docker compose up -d' for {stack_name} failed")

def compress_and_copy(source_path, target_dir):
    """Compresses a folder and saves it with a timestamp using Zstandard."""
    name = os.path.basename(source_path)
    datetime_stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') 
    archive_name = f"{name}_{datetime_stamp}.tar.zst" 
    target_file = os.path.join(target_dir, archive_name)

    log_message(f"--- 📦 Backup: {name} (Source: {source_path}) ---")

    # Use Zstandard compression
    if run_command(["tar", "-c", "-I", "zstd", "-f", target_file, "-C", os.path.dirname(source_path), name],
                   error_msg=f"Compression of {name} failed"):
        log_message(f"✅ SUCCESS: {name} backed up to {target_file}")
        ARCHIVE_PATHS.append(target_file)

def cleanup_local():
    """Deletes local archives older than DAILY_RETENTION_DAYS."""
    global FILES_DELETED_COUNT 
    FILES_DELETED_COUNT = 0 
    
    log_message(f"\n--- 4. LOCAL CLEANUP (Older than {DAILY_RETENTION_DAYS} days) ---")
    
    # Only search for Zstandard files
    file_patterns = ["*.tar.zst"] 
    
    for target in [STACKS_BACKUP_TARGET, EXTRA_STACK_BACKUP_TARGET]:
        log_message(f"  -> Cleaning up {target}:")
        
        try:
            total_deleted = 0
            
            for pattern in file_patterns:
                # Find files older than X days
                find_command = ["find", target, "-type", "f", "-name", pattern, "-mtime", f"+{DAILY_RETENTION_DAYS}", "-print0"]
                
                process = subprocess.Popen(find_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                
                # Use xargs -r to prevent "rm: missing operand" when no files are found
                delete_command = ["xargs", "-0", "-r", "rm", "-v"]
                
                delete_process = subprocess.run(delete_command, stdin=process.stdout, capture_output=True, text=True, encoding='utf-8')
                
                process.stdout.close()
                
                if process.wait() != 0 or delete_process.returncode != 0:
                    if delete_process.stderr.strip():
                        log_message(f"⚠️ WARNING: Cleanup with pattern {pattern} in {target} failed or had errors.", is_error=False)
                        log_message(f"Stderr: {delete_process.stderr.strip()}", is_error=False)
                    
                deleted_list = delete_process.stdout.strip().split('\n')
                
                if deleted_list and deleted_list[0]:
                    for deleted_file in deleted_list:
                        log_message(f"Deleted: {deleted_file.split(' ', 1)[-1]}") 
                    
                    total_deleted += len(deleted_list)
            
            if total_deleted > 0:
                FILES_DELETED_COUNT += total_deleted
                log_message(f"  -> {total_deleted} old archives deleted in total.")
            else:
                # Log entry for when no files were deleted
                log_message("  -> No old archives found.") 

        except Exception as e:
            log_message(f"🛑 FATAL ERROR during cleanup: {e}", is_error=True)

def get_disk_space_info():
    """Retrieves human-readable disk usage (Total, Used, Percentage) for the backup directory."""
    try:
        # Use df -h to get human-readable disk usage
        df_command = ["df", "-h", BACKUP_DIR]
        result = subprocess.run(df_command, check=True, capture_output=True, text=True, encoding='utf-8')
        
        data_line = result.stdout.strip().split('\n')[-1]
        columns = data_line.split()
        
        # Columns: Filesystem, Size, Used, Avail, Use%, Mounted on
        if len(columns) >= 6:
            size = columns[1]
            used = columns[2]
            percent = columns[4]
            mount_point = columns[5]
            
            return f"Disk: {mount_point} | Total: {size} | Used: {used} | Usage: {percent}"
        else:
            return "Could not parse comprehensive disk space information."

    except Exception as e:
        return f"ERROR retrieving disk space: {e}"

def create_summary():
    """Creates a formatted, alphabetized summary of the new archives, including disk space info."""
    
    summary_lines = ["\nSUMMARY OF CREATED ARCHIVES (Alphabetical by filename):", 
                     "--------------------------------------------------------------------", 
                     "SIZE\tFILENAME", 
                     "--------------------------------------------------------------------"]
    
    try:
        if ARCHIVE_PATHS:
            # Get human-readable size for all new archives
            du_command = ["du", "-h"] + ARCHIVE_PATHS
            result = subprocess.run(du_command, check=True, capture_output=True, text=True, encoding='utf-8')
            
            du_output_lines = result.stdout.strip().split('\n')
            sorted_lines = sorted(du_output_lines, key=lambda line: line.split('\t')[-1])

            summary_lines.extend(sorted_lines)
        else:
            summary_lines.append("No new archives were created.")

    except Exception as e:
        summary_lines.append(f"ERROR creating archive summary: {e}")
        
    summary_lines.append("--------------------------------------------------------------------\n")
    
    # --- ADD DISK SPACE INFORMATION ---
    disk_info = get_disk_space_info()
    summary_lines.append(f"DISK USAGE CHECK (on {BACKUP_DIR}):")
    summary_lines.append(disk_info)
    summary_lines.append("--------------------------------------------------------------------\n")

    return "\n".join(summary_lines)

def send_email_notification(subject_raw, body):
    """Sends an email notification with the full log content."""
    
    try:
        hostname = subprocess.check_output(['hostname']).decode('utf-8').strip()
    except:
        hostname = "UNKNOWN_HOST"
        
    final_subject = f"{SUBJECT_TAG} {subject_raw} on {hostname}"

    try:
        msg = MIMEMultipart()
        msg['Subject'] = final_subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        
        # Attach the body (summary) and the full log of the run
        full_body = body + "\n\n" + ("\n".join(LOG_MESSAGES))
        msg.attach(MIMEText(full_body, 'plain'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            
        log_message("✅ Email sent successfully.")
        return True
        
    except Exception as e:
        log_message(f"🛑 ERROR sending email: {e}", is_error=True)
        return False


def main():
    """Main logic of the backup script."""
    
    # 0. Initialization
    if not os.path.exists(os.path.dirname(LOG_FILE)):
        os.makedirs(os.path.dirname(LOG_FILE))
    
    with open(LOG_FILE, 'a') as f:
        f.write("\n" + "="*50 + "\n")
        f.write("--- DOCKER STACK BACKUP PROCESS START ---\n")
        f.write(f"Date and Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*50 + "\n")
        
    # Ensure backup target directories exist
    for d in [EXTRA_STACK_BACKUP_TARGET, STACKS_BACKUP_TARGET]:
        os.makedirs(d, exist_ok=True)
        
    # --- 1. STOPPING ---
    log_message("\n--- 1. STOP ALL STACKS ---")
    for stack in STACKS:
        stop_stack(os.path.join(BASE_DIR, stack))
    stop_stack(EXTRA_STACK_PATH)

    # --- 2. BACKUP ---
    log_message("\n--- 2. BACKUP DATA ---")
    for stack in STACKS:
        compress_and_copy(os.path.join(BASE_DIR, stack), STACKS_BACKUP_TARGET)
    compress_and_copy(EXTRA_STACK_PATH, EXTRA_STACK_BACKUP_TARGET)

    # --- 3. STARTING ---
    log_message("\n--- 3. START ALL STACKS ---")
    start_stack(EXTRA_STACK_PATH)
    for stack in STACKS:
        start_stack(os.path.join(BASE_DIR, stack))

    # --- 4. LOCAL CLEANUP ---
    cleanup_local()

    # --- 5. FINALIZATION & NOTIFICATION ---
    summary = create_summary()
    log_message(summary)
    
    if GLOBAL_EXIT_CODE == 0:
        mail_subject = "SUCCESS: Docker Backup completed successfully" 
        mail_body = f"The daily Docker backup process finished successfully.\n\n{summary}"
    else:
        mail_subject = "FAILURE: Docker Backup finished with errors"
        mail_body = "ATTENTION: The daily Docker backup process finished with errors.\n\n"
        mail_body += "Please check the full log in this email for details."

    send_email_notification(mail_subject, mail_body)

    # --- 6. FINAL MESSAGE ---
    log_message("="*50)
    if GLOBAL_EXIT_CODE == 0:
        log_message("🎉 PROCESS COMPLETED: All steps executed successfully.")
        log_message("Exit Code: 0")
    else:
        log_message("❌ PROCESS COMPLETED WITH ERRORS.")
        log_message("Exit Code: 1")
    log_message("="*50)

    sys.exit(GLOBAL_EXIT_CODE)


if __name__ == "__main__":
    main()
