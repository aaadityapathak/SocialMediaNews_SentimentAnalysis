data "openstack_containerinfra_clustertemplate_v1" "cluster" {
  name = var.cluster_template
}

resource "openstack_containerinfra_cluster_v1" "main" {
  name                = var.cluster_name
  cluster_template_id = data.openstack_containerinfra_clustertemplate_v1.cluster.id
  node_count          = var.cluster_node_count
  flavor              = var.cluster_node_flavor
  master_count        = var.cluster_master_count
  master_flavor       = var.cluster_master_flavor
}
