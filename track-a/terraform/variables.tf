variable "vm_name" {
  description = "VM name"
  type        = string
}

variable "vm_size" {
  description = "Azure VM size"
  type        = string
  default     = "Standard_B2s"

  validation {
    condition     = contains(["Standard_B1s", "Standard_B2s", "Standard_B1ms", "Standard_B2ms", "Standard_D2as_v4", "Standard_D2s_v3"], var.vm_size)
    error_message = "Allows standard VM sizes for training."
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
  description = "SSH public key"
  type        = string
}

variable "create_public_ip" {
  description = "Set true to attach a public IP"
  type        = bool
  default     = false
}

variable "allowed_ssh_source" {
  description = "CIDR/IP allowed to SSH"
  type        = string
  default     = "*"
}
