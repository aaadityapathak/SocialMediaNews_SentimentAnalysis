
# Valkey (Redis-equivalent) deployment for event based architecture
resource "helm_release" "valkey" {
  chart            = "valkey"
  name             = "valkey"
  repository       = "https://valkey.io/valkey-helm/"
  version          = var.valkey_chart_version
  atomic           = true
  namespace        = var.valkey_namespace
  create_namespace = var.valkey_create_namespace

  set = [
    # Single instance. No need for more
    {
      name  = "replica.enabled"
      value = false
    }
  ]

  depends_on = [openstack_containerinfra_cluster_v1.main]
}
