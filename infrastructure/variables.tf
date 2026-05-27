#################################################
# Cluster Creation Parameters
#################################################
variable "cluster_template" {
  description = "Template for Kubernetes cluster"
  type        = string
  default     = "kubernetes-v1.34.6-melbourne-qh2-uom-v1"
}

variable "cluster_node_count" {
  description = "Total nodes to add to cluster"
  type        = number
  default     = 3
}

variable "cluster_master_count" {
  description = "Total master nodes to add to cluster"
  type        = number
  default     = 1
}

variable "cluster_master_flavor" {
  description = "Flavor to use for master node instance"
  type        = string
  default     = "uom.mse.2c9g"
}

variable "cluster_node_flavor" {
  description = "Flavor to use for worker nodes"
  type        = string
  default     = "uom.mse.2c9g"
}

variable "cluster_name" {
  description = "Name of the cluster"
  default     = "comp90024"
  type        = string
}

variable "kubernetes_storage_reclaim_policy" {
  description = "Reclaim policy for the Storage class used with Cinder"
  default     = "Retain"
  type        = string
}

variable "kubernetes_storage_availability" {
  description = "Availability zone for the storage class to use with Cinder"
  default     = "melbourne-qh2-uom"
  type        = string
}

variable "kubernetes_storage_name" {
  description = "Name of the performance storage class to use with Cinder"
  default     = "perfretain"
  type        = string
}

#################################################
# ElasticSearch
#################################################
variable "elastic_chart_version" {
  type        = string
  default     = "v3.2.0"
  description = "Version of the elasticsearch operator chart to install"
}

variable "elastic_namespace" {
  type        = string
  description = "Namespace for elasticsearch resources"
  default     = "elastic"
}

variable "elastic_operator_name" {
  default     = "elastic-operator"
  description = "Name for Elastic operator chart"
  type        = string
}


#################################################
# Fission
#################################################
variable "fission_version" {
  description = "Version of Fission to install"
  default     = "1.22.0"
  type        = string
}

variable "fission_namespace" {
  description = "Namespace in which to deploy Fission"
  default     = "fission"
  type        = string
}

variable "fission_name" {
  description = "Name for the Fission Helm release"
  default     = "fission"
  type        = string
}

#################################################
# Valkey and Keda parameters for Event-Driven
# orchestration.
#################################################
variable "valkey_chart_version" {
  description = "Version of the Valkey chart to use"
  type        = string
  default     = "0.9.4"
}

variable "valkey_namespace" {
  description = "Namespace in which to deploy Valkey"
  type        = string
  default     = "valkey"
}

variable "valkey_create_namespace" {
  type        = bool
  default     = true
  description = "Whether to create the valkey namespace"
}

variable "keda_namespace" {
  default     = "keda"
  type        = string
  description = "Namespace for the Keda chart deployment"
}

variable "keda_create_namespace" {
  type        = bool
  default     = true
  description = "Whether to create the Keda namespace on the cluster"
}

variable "keda_version" {
  type        = string
  description = "Version of the Keda chart to install"
  default     = "2.9.4"
}