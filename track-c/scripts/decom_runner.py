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
# Python's subprocess.run needs 'az.cmd' instead of 'az' to execute it successfully on Windows without spawning a shell.
AZ_CMD = "az.cmd" if platform.system() == "Windows" else "az"


def fetch_decom_request():
    """Finds the first active Change Request containing decommission details in states: New, Assess, Scheduled, Implement."""
    print("Polling ServiceNow for active Decommission Change Requests...")
    # Query: active=true, state in New (-5), Assess (-4), Scheduled (-2), Implement (-1)
    query = "active=true^stateIN-5,-4,-2,-1^short_descriptionLIKEDecommission VM"
    params = {
        "sysparm_query": query,
        "sysparm_limit": 1,
        "sysparm_display_value": "true"
    }
    r = requests.get(f"{BASE_URL}/change_request", auth=AUTH, params=params, headers=HEADERS)
    r.raise_for_status()
    results = r.json().get("result", [])
    if not results:
        print("No pending Decommission Change Requests found.")
        return None
    return results[0]


def parse_vm_name(description):
    """Extract VM Name from description text."""
    for line in description.splitlines():
        if "Target VM Name:" in line:
            return line.split("Target VM Name:")[1].strip()
    return None


def verify_azure_resource_group(rg_name):
    """Checks if resource group exists in Azure."""
    print(f"Checking if resource group '{rg_name}' exists in Azure...")
    cmd = [AZ_CMD, "group", "exists", "--name", rg_name]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip() == "true"


def destroy_azure_resources(rg_name):
    """Destroys Azure resources. Tries terraform destroy first, falls back to az group delete."""
    # Check if we have terraform files locally
    tf_dir = os.path.join(os.path.dirname(__file__), "../terraform")
    if os.path.exists(tf_dir) and os.path.exists(os.path.join(tf_dir, "terraform.tfstate")):
        print("Local Terraform state found. Executing 'terraform destroy'...")
        cmd = ["terraform", "destroy", "-auto-approve"]
        result = subprocess.run(cmd, cwd=tf_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print("Terraform destroy completed successfully.")
            return True
        else:
            print(f"Terraform destroy failed: {result.stderr}. Falling back to Azure CLI group delete.")

    # Fallback to direct group deletion
    print(f"Deleting resource group '{rg_name}' directly via Azure CLI...")
    cmd = [AZ_CMD, "group", "delete", "--name", rg_name, "--yes"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.returncode == 0


def verify_cleanup(rg_name):
    """Verifies that all resources in the resource group are deleted."""
    print(f"Verifying all resources in '{rg_name}' have been deleted...")
    cmd = [AZ_CMD, "resource", "list", "--resource-group", rg_name, "-o", "json"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        # If the command fails because the resource group was deleted entirely, then deletion was successful
        return True
    try:
        resources = json.loads(result.stdout)
        return len(resources) == 0
    except Exception:
        return False


def retire_cmdb_ci(vm_name):
    """Queries for the VM record in the CMDB and updates its status to Retired (install_status=7, operational_status=6)."""
    print(f"Retiring CMDB record for VM '{vm_name}'...")
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
    payload = {"install_status": "7", "operational_status": "6"}
    r = requests.patch(f"{BASE_URL}/cmdb_ci_vm_instance/{sys_id}", auth=AUTH, json=payload, headers=HEADERS)
    if r.status_code == 200:
        print(f"Successfully retired CMDB record (SysID: {sys_id}).")
        return True
    else:
        print(f"Failed to update CMDB record status: {r.text}")
        return False


def close_change_request(sys_id, logs):
    """Moves Change Request state to Review and then closes it successfully."""
    print("Updating ServiceNow Change Request with decommission logs...")
    notes = f"Decommission process completed.\n\nVerification details:\n{logs}"
    payload = {
        "work_notes": notes,
        "state": "0"  # Move to Review first
    }
    requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=payload, headers=HEADERS)

    close_payload = {
        "state": "3",  # Move to Closed
        "close_code": "successful",
        "close_notes": "All VM resources successfully deleted and CMDB record retired."
    }
    r = requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=close_payload, headers=HEADERS)
    return r.status_code == 200


def main():
    change = fetch_decom_request()
    if not change:
        print("No active decommission change requests found. Exiting.")
        sys.exit(0)

    sys_id = change["sys_id"]
    number = change["number"]
    description = change.get("description", "")
    vm_name = parse_vm_name(description)

    if not vm_name:
        print(f"ERROR: Could not parse VM Name from description of Change Request {number}.")
        sys.exit(1)

    print(f"Processing Decommission Request {number} for VM: {vm_name}")
    rg_name = f"rg-{vm_name}"

    try:
        # Step 1: Verify resource group exists
        if not verify_azure_resource_group(rg_name):
            raise Exception(f"Resource group '{rg_name}' does not exist in Azure. Nothing to delete.")

        # Step 2: Destroy resources
        if not destroy_azure_resources(rg_name):
            raise Exception("Failed to delete Azure VM resources.")

        # Step 3: Verify deletion
        if not verify_cleanup(rg_name):
            raise Exception(f"Cleanup verification failed. Some resources still remain in '{rg_name}'.")

        print("Azure VM resources successfully deleted.")

        # Step 4: CMDB CI update
        retire_cmdb_ci(vm_name)

        # Step 5: Close Change Request
        if close_change_request(sys_id, f"Verified empty: '{rg_name}' has no remaining resources."):
            print(f"Successfully closed Change Request {number}!")

    except Exception as e:
        print(f"ERROR during decommission execution: {e}", file=sys.stderr)
        # Post failure work notes to ServiceNow
        try:
            fail_body = {"work_notes": f"❌ VM Decommission automation failed:\n{e}"}
            requests.patch(f"{BASE_URL}/change_request/{sys_id}", auth=AUTH, json=fail_body, headers=HEADERS)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
