#
# SPDX-License-Identifier: Apache-2.0
#
import logging

from api.lib.agent.network_base import NetworkBase
from api.common.enums import FabricNodeType, FabricImages
from api.utils.port_picker import find_available_ports, set_ports_mapping

LOG = logging.getLogger(__name__)

class FabricNetwork(NetworkBase):
    def __init__(self, *args, **kwargs):
        super(FabricNetwork, self).__init__(*args, **kwargs)

        self._version = kwargs.get("version")
        self._type = kwargs.get("node_type")
        self._agent_id = kwargs.get("agent_id")
        self._node_id = kwargs.get("node_id")
        self._deploy_name = "%s" % kwargs.get("node_name")
        self._service_name = "%s" % kwargs.get("node_name")
        # self._ingress_name = "ingress-%s" % str(self._node_id)
        self._container_image = ""
        self._container_environments = None
        self._container_command = None
        self._container_command_args = None
        self._initial_containers = None
        self._container_volume_mounts = None
        self._containers = None
        self._initial_containers = None
        self._volumes = None

        if self._type == FabricNodeType.Ca.name.lower():
            self._container_ports = [7054]
            self._service_ports = [{"port": 7054, "name": "server"}]
            self._image_name = "%s:%s" % (FabricImages.Ca.value, self._version)
            self._pod_name = "ca-server"
            self._init_ca_deployment()
        elif self._type == FabricNodeType.Peer.name.lower():
            self._container_ports = [7051, 7052]
            self._service_ports = [{"port": 7051, "name": "server"}, {"port": 7052, "name": "grpc"}]
            self._image_name = "%s:%s" % (FabricImages.Peer.value, self._version)
            self._pod_name = "peer"
            self._init_peer_deployment()
        else:
            self._container_ports = []
            self._service_ports = []
            self._image_name = ""
            self._pod_name = ""

    def _init_ca_deployment(self):
        self._container_environments = [
            {
                "name": "FABRIC_CA_HOME",
                "value": "/etc/hyperledger/fabric-ca-server",
            },
            {
                "name": "FABRIC_CA_SERVER_HOME",
                "value": "/etc/hyperledger/fabric-ca-server/crypto",
            },
            {"name": "FABRIC_CA_SERVER_TLS_ENABLED", "value": "true"},
            {
                "name": "FABRIC_CA_SERVER_CSR_HOSTS",
                "value": "0.0.0.0",
            },
        ]
        self._container_command = ["fabric-ca-server"]
        self._container_command_args = ["start", "-b", "admin:adminpw", "-d"]

    def _init_peer_deployment(self):
        pass

    def _generate_deployment(self):
        deployment = {"name": self._deploy_name, "labels":  {"app": self._node_id}}
        if self._volumes is not None:
            deployment.update({"volumes": self._volumes})
        if self._initial_containers is not None:
            deployment.update({"initial_containers": self._initial_containers})
        container_dict = {
            "image": self._image_name,
            "name": self._pod_name,
            "ports": self._container_ports,
        }
        if self._container_environments is not None:
            container_dict.update(
                {"environments": self._container_environments}
            )
        if self._container_volume_mounts is not None:
            container_dict.update(
                {"volume_mounts": self._container_volume_mounts}
            )
        if self._container_command is not None:
            container_dict.update({"command": self._container_command})
        if self._container_command_args is not None:
            container_dict.update(
                {"command_args": self._container_command_args}
            )
        containers = [container_dict]
        deployment.update({"containers": containers})
        
        return  deployment

    # def _generate_deployment(self):
    #     containers = []
    #     name = "deploy-%s" % str(self._node_id)
    #     if self._type == FabricNodeType.Ca.name.lower():
    #         image = "%s:%s" % (CA_IMAGE_NAME, self._version)
    #         environments = [
    #             {
    #                 "name": "FABRIC_CA_HOME",
    #                 "value": "/etc/hyperledger/fabric-ca-server",
    #             },
    #             {
    #                 "name": "FABRIC_CA_SERVER_HOME",
    #                 "value": "/etc/hyperledger/fabric-ca-server/crypto",
    #             },
    #             {"name": "FABRIC_CA_SERVER_TLS_ENABLED", "value": "true"},
    #             {
    #                 "name": "FABRIC_CA_SERVER_CSR_HOSTS",
    #                 "value": ",".join(CA_HOSTS),
    #             },
    #         ]
    #         ports = [7054]
    #         command = ["fabric-ca-server"]
    #         command_args = ["start", "-b", "admin:adminpw", "-d"]
    #         containers.append(
    #             {
    #                 "image": image,
    #                 "environments": environments,
    #                 "name": "ca-server",
    #                 "ports": ports,
    #                 "command": command,
    #                 "command_args": command_args,
    #             }
    #         )
    #     elif self._type == FabricNodeType.Peer.name.lower():
    #         image = "%s:%s" % (PEER_IMAGE_NAME, self._version)

    #         ports = [7051, 7052]
    #         pass
    #     else
    #         pass
    #     return {"containers": containers, "name": name}

    def _generate_service(self):
        return {
            "name": self._service_name,
            "ports": self._service_ports,
            "selector": {"app":  self._node_id},
            "service_type": "NodePort",
        }

    # def _generate_ingress(self):
    #     name = str(self._node_id)
    #     service_name = "service-%s" % name
    #     ingress_name = "ingress-%s" % name
    #     ingress_paths = []
    #     annotations = {"nginx.ingress.kubernetes.io/ssl-redirect": "false"}
    #     if self._type == FabricNodeType.Ca.name.lower():
    #         ingress_paths = [{"port": 7054, "path": "/%s" % name}]

    #     return {
    #         "name": ingress_name,
    #         "service_name": service_name,
    #         "ingress_paths": ingress_paths,
    #         "annotations": annotations,
    #     }

    def generate_config(self, *args, **kwargs):
        config = {
            "deployment": self._generate_deployment(),
            "service": self._generate_service(),
            # "ingress": self._generate_ingress(),
        }

        return config
