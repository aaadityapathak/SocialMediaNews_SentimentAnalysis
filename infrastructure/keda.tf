resource "helm_release" "keda" {
  name             = "keda"
  namespace        = var.keda_namespace
  create_namespace = var.keda_create_namespace
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  version          = var.keda_version
  atomic           = true

  depends_on = [openstack_containerinfra_cluster_v1.main]
}
