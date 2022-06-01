import logging
import os

from django.conf import settings
from kubernetes import client, config
from kubernetes.client.rest import ApiException

LOG = logging.getLogger(__name__)

K8S_NAMESPACE = getattr(settings, "K8S_NAMESPACE", "cello")
GLUSTER_HOSTS = os.getenv("GLUSTER_HOSTS")
GLUSTER_VOL_NAME = os.getenv("GLUSTER_VOL_NAME")
GLUSTER_STORAGE_SIZE =  os.getenv("GLUSTER_STORAGE_SIZE", "100Gi")

class KubernetesClient(object):
    def __init__(self, config_file=None):
        super(KubernetesClient, self).__init__()
        self._config_file = config_file
        config.load_kube_config(config_file)

    def list_pods(self):
        v1 = client.CoreV1Api()
        print("Listing pods with their IPs:")
        ret = v1.list_pod_for_all_namespaces(watch=False)
        for i in ret.items:
            print(
                "%s\t%s\t%s"
                % (i.status.pod_ip, i.metadata.namespace, i.metadata.name)
            )

    def get_or_create_namespace(self, name=None):
        if name:
            v1 = client.CoreV1Api()
            try:
                v1.read_namespace(name=name)
            except ApiException:
                body = client.V1Namespace(
                    kind="Namespace",
                    api_version="v1",
                    metadata=client.V1ObjectMeta(name=name),
                )
                try:
                    v1.create_namespace(body=body)
                except ApiException as e:
                    LOG.error(
                        "Exception when calling CoreV1Api->read_namespace: %s",
                        e,
                    )
                
                if (GLUSTER_HOSTS is not None) and (GLUSTER_VOL_NAME is not None):
                    self.get_or_create_persistentvolumeclaim(namespace=name)
    
    def get_or_create_persistentvolumeclaim(self, namespace=K8S_NAMESPACE):
        pv_name = "pv-{}".format(namespace)
        endpoint_name = "glusterfs"
        labels = {"storage.k8s.io/name": "glusterfs", "storage.k8s.io/part-of":"kubernetes-complete-reference"}
        v1 = client.CoreV1Api()
        # create persistentVolume(static)
        try:
            v1.read_persistent_volume(name=pv_name)
        except ApiException as e:
            metadata = client.V1ObjectMeta(name=pv_name, labels=labels)
            body = client.V1PersistentVolume(
                metadata=metadata, kind="PersistentVolume", api_version="v1", spec=client.V1PersistentVolumeSpec(
                    access_modes=["ReadWriteMany"],
                    capacity={"storage": GLUSTER_STORAGE_SIZE},
                    glusterfs={"endpoints": endpoint_name, "path":  GLUSTER_VOL_NAME},
                    persistent_volume_reclaim_policy="Retain",
                    volume_mode="Filesystem"
                )
            )
            try:
                v1.create_persistent_volume(body)
            except ApiException as e:
                LOG.error("Exception when call CoreV1Api: %s", e)
                raise e
        
        # create glusterfs service
        try:
            v1.read_namespaced_service(endpoint_name, namespace)
        except ApiException as e:
            metadata.name = endpoint_name
            body = client.V1Service(
                metadata=metadata, kind="Service", api_version="v1", spec=client.V1ServiceSpec(
                    ports=[{"protocol": "TCP", "port": 1, "targetPort": 1}],
                    type="ClusterIP",
                )
            )
            try:
                v1.create_namespaced_service(namespace, body)
            except ApiException as e:
                LOG.error("Exception when call CoreV1Api: %s", e)
                raise e
            
        # create glusterfs endpoint
        try:
            v1.read_namespaced_endpoints(endpoint_name, namespace)
        except ApiException as e:
            body = client.V1Endpoints(
                metadata=metadata, kind="Endpoints", api_version="v1", subsets=[
                    {
                        "addresses": [{"ip": ip} for ip in GLUSTER_HOSTS.split(",")],
                        "ports": [{"protocol": "TCP", "port": 1}],
                    }
                ]
            )
            try:
                v1.create_namespaced_endpoints(namespace, body)
            except ApiException as e:
                LOG.error("Exception when call CoreV1Api: %s", e)
                raise e
        
        # create  persistentvolumeclaim
        try:
            v1.read_namespaced_persistent_volume_claim("pvc-data", namespace)
        except ApiException as e:
            metadata.name = "pvc-data"
            body = client.V1PersistentVolumeClaim(
                metadata=metadata, kind="PersistentVolumeClaim", api_version="v1", spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteMany"],
                    resources={"requests": {"storage": GLUSTER_STORAGE_SIZE}},
                    volume_name=pv_name,
                    volume_mode="Filesystem"
                )
            )
            try:
                v1.create_namespaced_persistent_volume_claim(namespace, body)
            except ApiException as e:
                LOG.error("Exception when call CoreV1Api: %s", e)
                raise e

    def create_deployment(self, namespace=K8S_NAMESPACE, *args, **kwargs):
        containers = kwargs.get("containers", [])
        deploy_name = kwargs.get("name")
        labels = kwargs.get("labels", {})
        volumes = kwargs.get("volumes", [])
        # labels.update({"app": deploy_name})
        container_pods = []
        for container in containers:
            name = container.get("name")
            image = container.get("image")
            ports = container.get("ports", [])
            environments = container.get("environments", [])
            command = container.get("command", [])
            command_args = container.get("command_args", [])
            volume_mounts = container.get("volume_mounts",[])
            environments = [
                client.V1EnvVar(name=env.get("name"), value=env.get("value"))
                for env in environments
            ]
            ports = [
                client.V1ContainerPort(container_port=port) for port in ports
            ]
            container_pods.append(
                client.V1Container(
                    name=name,
                    image=image,
                    env=environments,
                    command=command,
                    args=command_args,
                    ports=ports,
                    image_pull_policy="IfNotPresent",
                    volume_mounts=volume_mounts,
                )
            )
        deployment_metadata = client.V1ObjectMeta(name=deploy_name)
        pod_spec = client.V1PodSpec(containers=container_pods, volumes=volumes)
        spec_metadata = client.V1ObjectMeta(labels=labels)
        template_spec = client.V1PodTemplateSpec(
            metadata=spec_metadata, spec=pod_spec
        )
        spec= client.V1DeploymentSpec(
            selector=client.V1LabelSelector(match_labels=labels),
            template=template_spec
        )

        body = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=deployment_metadata,
            spec=spec,
        )

        api_instance = client.AppsV1Api()

        try:
            response = api_instance.create_namespaced_deployment(
                namespace=namespace, body=body, pretty="true"
            )
        except ApiException as e:
            LOG.error("Exception when call AppsV1Api: %s", e)
            raise e

        return True, response

    def create_service(
        self,
        namespace=K8S_NAMESPACE,
        name=None,
        selector=None,
        ports=None,
        service_type="ClusterIP",
    ):
        if selector is None:
            selector = {}
        if ports is None:
            ports = []

        metadata = client.V1ObjectMeta(name=name, labels=selector)
        spec = client.V1ServiceSpec(
            ports=ports, selector=selector, type=service_type
        )
        body = client.V1Service(
            metadata=metadata, spec=spec, kind="Service", api_version="v1"
        )

        api_instance = client.CoreV1Api()
        try:
            response = api_instance.create_namespaced_service(namespace, body)
        except ApiException as e:
            LOG.error("Exception when call CoreV1Api: %s", e)
            raise e

        return True, response

    def create_ingress(
        self,
        namespace=K8S_NAMESPACE,
        name=None,
        service_name=None,
        ingress_paths=None,
        annotations=None,
    ):
        if ingress_paths is None:
            ingress_paths = []
        if annotations is None:
            annotations = {}

        api_instance = client.ExtensionsV1beta1Api()
        metadata = client.V1ObjectMeta(name=name, annotations=annotations)
        path_list = []
        for ing_path in ingress_paths:
            ing_backend = client.V1beta1IngressBackend(
                service_name=service_name, service_port=ing_path.get("port", 0)
            )
            path_list.append(
                client.V1beta1HTTPIngressPath(
                    path=ing_path.get("path", ""), backend=ing_backend
                )
            )
        http_dict = client.V1beta1HTTPIngressRuleValue(paths=path_list)
        rule_list = [client.V1beta1IngressRule(http=http_dict, host="")]
        ingress_spec = client.V1beta1IngressSpec(rules=rule_list)
        body = client.V1beta1Ingress(
            api_version="extensions/v1beta1",
            metadata=metadata,
            spec=ingress_spec,
            kind="Ingress",
        )

        try:
            api_instance.create_namespaced_ingress(
                namespace=namespace, body=body, pretty="true"
            )
        except ApiException as e:
            LOG.error("Create ingress failed %s", e)
            raise e

        return True

    def delete_deployment(self, namespace=K8S_NAMESPACE, name=None):
        api_instance = client.AppsV1Api()
        delete_options = client.V1DeleteOptions(
            propagation_policy="Foreground"
        )
        grace_period_seconds = 10

        try:
            api_instance.delete_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=delete_options,
                grace_period_seconds=grace_period_seconds,
                pretty="true",
            )
        except ApiException as e:
            LOG.error("Exception when call AppsV1beta1Api: %s", e)

    def delete_service(self, namespace=K8S_NAMESPACE, name=None):
        api_instance = client.CoreV1Api()

        try:
            api_instance.delete_namespaced_service(
                name=name, namespace=namespace
            )
        except ApiException as e:
            LOG.error("Exception when call CoreV1Api: %s", e)

    def delete_ingress(self, namespace=K8S_NAMESPACE, name=None):
        api_instance = client.ExtensionsV1beta1Api()
        delete_options = client.V1DeleteOptions()

        try:
            api_instance.delete_namespaced_ingress(
                name=name,
                namespace=namespace,
                body=delete_options,
                pretty="true",
            )
        except ApiException as e:
            LOG.error("Exception when call AppsV1beta1Api: %s\n" % e)
