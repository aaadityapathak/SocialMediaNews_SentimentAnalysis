
resource "helm_release" "elastic_operator" {
  name             = var.elastic_operator_name
  repository       = "https://helm.elastic.co"
  chart            = "eck-operator"
  version          = var.elastic_chart_version
  namespace        = var.elastic_namespace
  create_namespace = true
  atomic           = true
  depends_on       = [kubernetes_storage_class_v1.perfretain]
}

resource "kubernetes_manifest" "elasticsearch" {
  manifest   = yamldecode(file("${path.module}/elasticsearch.yaml"))
  depends_on = [helm_release.elastic_operator]
}

resource "kubernetes_manifest" "kibana" {
  manifest   = yamldecode(file("${path.module}/kibana.yaml"))
  depends_on = [kubernetes_manifest.elasticsearch]
}
