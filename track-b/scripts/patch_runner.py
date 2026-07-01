import json
import os
import subprocess
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

INSTANCE = os.environ["SNOW_INSTANCE"]
AUTH = (os.environ["SNOW_USER"], os.environ["SNOW_PASSWORD"])
BASE = f"https://{INSTANCE}.service-now.com/api/now/table"
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def find_change_request():
    params = {
        "sysparm_query": "stateIN-2,-1^short_descriptionLIKEPatch VM",
        "sysparm_limit": 1,
    }
    r = requests.get(f"{BASE}/change_request", auth=AUTH, headers=HEADERS, params=params)
    r.raise_for_status()
    result = r.json()["result"]
    if not result:
        return None
    return result[0]


def extract_vm_details(change_req):
    desc = change_req.get("description", "")
    ip = ""
    name = ""
    for line in desc.split("\n"):
        if "Target VM IP:" in line:
            ip = line.split("Target VM IP:")[1].strip()
        elif "Target VM Name:" in line:
            name = line.split("Target VM Name:")[1].strip()
    return name, ip


def generate_inventory(vm_name, vm_ip):
    inventory_content = f"""[all]
{vm_name} ansible_host={vm_ip} ansible_user=ubuntu ansible_ssh_pass=abcd
"""
    os.makedirs("ansible", exist_ok=True)
    with open("ansible/inventory.ini", "w") as f:
        f.write(inventory_content)


def run_ansible_playbook():
    cmd = [
        "wsl",
        "ansible-playbook",
        "-i",
        "inventory.ini",
        "patch.yml"
    ]
    res = subprocess.run(cmd, cwd="ansible", capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        sys.exit(1)


def read_compliance_report():
    with open("patch_result.json", "r") as f:
        return json.load(f)


def update_change_request(sys_id, result):
    notes = (
        "OS Patching Compliance Summary:\n"
        f"Packages Updated: {result.get('packages_updated', 0)}\n"
        f"Reboot Performed: {result.get('reboot_required', False)}\n"
        f"Kernel Version: {result.get('kernel_before')} -> {result.get('kernel_after')}\n"
        "Automation Tool: Ansible + Python Runner"
    )
    body = {
        "work_notes": notes,
        "state": "3",
        "close_code": "successful",
        "close_notes": f"OS patching successfully applied. Kernel updated from {result.get('kernel_before')} to {result.get('kernel_after')}."
    }
    r = requests.patch(f"{BASE}/change_request/{sys_id}", auth=AUTH, headers=HEADERS, json=body)
    r.raise_for_status()


def main():
    change_req = find_change_request()
    if not change_req:
        sys.exit(0)

    sys_id = change_req["sys_id"]
    vm_name, vm_ip = extract_vm_details(change_req)
    if not vm_ip:
        sys.exit(1)

    generate_inventory(vm_name, vm_ip)
    run_ansible_playbook()
    result = read_compliance_report()
    update_change_request(sys_id, result)


if __name__ == "__main__":
    main()
