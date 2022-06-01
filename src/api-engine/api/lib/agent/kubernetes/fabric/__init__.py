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

        self._name = kwargs.get("name")
        self._version = kwargs.get("version")
        self._type = kwargs.get("node_type")
        self._agent_id = kwargs.get("agent_id")
        self._node_name = kwargs.get("node_name")
        self._node_id = kwargs.get("node_id")
        self._org_name = kwargs.get("org_name")
        self._network_name = kwargs.get("network_name")
        self._domain = self._org_name.split(".",1)[1] if self._org_name is not None else ""
        self._deploy_name = "%s" % self._node_name
        self._service_name = "%s" % self._node_name
        # self._ingress_name = "ingress-%s" % str(self._node_id)
        self._container_image = ""
        self._container_environments = None
        self._container_command = None
        self._container_command_args = None
        self._initial_containers = None
        self._container_volume_mounts = None
        self._containers = None
        self._initial_containers = None
        # self._volumes = None
        self._volumes = [
            {
                "name": "data",
                "persistentVolumeClaim": {"claimName": "pvc-data"},
            }
        ]
        if self._type == FabricNodeType.Ca.name.lower():
            self._container_ports = [7054]
            self._service_ports = [{"port": 7054, "name": "server"}]
            self._image_name = "%s:%s" % (FabricImages.Ca.value, "1.4")
            self._pod_name = "ca-server"
            self._init_ca_deployment()
        elif self._type == FabricNodeType.Orderer.name.lower():
            self._container_ports = [7050]
            self._service_ports = [{"port": 7050, "name": "server"}]
            self._image_name = "%s:%s" % (FabricImages.Orderer.value, self._version)
            self._pod_name = "orderer"
            self._init_orderer_deployment()
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
            self._container_volume_mounts = None
            self._volumes = None

    def _init_ca_deployment(self):
        self._container_environments = [
            {
                "name": "FABRIC_CA_HOME",
                "value": "/etc/hyperledger/fabric-ca-server",
            },
            {
                "name": "FABRIC_CA_SERVER_CA_NAME",
                "value": self._name,
            },
            {
                "name": "FABRIC_CA_SERVER_TLS_ENABLED",
                "value": "true",
            }
        ]
        self._container_volume_mounts = [
            {
                "mountPath": "/etc/hyperledger/fabric-ca-server-config",
                "name": "data",
                "subPath": "./{org}/crypto-config/peerOrganizations/{org}/ca/".format(org=self._org_name)
            },
        ]
        self._container_command = ["fabric-ca-server"]
        self._container_command_args = [
            "start", 
            "--ca.certfile", 
            "/etc/hyperledger/fabric-ca-server-config/ca.{}-cert.pem".format(self._org_name),
            "--ca.keyfile",
            "/etc/hyperledger/fabric-ca-server-config/priv_sk",
            "-b", 
            "admin:adminpw", 
            "-d"
        ]

    def _init_orderer_deployment(self):
        self._container_environments = [
            {
                "name": "ORDERER_GENERAL_LOGLEVEL",
                "value": "debug",
            },
            {
                "name": "ORDERER_GENERAL_LISTENADDRESS",
                "value": "0.0.0.0",
            },
            {
                "name": "ORDERER_GENERAL_BOOTSTRAPMETHOD", 
                "value": "file"
            },
            {
                "name": "ORDERER_GENERAL_BOOTSTRAPFILE", 
                "value": "/etc/hyperledger/configtx/genesis.block"
            },
            {
                "name": "ORDERER_GENERAL_LOCALMSPID", 
                "value": "{}MSP".format(self._node_name.capitalize())
            },
            {
                "name": "ORDERER_GENERAL_LOCALMSPDIR", 
                "value": "/etc/hyperledger/fabric/msp"
            },
            {
                "name": "ORDERER_GENERAL_TLS_ENABLED", 
                "value": "true"
            },
            {
                "name": "ORDERER_GENERAL_TLS_PRIVATEKEY", 
                "value": "/etc/hyperledger/fabric/tls/server.key"
            },
            {
                "name": "ORDERER_GENERAL_TLS_CERTIFICATE", 
                "value": "/etc/hyperledger/fabric/tls/server.crt"
            },
            {
                "name": "ORDERER_GENERAL_TLS_ROOTCAS", 
                "value": "[/etc/hyperledger/fabric/tls/ca.crt]"
            }
        ]
        self._container_volume_mounts = [
            {
                "mountPath": "/etc/hyperledger/configtx",
                "name": "data",
                "subPath": "./{}/".format(self._network_name)
            },
            {
                "mountPath": "/etc/hyperledger/fabric/msp",
                "name": "data",
                "subPath": "./{}/crypto-config/ordererOrganizations/{}/orderers/{}/msp".format(self._org_name, self._domain, self._name)
            },
            {
                "mountPath": "/etc/hyperledger/fabric/tls",
                "name": "data",
                "subPath": "./{}/crypto-config/ordererOrganizations/{}/orderers/{}/tls".format(self._org_name, self._domain, self._name)
            },
        ]
        self._container_command = ["orderer"]

    def _init_peer_deployment(self):
        self._container_environments = [
            {
                "name": "FABRIC_LOGGING_SPEC",
                "value": "debug",
            },
            {
                "name": "CORE_PEER_ID",
                "value": self._name,
            },
            {
                "name": "CORE_PEER_ADDRESS", 
                "value": "0.0.0.0:7051"
            },
            {
                "name": "CORE_PEER_LOCALMSPID", 
                "value": "{}MSP".format(self._node_name.capitalize())
            },
            {
                "name": "CORE_PEER_MSPCONFIGPATH", 
                "value": "/etc/hyperledger/peer/msp"
            },
            {
                "name": "CORE_LEDGER_STATE_STATEDATABASE", 
                "value": "LevelDB"
            },
            {
                "name": "CORE_LEDGER_STATE_COUCHDBCONFIG_COUCHDBADDRESS", 
                "value": "couchdb:5984"
            },
            {
                "name": "CORE_LEDGER_STATE_COUCHDBCONFIG_USERNAME", 
                "value": ""
            },
            {
                "name": "CORE_LEDGER_STATE_COUCHDBCONFIG_PASSWORD", 
                "value": ""
            }
        ]
        self._container_volume_mounts = [
            {
                "mountPath": "/var/hyperledger/configtx",
                "name": "data",
                "subPath": "./{}/".format(self._network_name)
            },
            {
                "mountPath": "/etc/hyperledger/peer/msp",
                "name": "data",
                "subPath": "./{org}/crypto-config/peerOrganizations/{org}/peers/{name}/msp".format(org=self._org_name, name=self._name)
            },
            {
                "mountPath": "/etc/hyperledger/msp/users",
                "name": "data",
                "subPath": "./{org}/crypto-config/peerOrganizations/{org}/users".format(org=self._org_name)
            },
        ]
        self._container_command = ["peer", "node", "start"]

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
