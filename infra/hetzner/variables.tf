variable "server_name" {
  description = "Hetzner Cloud server name."
  type        = string
  default     = "veridra-prod-01"
}

variable "server_type" {
  description = "Hetzner Cloud server type; verify availability/price before apply."
  type        = string
  default     = "cx33"
}

variable "location" {
  description = "Hetzner Cloud EU location."
  type        = string
  default     = "nbg1"
}

variable "ssh_public_key" {
  description = "Operator SSH public key. Never provide a private key."
  type        = string
  sensitive   = true
}

variable "ssh_source_cidrs" {
  description = "CIDRs allowed to reach TCP/22. Deliberately has no open-to-world default."
  type        = list(string)

  validation {
    condition     = length(var.ssh_source_cidrs) > 0
    error_message = "Provide at least one trusted SSH source CIDR."
  }
}
