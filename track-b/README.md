# OS Patching Automation

This repository automates the patching of a Linux VM triggered by a ServiceNow Change Request (CHG).

## Requirements

- Python 3.x
- Ansible (installed in WSL)
- requests
- python-dotenv

Install python dependencies:
```bash
pip install -r scripts/requirements.txt
```

## Solution Files

- `scripts/patch_runner.py`: Polls ServiceNow for active Change Requests, parses the VM details, generates Ansible inventory, executes the playbook in WSL, reads compliance reports, and closes the ticket in ServiceNow.
- `ansible/patch.yml`: Playbook to retrieve kernel version, upgrade packages via apt, check if reboot is needed, reboot, and write a compliance summary.
- `ansible/ansible.cfg`: Configuration to skip host key checking and define inventory path.

## How to Run

1. Define environment variables in `.env`:
   ```ini
   SNOW_INSTANCE=your_instance_prefix
   SNOW_USER=your_username
   SNOW_PASSWORD=your_password
   ```
2. Run the orchestrator:
   ```bash
   python scripts/patch_runner.py
   ```
