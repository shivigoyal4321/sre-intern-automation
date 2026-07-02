# VM Decommission Automation

This script automates the decommissioning of an Azure VM when a corresponding ServiceNow Change Request is approved. It deletes the Azure Resource Group (which deletes the VM and all associated disks, network interfaces, and public IPs), updates the configuration item (CI) status in the CMDB to **Retired**, and closes the ticket in ServiceNow.

---

## 📂 Project Structure

```
track-c/
├── .env.example              # Template for credentials
├── .gitignore                # Git ignore rules
├── README.md                 # This guide
└── scripts/
    ├── requirements.txt      # Python dependencies
    └── decom_runner.py       # Main python decommissioning script
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

### Step 3: Raise a Decommission Change Request in ServiceNow
1. Open your ServiceNow PDI in the browser.
2. Go to **Change** -> **Create New** (or search `change_request.list` -> click **New**).
3. Select **Normal** or **Standard** change.
4. Set the following fields:
   - **Short Description**: `Decommission VM`
   - **Description**: Add the following line containing your target VM's name:
     ```text
     Target VM Name: vm-patch-test
     ```
   - **State**: Set the state to **Assess**, **Scheduled**, or **Implement**. (If selecting **Assess**, fill in the **Assignment Group** as `Service Desk` or similar before saving).
5. Save/Submit the Change Request.

---

## 🚀 Running the Automation

To run the decommissioning orchestrator locally:
```bash
python scripts/decom_runner.py
```

### What happens behind the scenes:
1. **Polls ServiceNow**: The script queries the Table API for any active Change Request in state **New**, **Assess**, **Scheduled**, or **Implement** with the short description `"Decommission VM"`.
2. **Extracts VM Name**: It parses the target VM name from the description field.
3. **Verifies Resource Group**: It runs `az group exists` using Azure CLI to verify the resource group `rg-<vm_name>` exists in Azure.
4. **Destroys Azure Resources**: 
   - First, it looks for local Terraform configuration in `../terraform/` (or relative path) and attempts `terraform destroy -auto-approve`.
   - If that is missing or fails, it falls back to deleting the entire resource group directly using Azure CLI: `az group delete --name rg-<vm_name> --yes`.
5. **Verifies Cleanup**: It checks `az resource list` to ensure all VM resources have been destroyed.
6. **Retires the CMDB record**: It searches the CMDB `cmdb_ci_vm_instance` table for a record matching the VM Name and updates its operational status and install status to **Retired** (`operational_status=6`, `install_status=7`).
7. **Closes ServiceNow Ticket**: Writes the deletion verification logs to the Change Request's **Work notes** and sets the ticket state to **Closed** (`state=3`) with a close code of `successful`.
