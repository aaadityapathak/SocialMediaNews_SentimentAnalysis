output "cluster_id" {
  value       = openstack_containerinfra_cluster_v1.main.id
  description = "ID of the Magnum Kubernetes cluster"
}

output "cluster_name" {
  value       = openstack_containerinfra_cluster_v1.main.name
  description = "Name of the Magnum Kubernetes cluster"
}
