
resource "null_resource" "fission_crds" {
  provisioner "local-exec" {
    command = "kubectl create -k 'github.com/fission/fission/crds/v1?ref=v${var.fission_version}'"
  }
  depends_on = [openstack_containerinfra_cluster_v1.main]
}


resource "helm_release" "fission" {
  chart            = "fission-all"
  repository       = "https://fission.github.io/fission-charts/"
  version          = "v${var.fission_version}"
  namespace        = var.fission_namespace
  name             = var.fission_name
  create_namespace = true
  atomic           = true

  set = [
    {
      name  = "routerServiceType"
      value = "ClusterIP"
    },
    {
      name  = "persistence.storageClass"
      value = var.kubernetes_storage_name
    }
  ]

  depends_on = [null_resource.fission_crds]
}
