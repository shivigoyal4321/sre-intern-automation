import json
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

INSTANCE = os.environ["SNOW_INSTANCE"]
AUTH = (os.environ["SNOW_USER"], os.environ["SNOW_PASSWORD"])
RITM_NUMBER = os.environ["RITM_NUMBER"]
BASE = f"https://{INSTANCE}.service-now.com/api/now/table"


def get_ritm():
    params = {
        "sysparm_query": f"number={RITM_NUMBER}",
        "sysparm_limit": 1,
        "sysparm_display_value": "true",
    }
    r = requests.get(f"{BASE}/sc_req_item", auth=AUTH, params=params,
                     headers={"Accept": "application/json"})
    r.raise_for_status()
    result = r.json()["result"]
    if not result:
        sys.exit(1)
    return result[0]


def get_variables(ritm_sys_id):
    r = requests.get(
        f"{BASE}/sc_item_option_mtom",
        auth=AUTH,
        params={
            "sysparm_query": f"request_item={ritm_sys_id}",
            "sysparm_fields": "sc_item_option.item_option_new.name,sc_item_option.value",
            "sysparm_display_value": "true",
        },
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    variables = {}
    for row in r.json()["result"]:
        name = row.get("sc_item_option.item_option_new.name")
        value = row.get("sc_item_option.value")
        if name:
            variables[name] = value
    return variables


def main():
    ritm = get_ritm()
    sys_id = ritm["sys_id"]

    vm_name = os.environ.get("VM_NAME") or ""
    vm_size = os.environ.get("VM_SIZE") or ""
    region = os.environ.get("REGION") or ""

    if not vm_name:
        vars_ = get_variables(sys_id)
        vm_name = vars_.get("vm_name") or ""
        vm_size = vm_size or vars_.get("vm_size") or ""
        region = region or vars_.get("region") or ""

    vm_name = vm_name or f"vm-{RITM_NUMBER.lower()}"
    vm_size = vm_size or "Standard_B1s"
    region = region or "centralindia"

    tfvars = {"vm_name": vm_name, "vm_size": vm_size, "region": region}
    with open("terraform/terraform.tfvars.json", "w") as f:
        json.dump(tfvars, f, indent=2)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"ritm_sys_id={sys_id}\n")
            f.write(f"vm_name={vm_name}\n")


if __name__ == "__main__":
    main()
