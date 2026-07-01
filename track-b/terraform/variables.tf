# variables.tf — inputs the pipeline passes in (sourced from the ServiceNow request)

variable "vm_name" {
  description = "VM name; derive it from the Change Request for idempotency"
  type        = string
}

variable "vm_size" {
  description = "Azure VM size. Keep it small/cheap."
  type        = string
  default     = "Standard_B1s"

  validation {
    condition     = contains(["Standard_B1s", "Standard_B2s"], var.vm_size)
    error_message = "For cost safety this training only allows Standard_B1s or Standard_B2s."
  }
}

variable "region" {
  description = "Azure region"
  type        = string
  default     = "centralus"
}

variable "admin_username" {
  description = "Admin user for the VM"
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key" {
  description = "SSH public key for VM access. Loaded dynamically in terraform.tfvars."
  type        = string
}

variable "create_public_ip" {
  description = "Set true to attach a public IP + NSG (needed for Track B Ansible-over-SSH). Keep true for Track B."
  type        = bool
  default     = true
}

variable "allowed_ssh_source" {
  description = "CIDR/IP allowed to SSH when create_public_ip=true. '*' = anywhere (only ok for a short-lived training VM you tear down fast)."
  type        = string
  default     = "*"
}
