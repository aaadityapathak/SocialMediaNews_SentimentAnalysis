
resource "kubernetes_storage_class_v1" "perfretain" {
  metadata {
    name = var.kubernetes_storage_name
    annotations = {
      "storageclass.kubernetes.io/is-default-class" : false
    }
  }
  parameters = {
    type         = "performance"
    availability = var.kubernetes_storage_availability
  }
  storage_provisioner = "cinder.csi.openstack.org"
  reclaim_policy      = var.kubernetes_storage_reclaim_policy
  depends_on          = [openstack_containerinfra_cluster_v1.main]
}
