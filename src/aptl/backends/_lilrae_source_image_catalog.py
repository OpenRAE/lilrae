"""Reviewed source bindings added for the released Linux infrastructure kits.

Tags in provenance record the lookup used on 2026-10-15. Runtime selection
uses only the immutable references below and never contacts a registry.
"""

from aptl.backends._raes_backend_implementation_types import (
    BackendImplementationProfile,
    SemanticRuntimeSelector,
)

_RUNTIME_SELECTORS = {
    "postgresql": SemanticRuntimeSelector(
        "database_services", "engine", "postgresql", "17"
    ),
    "cassandra": SemanticRuntimeSelector(
        "datastore_services", "engine", "cassandra", "5"
    ),
    "python": SemanticRuntimeSelector(
        "software_components", "component_id", "python", "3.12"
    ),
}

_SOURCE_ORIGINS = {
    "application-service": "https://github.com/mendhak/docker-http-https-echo",
    "linux": "https://github.com/panubo/docker-sshd",
    "nftables": "https://github.com/nicolaka/netshoot",
    "devpi": (
        "https://github.com/JonasAlfredsson/docker-devpi/blob/"
        "730fa5a3b655d9645b4421bd9c943cf8c5f35090/server/requirements.txt"
    ),
    "openldap": "https://github.com/vegardit/docker-openldap",
    "samba": "https://github.com/instantlinux/docker-tools/tree/main/images/samba-dc",
    "minio": (
        "https://github.com/pgsty/silo/tree/d88f46ccee345a9c2fabe2d221d9a9e56bc11aec"
    ),
    "kea": "https://kb.isc.org/docs/isc-kea-packages",
}


def _source(
    name: str, version: str, repository: str, tag: str, digest: str
) -> BackendImplementationProfile:
    origin = _SOURCE_ORIGINS.get(name)
    return BackendImplementationProfile(
        profile_id=f"{name}-{version}",
        selector=None,
        source_name=name,
        source_version=version,
        image_ref=f"{repository}@sha256:{digest}",
        provenance_refs=(
            f"docker://{repository}:{tag}",
            "resolved:2026-10-15",
            *((origin,) if origin else ()),
        ),
        source_runtime_selector=_RUNTIME_SELECTORS.get(name),
    )


