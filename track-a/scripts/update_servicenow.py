import os
import sys
import requests

INSTANCE = os.environ["SNOW_INSTANCE"]
AUTH = (os.environ["SNOW_USER"], os.environ["SNOW_PASSWORD"])
BASE = f"https://{INSTANCE}.service-now.com/api/now/table"
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

RITM_SYS_ID = os.environ["RITM_SYS_ID"]
VM_NAME = os.environ["VM_NAME"]
VM_IP = os.environ.get("VM_IP", "")
VM_SIZE = os.environ.get("VM_SIZE", "")
VM_LOCATION = os.environ.get("VM_LOCATION", "")


def create_ci():
    body = {
        "name": VM_NAME,
        "ip_address": VM_IP,
        "short_description": f"Provisioned via training pipeline ({VM_SIZE} in {VM_LOCATION})",
        "operational_status": "1",
    }
    r = requests.post(f"{BASE}/cmdb_ci_vm_instance", auth=AUTH, headers=HEADERS, json=body)
    r.raise_for_status()
    ci = r.json()["result"]
    return ci


def close_ritm():
    notes = (
        f"VM provisioned automatically.\n"
        f"Name: {VM_NAME}\nPrivate IP: {VM_IP}\nSize: {VM_SIZE}\nRegion: {VM_LOCATION}\n"
        f"CMDB CI created. Pipeline: GitHub Actions."
    )
    body = {
        "work_notes": notes,
        "state": "3",
    }
    r = requests.patch(f"{BASE}/sc_req_item/{RITM_SYS_ID}", auth=AUTH, headers=HEADERS, json=body)
    r.raise_for_status()


def main():
    try:
        create_ci()
        close_ritm()
    except requests.HTTPError as e:
        sys.exit(1)


if __name__ == "__main__":
    main()
