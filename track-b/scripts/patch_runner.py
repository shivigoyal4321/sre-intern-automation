#!/usr/bin/env python3
"""patch_runner.py — Automated OS Patching & ServiceNow Integration.

1. Polls ServiceNow for a Change Request in state Scheduled (-2) or Implement (-1).
2. Extracts the target VM's IP address and name from the ticket description.
3. Generates an Ansible inventory.ini.
4. Runs the Ansible playbook in WSL.
5. Collects the JSON compliance summary.
6. Updates the ServiceNow Change Request with work notes and closes it.
"""
import os
import sys
import json
import subprocess
from datetime import datetime
import requests
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()

INSTANCE = os.environ.get("SNOW_INSTANCE")
USER = os.environ.get("SNOW_USER")
PASSWORD = os.environ.get("SNOW_PASSWORD")

if not INSTANCE or not USER or not PASSWORD:
    print("ERROR: Missing SNOW_INSTANCE, SNOW_USER, or SNOW_PASSWORD in environment/dotenv.")
    sys.exit(1)

BASE_URL = f"https://{INSTANCE}.service-now.com/api/now/table"
AUTH = (USER, PASSWORD)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def fetch_change_request():
    """Finds the first active, scheduled Change Request containing target IP details."""
    print("Polling ServiceNow for active Change Requests in Scheduled (-2) or Implement (-1) state...")
    # Query: active=true, state is Scheduled (-2) or Implement (-1), description contains "Target VM IP:"
    query = "active=true^stateIN-2,-1^descriptionLIKETarget VM IP:"
    params = {
        "sysparm_query": query,
        "sysparm_limit": 1,
        "sysparm_display_value": "true"
    }
    
    r = requests.get(f"{BASE_URL}/change_request", auth=AUTH, params=params, headers=HEADERS)
    r.raise_for_status()
    results = r.json().get("result", [])
    
    if not results:
        print("No pending Change Requests found matching the query.")
        return None
        
    return results[0]


def parse_vm_details(description):
    """Extract IP and name from description text."""
    ip = None
    name = "target-vm"
    
    for line in description.splitlines():
        if "Target VM IP:" in line:
            ip = line.split("Target VM IP:")[1].strip()
        if "Target VM Name:" in line:
            name = line.split("Target VM Name:")[1].strip()
            
    return ip, name


def write_inventory(ip, name):
    """Writes the ansible/inventory.ini file dynamically."""
    inventory_content = f"""[target]
{name} ansible_host={ip} ansible_user=azureuser ansible_ssh_private_key_file=~/.ssh/training_key
"""
    # Ensure ansible directory exists
    os.makedirs("ansible", exist_ok=True)
    with open("ansible/inventory.ini", "w") as f:
        f.write(inventory_content)
    print(f"Generated ansible/inventory.ini for host {name} ({ip})")


def run_ansible():
    """Invokes Ansible playbook using WSL."""
    print("Launching Ansible patching playbook in WSL...")
    # Run inside WSL Ubuntu since Ansible runs on Linux control node
    cmd = [
        "wsl", "ansible-playbook", 
        "-i", "ansible/inventory.ini", 
        "ansible/patch.yml"
    ]
    
    # Run the command and print output in real-time
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        print(line, end="")
    
    process.wait()
    if process.returncode != 0:
        raise Exception(f"Ansible playbook execution failed with exit code {process.returncode}")
    print("Ansible playbook execution completed successfully.")


def read_compliance_report():
    """Reads the JSON summary file created by the Ansible playbook."""
    report_path = "patch_result.json"
    if not os.path.exists(report_path):
        raise Exception("Ansible did not write the patch_result.json report file.")
        
    with open(report_path, "r") as f:
        return json.load(f)


def update_change_request(sys_id, number, report):
    """Updates ServiceNow ticket with work notes and moves it to closed."""
    print(f"Writing compliance report back to ServiceNow Change Request {number}...")
    
    reboot_str = "Yes" if report.get("reboot_required") else "No"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    notes = (
        f"✅ OS Patching Compliance Summary:\n"
        f"Run Timestamp: {timestamp}\n"
        f"Packages Updated: {report.get('packages_updated')}\n"
        f"Reboot Performed: {reboot_str}\n"
        f"Kernel Version: {report.get('kernel_before')} ➔ {report.get('kernel_after')}\n"
        f"Automation Tool: Ansible + Python Runner"
    )
    
    # ServiceNow change closed states:
    # state = "3" (Closed), close_code = "successful", close_notes = description of completion.
    body = {
        "work_notes": notes,
        "state": "0",  # First move to Review state (0)
    }
    
    # 1. Update to Review state
    r = requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=body, headers=HEADERS)
    r.raise_for_status()
    print("Moved Change Request to Review state.")
    
    # 2. Update to Closed state (typically ServiceNow requires review, then close)
    close_body = {
        "state": "3",  # 3 = Closed
        "close_code": "successful",
        "close_notes": f"OS patching successfully applied. Kernel updated from {report.get('kernel_before')} to {report.get('kernel_after')}."
    }
    r = requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=close_body, headers=HEADERS)
    r.raise_for_status()
    print(f"Successfully closed Change Request {number}!")
    
    
def main():
    change = fetch_change_request()
    if not change:
        print("No work to perform. Exiting.")
        return
        
    sys_id = change["sys_id"]
    number = change["number"]
    description = change.get("description", "")
    
    print(f"Processing Change Request {number} (SysID: {sys_id})...")
    ip, name = parse_vm_details(description)
    
    if not ip:
        print(f"ERROR: Could not parse VM IP address from description of {number}.")
        sys.exit(1)
        
    print(f"Target VM parsed: {name} at IP {ip}")
    
    try:
        # Step 1: Write inventory
        write_inventory(ip, name)
        
        # Step 2: Run Ansible
        run_ansible()
        
        # Step 3: Parse results
        report = read_compliance_report()
        
        # Step 4: Update SNOW
        update_change_request(sys_id, number, report)
        
        # Cleanup report file
        if os.path.exists("patch_result.json"):
            os.remove("patch_result.json")
            
    except Exception as e:
        print(f"ERROR during execution: {e}", file=sys.stderr)
        # Attempt to post failure work notes
        try:
            fail_body = {"work_notes": f"❌ OS Patching automation failed:\n{e}"}
            requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=fail_body, headers=HEADERS)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
