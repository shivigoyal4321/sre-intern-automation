# VM Resize Automation

This script automates the process of resizing a running Azure VM when triggered by an approved ServiceNow Change Request. It validates the request, checks the VM size in Azure, safely deallocates the VM, changes the SKU (between `Standard_B1s` and `Standard_B2s` for cost safety), restarts the VM, verifies the change in Azure, updates the size attribute of the configuration item (CI) in the ServiceNow CMDB, and closes the ticket.

---

## 📂 Project Structure

```
track-d/
├── .env.example              # Template for credentials
├── .gitignore                # Git ignore rules
├── README.md                 # This guide
└── scripts/
    ├── requirements.txt      # Python dependencies
    └── resize_runner.py      # Main python resizing orchestrator script
```

---

## 🛠️ Step-by-Step Setup

### Step 1: Prepare ServiceNow Credentials
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your ServiceNow Personal Developer Instance (PDI) details:
   - `SNOW_INSTANCE`: your developer instance prefix (e.g. `dev12345`).
   - `SNOW_USER`: your admin user (typically `admin`).
   - `SNOW_PASSWORD`: your instance password.

### Step 2: Install Python Dependencies
Install the required libraries in your local machine:
```bash
pip install -r scripts/requirements.txt
```

### Step 3: Raise a Resize Change Request in ServiceNow
1. Open your ServiceNow PDI in the browser.
2. Go to **Change** -> **Create New** (or search `change_request.list` -> click **New**).
3. Select **Normal** or **Standard** change.
4. Set the following fields:
   - **Short Description**: `Resize VM`
   - **Description**: Add the target VM name and target size (SKU) in this format:
     ```text
     Target VM Name: vm-patch-test
     Target VM Size: Standard_B2s
     ```
     *(Note: Allowed target sizes are Standard_B1s and Standard_B2s for cost safety).*
   - **State**: Set the state to **Assess**, **Scheduled**, or **Implement**. (If selecting **Assess**, fill in the **Assignment group** as `Service Desk` or similar before saving).
5. Save/Submit the Change Request.

---

## 🚀 Running the Automation

To run the resizing orchestrator locally:
```bash
python scripts/resize_runner.py
```

### What happens behind the scenes:
1. **Polls ServiceNow**: The script queries the Table API for any active Change Request in state **New**, **Assess**, **Scheduled**, or **Implement** with the short description `"Resize VM"`.
2. **Extracts Details**: It parses the VM Name and Target Size from the description field.
3. **Safety Check**: It validates that the Target Size is within the allowed values (`Standard_B1s`, `Standard_B2s`) to prevent billing surprises.
4. **Idempotency Check**: It queries the VM's current size via Azure CLI (`az vm show`). If the VM is already at the target size, it skips the execution (no-op), logs it, and closes the ticket successfully.
5. **Execution**: If a resize is needed, it deallocates the VM, resizes it, and starts it up again.
6. **Verification**: It queries Azure to verify that the VM size change actually took effect.
7. **Updates CMDB CI**: It patches the corresponding VM instance CI record in the CMDB (`cmdb_ci_vm_instance`) with the new size.
8. **Closes ServiceNow Ticket**: Writes the execution logs to the Change Request's **Work notes** and sets the ticket state to **Closed** (`state=3`) with a close code of `successful`.
