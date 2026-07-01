# VM Provisioning Automation

This repository automates the provisioning of a Linux Virtual Machine in Azure triggered by a ServiceNow Requested Item (RITM).

## Requirements

- Python 3.x
- Terraform
- requests
- python-dotenv

Install python dependencies:
```bash
pip install -r scripts/requirements.txt
```

## Solution Files

- `scripts/fetch_request.py`: Polls or receives the ServiceNow RITM payload, extracts the configuration variables (VM name, size, location), and generates `terraform.tfvars.json`.
- `scripts/update_servicenow.py`: Creates a Virtual Machine Instance Configuration Item (CI) in the ServiceNow CMDB and updates the RITM state to Closed Complete.
- `terraform/main.tf`: Defines the Azure provider, resource group, virtual network, subnets, and the Linux Virtual Machine resources.
- `terraform/variables.tf`: Defines variables for the deployment including naming, sizing, region, and SSH public keys.
- `terraform/outputs.tf`: Defines outputs captured by the pipeline including private IP and naming values.

## How to Run

1. Configure your environment credentials in a `.env` file:
   ```ini
   SNOW_INSTANCE=your_instance_prefix
   SNOW_USER=your_username
   SNOW_PASSWORD=your_password
   RITM_NUMBER=RITMXXXXXX
   ```
2. Run the request extraction script:
   ```bash
   python scripts/fetch_request.py
   ```
3. Initialize and apply the Terraform configuration:
   ```bash
   cd terraform
   terraform init
   terraform apply -auto-approve
   ```
4. Run the ServiceNow update script:
   ```bash
   cd ..
   python scripts/update_servicenow.py
   ```

## Design Choices

- **Decoupled Workflow**: ServiceNow ticket handling and infrastructure orchestration are kept separate. The python scripts act as the integration glue, which allows changing the infrastructure engine or the ticket manager independently.
- **Dynamic Configuration**: Variables are passed from ServiceNow straight to Terraform variables via JSON, avoiding hardcoded values.
- **CMDB Lifecycle**: The pipeline ensures the CMDB is populated before closing the ticket to maintain audit trace integrity.

## Limitations

- **State Management**: Uses local state by default. For team settings, a remote backend configuration is required.
