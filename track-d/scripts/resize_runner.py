import os
import sys
import json
import subprocess
import requests
import platform
from dotenv import load_dotenv

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

# On Windows, Azure CLI is installed as 'az.cmd' (a batch file).
# Python's subprocess.run needs 'az.cmd' instead of 'az' to execute it successfully on Windows.
AZ_CMD = "az.cmd" if platform.system() == "Windows" else "az"

# Allowed VM Sizes for cost safety
ALLOWED_SIZES = ["Standard_B1s", "Standard_B2s"]


def fetch_resize_request():
    """Finds the first active Change Request containing resize details in states: New, Assess, Scheduled, Implement."""
    print("Polling ServiceNow for active VM Resize Change Requests...")
    # Query: active=true, state in New (-5), Assess (-4), Scheduled (-2), Implement (-1)
    query = "active=true^stateIN-5,-4,-2,-1^short_descriptionLIKEResize VM"
    params = {
        "sysparm_query": query,
        "sysparm_limit": 1,
        "sysparm_display_value": "true"
    }
    r = requests.get(f"{BASE_URL}/change_request", auth=AUTH, params=params, headers=HEADERS)
    r.raise_for_status()
    results = r.json().get("result", [])
    if not results:
        print("No pending VM Resize Change Requests found.")
        return None
    return results[0]


def parse_resize_details(description):
    """Extract VM Name and Target Size from description text."""
    vm_name = None
    target_size = None
    
    for line in description.splitlines():
        if "Target VM Name:" in line:
            vm_name = line.split("Target VM Name:")[1].strip()
        if "Target VM Size:" in line:
            target_size = line.split("Target VM Size:")[1].strip()
            
    return vm_name, target_size


def get_current_vm_size(rg_name, vm_name):
    """Queries Azure for the current VM size."""
    print(f"Checking current size of VM '{vm_name}' in Azure...")
    cmd = [AZ_CMD, "vm", "show", "-g", rg_name, "-n", vm_name, "--query", "hardwareProfile.vmSize", "-o", "tsv"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to query VM size: {result.stderr.strip()}")
    return result.stdout.strip()


def resize_vm(rg_name, vm_name, target_size):
    """Performs the deallocate -> resize -> start sequence in Azure."""
    # 1. Deallocate
    print(f"Deallocating VM '{vm_name}' (required before resizing)...")
    cmd = [AZ_CMD, "vm", "deallocate", "-g", rg_name, "-n", vm_name]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to deallocate VM: {result.stderr.strip()}")

    # 2. Resize
    print(f"Resizing VM '{vm_name}' to '{target_size}'...")
    cmd = [AZ_CMD, "vm", "resize", "-g", rg_name, "-n", vm_name, "--size", target_size]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to resize VM: {result.stderr.strip()}")

    # 3. Start
    print(f"Restarting VM '{vm_name}'...")
    cmd = [AZ_CMD, "vm", "start", "-g", rg_name, "-n", vm_name]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to start VM: {result.stderr.strip()}")


def update_cmdb_ci(vm_name, new_size):
    """Queries for the VM record in the CMDB and updates its size attribute."""
    print(f"Updating CMDB record for VM '{vm_name}' size attribute to '{new_size}'...")
    query = f"name={vm_name}"
    params = {"sysparm_query": query, "sysparm_limit": 1}
    r = requests.get(f"{BASE_URL}/cmdb_ci_vm_instance", auth=AUTH, params=params, headers=HEADERS)
    if r.status_code != 200:
        print("Failed to query CMDB CI table.")
        return False
    results = r.json().get("result", [])
    if not results:
        print(f"No CMDB CI record found with name '{vm_name}'. Skipping CMDB update.")
        return False
    sys_id = results[0]["sys_id"]
    payload = {"size": new_size}
    r = requests.patch(f"{BASE_URL}/cmdb_ci_vm_instance/{sys_id}", auth=AUTH, json=payload, headers=HEADERS)
    if r.status_code == 200:
        print(f"Successfully updated CMDB size attribute (SysID: {sys_id}).")
        return True
    else:
        print(f"Failed to update CMDB record: {r.text}")
        return False


def close_change_request(sys_id, logs, status="successful"):
    """Moves Change Request state to Review and then closes it."""
    print("Updating ServiceNow Change Request with completion logs...")
    notes = f"VM Resize process completed.\n\nVerification details:\n{logs}"
    payload = {
        "work_notes": notes,
        "state": "0"  # Move to Review first
    }
    requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=payload, headers=HEADERS)

    close_payload = {
        "state": "3",  # Move to Closed
        "close_code": status,
        "close_notes": f"VM successfully resized and CMDB record updated."
    }
    r = requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=close_payload, headers=HEADERS)
    return r.status_code == 200


def main():
    change = fetch_resize_request()
    if not change:
        print("No active resize change requests found. Exiting.")
        sys.exit(0)

    sys_id = change["sys_id"]
    number = change["number"]
    description = change.get("description", "")
    vm_name, target_size = parse_resize_details(description)

    if not vm_name or not target_size:
        print(f"ERROR: Could not parse VM Name or Target Size from description of Change Request {number}.")
        sys.exit(1)

    print(f"Processing Resize Request {number} for VM: {vm_name} to size: {target_size}")

    # Cost-Safety validation
    if target_size not in ALLOWED_SIZES:
        error_msg = f"Forbidden target size '{target_size}'. Only Standard_B1s and Standard_B2s are allowed for cost safety."
        print(f"ERROR: {error_msg}")
        # Log failure notes in ServiceNow and exit
        try:
            fail_body = {"work_notes": f"❌ VM Resize failed: {error_msg}"}
            requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=fail_body, headers=HEADERS)
        except Exception:
            pass
        sys.exit(1)

    rg_name = f"rg-{vm_name}"

    try:
        # Step 1: Check current VM size
        current_size = get_current_vm_size(rg_name, vm_name)
        print(f"Current size of VM in Azure is: {current_size}")

        # Idempotency check: Already at target size
        if current_size.lower() == target_size.lower():
            log_msg = f"Idempotent Run: VM is already at the target size '{target_size}'."
            print(log_msg)
            update_cmdb_ci(vm_name, target_size)
            close_change_request(sys_id, log_msg)
            print(f"Successfully completed Change Request {number} (No-op).")
            return

        # Step 2: Perform resize in Azure (deallocate -> resize -> start)
        resize_vm(rg_name, vm_name, target_size)

        # Step 3: Verify the new size
        new_size = get_current_vm_size(rg_name, vm_name)
        print(f"New size verified in Azure: {new_size}")

        if new_size.lower() != target_size.lower():
            raise Exception(f"Validation failed: Size is currently '{new_size}' instead of expected '{target_size}'.")

        # Step 4: Update CMDB record
        update_cmdb_ci(vm_name, target_size)

        # Step 5: Close Change Request
        log_msg = f"Successfully resized VM from {current_size} -> {new_size}."
        if close_change_request(sys_id, log_msg):
            print(f"Successfully closed Change Request {number}!")

    except Exception as e:
        print(f"ERROR during VM resize execution: {e}", file=sys.stderr)
        # Post failure work notes to ServiceNow
        try:
            fail_body = {"work_notes": f"❌ VM Resize automation failed:\n{e}"}
            requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=fail_body, headers=HEADERS)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
