# OS Patching Automation (ServiceNow + Ansible Integration)

This solution automates the OS patching of a virtual machine in Azure when triggered by an approved Change Request in ServiceNow. It fetches the Change Request, extracts target VM details, renders the Ansible inventory, patches the target host over SSH, collects patch compliance data (packages updated, reboot status, kernel versions), updates the ServiceNow ticket, and automatically closes it.

---

## 📂 Project Structure

```
solution/
├── .env.example              # Template for credentials
├── .gitignore                # Git ignore rules
├── README.md                 # This guide
├── ansible/
│   ├── patch.yml             # Ansible playbook to perform patch, check reboot, and log output
│   └── ansible.cfg           # Ansible configuration (host key checking disabled)
└── scripts/
    ├── requirements.txt      # Python dependencies
    └── patch_runner.py       # Main python automation orchestrator
```

---

## 🛠️ Step-by-Step Setup

### Step 1: Prepare ServiceNow Credentials
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your ServiceNow Personal Developer Instance (PDI) details:
   - `SNOW_INSTANCE`: your developer instance prefix (e.g., if URL is `https://dev12345.service-now.com`, use `dev12345`).
   - `SNOW_USER`: your admin user (typically `admin` or a dedicated user like `automation.bot`).
   - `SNOW_PASSWORD`: your instance password.

### Step 2: Install Python Dependencies
Install the required libraries in your local machine:
```bash
pip install -r scripts/requirements.txt
```

### Step 3: Set Up SSH Key in WSL
Ansible runs inside WSL (Linux environment) and needs your private SSH key configured:
```bash
# Create SSH directory inside WSL if it doesn't exist
mkdir -p ~/.ssh

# Copy your training key from Windows C:\Users\shivi.goyal\.ssh\ to WSL
cp /mnt/c/Users/shivi.goyal/.ssh/training_key ~/.ssh/

# Secure key permissions (required by SSH client)
chmod 600 ~/.ssh/training_key
```

### Step 4: Raise a Change Request in ServiceNow
1. Open your ServiceNow PDI in the browser.
2. Search for **Change** in the filter navigator and select **Create New** (or go to `change_request.list` -> click **New**).
3. Select **Normal** or **Standard** change.
4. Set the following fields:
   - **Short Description**: `Patch VM vm-patch-test`
   - **Description**: Add the following lines containing your target VM's details:
     ```text
     Target VM IP: <IP_OF_YOUR_AZURE_VM>
     Target VM Name: vm-patch-test
     ```
   - **State**: Set the state to **Scheduled** (`-2`) or **Implement** (`-1`) to represent that it is approved and ready for implementation.
5. Save/Submit the Change Request. Take note of the change request number (e.g. `CHG0030001`).

---

## 🚀 Running the Automation

To run the automation locally, execute the Python script:
```bash
python scripts/patch_runner.py
```

### What happens behind the scenes:
1. **Polls ServiceNow**: The script queries the Table API for any active Change Request in state **Scheduled** (`-2`) or **Implement** (`-1`) that mentions a `Target VM IP:`.
2. **Extracts VM Details**: It parses the IP address and name from the description field.
3. **Generates Inventory**: It dynamically writes `ansible/inventory.ini` pointing to the target VM using your `training_key`.
4. **Executes Ansible**: It runs the Ansible playbook (`ansible/patch.yml`) inside WSL. The playbook:
   - Captures the initial running kernel version (`uname -r`).
   - Updates the package cache and upgrades all packages (`apt-get upgrade`).
   - Checks if `/var/run/reboot-required` exists.
   - If a reboot is needed, it reboots the VM and waits for it to come back online.
   - Captures the new running kernel version (`uname -r`).
   - Exports the results to a temporary JSON report `patch_result.json`.
5. **Updates ServiceNow**:
   - Parses the JSON report.
   - Writes a compliance report containing the number of updated packages, reboot status, and before/after kernel versions to the Change Request's **Work notes**.
   - Changes the ticket state to **Review** (`state=0`).
   - Sets the ticket state to **Closed** (`state=3`), with a completion code of `successful` and the close notes.