SOURCE_IMAGE_PROFILES = (
    _source(
        "application-service",
        "stable",
        "mendhak/http-https-echo",
        "42",
        "a265f55c86cb3baead76fdf379dc8e9e6440ed121874e101e60b833e05bce8d4",
    ),
    _source(
        "linux",
        "stable",
        "quay.io/panubo/sshd",
        "1.9.0",
        "3b6bea884a5449232c0db49ffd765c73f839a0ae1f158caac1e67d37e2ddcb3e",
    ),
    _source(
        "nftables",
        "stable",
        "nicolaka/netshoot",
        "latest",
        "b09d9b21381f47a79b3cbcb30da25266dc17186ea00ae65e99fdc51396f48e70",
    ),
    _source(
        "devpi",
        "6",
        "jonasal/devpi-server",
        "latest",
        "6cd77af3926735dd88c63e9dfb780b8ff2040de23d148c6d26f64dc4ac7a0105",
    ),
    _source(
        "openldap",
        "stable",
        "vegardit/openldap",
        "latest",
        "82b394eb7457dba68f8a387045f8a8bb7f17220912250ff093fe90b434a046cc",
    ),
    _source(
        "samba",
        "4",
        "instantlinux/samba-dc",
        "latest",
        "7b569a7f21f86d9f6570de561dd07cb7e3d85ab57da7866b7006a9a932a8feb6",
    ),
    _source(
        "kea",
        "stable",
        "docker.cloudsmith.io/isc/docker/kea-dhcp4",
        "3.0.2",
        "384c936f23d064556d3a92e34d550a2e9b5cd3cf6e2e492a52b93ccb212d6508",
    ),
    _source(
        "minio",
        "stable",
        "pgsty/minio",
        "RELEASE.2026-08-04T00-00-00Z",
        "b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372",
    ),
    _source(
        "chromium",
        "stable",
        "lscr.io/linuxserver/chromium",
        "latest",
        "9761e4dce2375165ab85566d5a58920525d49c49469ed7a08a6d874dcdb1cedc",
    ),
    _source(
        "keycloak",
        "26",
        "quay.io/keycloak/keycloak",
        "26.8.1",
        "79c623a22abacf3fe6c00a5fb30f5b7843d717b234033b80995891c06116d244",
    ),
    _source(
        "jupyterlab",
        "4",
        "quay.io/jupyter/base-notebook",
        "lab-4.6.4",
        "3fc2b8023bb7e3f11a09bd77aa07575c1ece16a0b9b64556757e34c52f667a1a",
    ),
    _source(
        "triton-inference-server",
        "stable",
        "nvcr.io/nvidia/tritonserver",
        "26.09-py3",
        "350820308a0e62efbb22f9d4e5b29c970b7c7a54f7b275674e457e5fd8bab1a5",
    ),
    _source(
        "shuffle",
        "2",
        "ghcr.io/shuffle/shuffle-backend",
        "2.3.0",
        "b50f8bf9e1a1bd0966ffa5b4bee8620bfe8c7ad87d18abe4fb085b56b41982f4",
    ),
    _source(
        "open-policy-agent",
        "1",
        "openpolicyagent/opa",
        "1.21.2",
        "7459fa69661242c8983d6e4116779550cbb17608f1110ddcd4e9e24da4dcb0e5",
    ),
    _source(
        "airflow",
        "3",
        "apache/airflow",
        "3.1.0",
        "e81cb98fe4e5f60fadde8cc6a1c926a363720339062cd53db04b6442950ab9ee",
    ),
    _source(
        "bind9",
        "9",
        "internetsystemsconsortium/bind9",
        "9.20",
        "071465f88068854d0ceadd9b985fb1acae4071e80754e545cd811fde57541ad0",
    ),
    _source(
        "cassandra",
        "5",
        "cassandra",
        "5",
        "618a493bcf1f817ea2f07288a46fa76fb2d9c4dfd5a04c28227336405782889c",
    ),
    _source(
        "gitea",
        "1",
        "gitea/gitea",
        "1",
        "87a67ee09d3ae0d1df5fda5dcda3e2a1f9236a45b0a59025d6e00e46adc43bef",
    ),
    _source(
        "grafana",
        "stable",
        "grafana/grafana",
        "latest",
        "dbbc38ea21103cefb50396340cd88afec779c7e070b0a7bf5a75b4ce46651d3f",
    ),
    _source(
        "homepage",
        "stable",
        "ghcr.io/gethomepage/homepage",
        "latest",
        "57c4a0531937889c0b968b120fe9c2560bbe036b5c9e18c49a9e2479de9975d1",
    ),
    _source(
        "k3s",
        "stable",
        "rancher/k3s",
        "latest",
        "5e0707cfd1239b358ef73f3254bc3eadc027dd30cd5ec6ca41e29e47652a1b8c",
    ),
    _source(
        "k6",
        "stable",
        "grafana/k6",
        "latest",
        "e66db15b860113878fa74670e31f5e274830b7b6e42c8bff28b2f2d86a257603",
    ),
    _source(
        "litellm",
        "stable",
        "ghcr.io/berriai/litellm",
        "main-stable",
        "b7b9e2c306343721802253d0dd9436b9634a2eb4e14da7c7cf06c5c7b7530802",
    ),
    _source(
        "mail-server",
        "stable",
        "ghcr.io/docker-mailserver/docker-mailserver",
        "15",
        "af51b15dd3fc72153c0e90eb7692bb5e3a463212d87959a80fa7aa89b617d44a",
    ),
    _source(
        "mlflow",
        "3",
        "ghcr.io/mlflow/mlflow",
        "v3.4.0",
        "9c9e24a3fc24a0e9dcc5ba1daa9ebfc59e01b0a23b6eb89a4fdf25b84ad5347c",
    ),
    _source(
        "nginx",
        "stable",
        "nginx",
        "stable",
        "908cb0471582493fcf76dcc97e8e52cf9a43a72bcfcb4fe06e6390fb89a19577",
    ),
    _source(
        "openbao",
        "stable",
        "openbao/openbao",
        "latest",
        "6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf",
    ),
    _source(
        "openproject",
        "stable",
        "openproject/openproject",
        "16",
        "eb08fa636184f737af2cd31b2ef1706cb9b35bf7bc2cfe2c4e065e1dd461a74e",
    ),
    _source(
        "opentelemetry-collector",
        "stable",
        "otel/opentelemetry-collector-contrib",
        "latest",
        "39923a8e431bd1f57be82411999d389fcfe40857492e4365456d97a4c1f74be6",
    ),
    _source(
        "postgresql",
        "17",
        "postgres",
        "17",
        "2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3",
    ),
    _source(
        "python",
        "3.12",
        "python",
        "3.12",
        "42dc0ee40d7707e2f2ee506a1cbe52e09ab11c207c5b429342638f83177601fe",
    ),
    _source(
        "rabbitmq",
        "stable",
        "rabbitmq",
        "4",
        "28973fc043b661c4b366236b70a0ec5a0959f1d85bdeb7bfdd1817e208520e57",
    ),
    _source(
        "roundcube",
        "1",
        "roundcube/roundcubemail",
        "1.6.11-apache",
        "7191357d2ee2b50e4068571f683a85fec86f5b2f27b764e5850c5799f0ad89df",
    ),
    _source(
        "step-ca",
        "stable",
        "smallstep/step-ca",
        "latest",
        "a2b17872915c193259b75a5474c398326f41bd199f0842093e52cf4182bc8270",
    ),
    _source(
        "suricata",
        "8",
        "jasonish/suricata",
        "8.0",
        "bf4bea5b45d9c10265a3ee6628e2ec8930b9d1fb7caf9d1afb63af413b9cbb26",
    ),
    _source(
        "tempo",
        "stable",
        "grafana/tempo",
        "latest",
        "1ce31d6d7ffab62189685e8c47881d4a561c5d38bd0dbd66e40ca83cef07923d",
    ),
    _source(
        "traefik",
        "3",
        "traefik",
        "3",
        "575fa15b135078fe5e50aa847987d96dbddd7b093c172429618404df73f3fa7c",
    ),
    _source(
        "valkey",
        "stable",
        "valkey/valkey",
        "8",
        "640c5e62cea04b6d6f2084232651d0cc70362d31f4f805e7be94dbed6855e8f2",
    ),
    _source(
        "vllm",
        "stable",
        "vllm/vllm-openai",
        "latest",
        "c1c9f6fd5c109ba7f0546a59f5b2f15fb87f64c77782e90a27b648b42a8e67c3",
    ),
)
