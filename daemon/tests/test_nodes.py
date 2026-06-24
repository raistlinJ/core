from unittest import mock
from pathlib import Path

import pytest

from core.emulator.data import InterfaceData
from core.emulator.session import Session
from core.errors import CoreError
from core.nodes.base import CoreNode
from core.nodes.docker import DockerNode, DockerOptions
from core.nodes.network import HubNode, SwitchNode, WlanNode
from core.nodes.podman import PodmanNode, PodmanOptions

MODELS = ["router", "host", "PC", "mdr"]
NET_TYPES = [SwitchNode, HubNode, WlanNode]


class TestNodes:
    @pytest.mark.parametrize("model", MODELS)
    def test_node_add(self, session: Session, model: str):
        # given
        options = CoreNode.create_options()
        options.model = model

        # when
        node = session.add_node(CoreNode, options=options)

        # then
        assert node
        assert node.alive()
        assert node.up

    def test_node_set_pos(self, session: Session):
        # given
        node = session.add_node(CoreNode)
        x, y = 100.0, 50.0

        # when
        session.set_node_pos(node, x, y)

        # then
        assert node.position.x == x
        assert node.position.y == y

    def test_node_set_geo(self, session: Session):
        # given
        node = session.add_node(CoreNode)
        lon, lat, alt = 0.0, 0.0, 0.0

        # when
        session.set_node_geo(node, lon, lat, alt)

        # then
        assert node.position.lon == lon
        assert node.position.lat == lat
        assert node.position.alt == alt

    def test_node_delete(self, session: Session):
        # given
        node = session.add_node(CoreNode)

        # when
        session.delete_node(node.id)

        # then
        with pytest.raises(CoreError):
            session.get_node(node.id, CoreNode)

    def test_node_add_iface(self, session: Session):
        # given
        node = session.add_node(CoreNode)

        # when
        iface = node.create_iface()

        # then
        assert iface.id in node.ifaces

    def test_node_get_iface(self, session: Session):
        # given
        node = session.add_node(CoreNode)
        iface = node.create_iface()
        assert iface.id in node.ifaces

        # when
        iface2 = node.get_iface(iface.id)

        # then
        assert iface == iface2

    def test_node_delete_iface(self, session: Session):
        # given
        node = session.add_node(CoreNode)
        iface = node.create_iface()
        assert iface.id in node.ifaces

        # when
        node.delete_iface(iface.id)

        # then
        assert iface.id not in node.ifaces

    @pytest.mark.parametrize(
        "mac,expected",
        [
            ("AA-AA-AA-FF-FF-FF", "aa:aa:aa:ff:ff:ff"),
            ("00:00:00:FF:FF:FF", "00:00:00:ff:ff:ff"),
        ],
    )
    def test_node_set_mac(self, session: Session, mac: str, expected: str):
        # given
        node = session.add_node(CoreNode)
        iface_data = InterfaceData()
        iface = node.create_iface(iface_data)

        # when
        iface.set_mac(mac)

        # then
        assert str(iface.mac) == expected

    @pytest.mark.parametrize(
        "mac", ["AAA:AA:AA:FF:FF:FF", "AA:AA:AA:FF:FF", "AA/AA/AA/FF/FF/FF"]
    )
    def test_node_set_mac_exception(self, session: Session, mac: str):
        # given
        node = session.add_node(CoreNode)
        iface_data = InterfaceData()
        iface = node.create_iface(iface_data)

        # when
        with pytest.raises(CoreError):
            iface.set_mac(mac)

    @pytest.mark.parametrize(
        "ip,expected,is_ip6",
        [
            ("127", "127.0.0.0/32", False),
            ("10.0.0.1/24", "10.0.0.1/24", False),
            ("2001::", "2001::/128", True),
            ("2001::/64", "2001::/64", True),
        ],
    )
    def test_node_add_ip(self, session: Session, ip: str, expected: str, is_ip6: bool):
        # given
        node = session.add_node(CoreNode)
        iface_data = InterfaceData()
        iface = node.create_iface(iface_data)

        # when
        iface.add_ip(ip)

        # then
        if is_ip6:
            assert str(iface.get_ip6()) == expected
        else:
            assert str(iface.get_ip4()) == expected

    def test_node_add_ip_exception(self, session):
        # given
        node = session.add_node(CoreNode)
        iface_data = InterfaceData()
        iface = node.create_iface(iface_data)
        ip = "256.168.0.1/24"

        # when
        with pytest.raises(CoreError):
            iface.add_ip(ip)

    @pytest.mark.parametrize("net_type", NET_TYPES)
    def test_net(self, session, net_type):
        # given

        # when
        node = session.add_node(net_type)

        # then
        assert node
        assert node.up

    def test_ptp(self, session):
        # given

        # when
        ptp = session.create_ptp()

        # then
        assert ptp
        assert ptp.up

    def test_control_net(self, session):
        # given

        # when
        control_net = session.create_control_net(0, "172.168.0.0/24", None, None)

        # then
        assert control_net
        assert control_net.up

    def test_control_net_error(self, session):
        # given
        ip_prefix = "172.168.0.0/24"
        session.create_control_net(0, ip_prefix, None, None)

        # when
        with pytest.raises(CoreError):
            session.create_control_net(0, ip_prefix, None, None)

    def test_container_options_defaults(self):
        # given
        docker_options = DockerOptions()
        podman_options = PodmanOptions()

        # then
        assert not docker_options.image_compatibility
        assert not podman_options.image_compatibility
        assert docker_options.model == "PC"
        assert podman_options.model == "PC"
        assert docker_options.services == ["DefaultRoute"]
        assert podman_options.services == ["DefaultRoute"]

    def test_docker_image_compatibility_builds_derived_image(self):
        # given
        node = DockerNode.__new__(DockerNode)
        node.name = "n1"
        node.id = 1
        node.image = "ubuntu:latest"
        node.directory = Path("/tmp/n1.conf")
        node.session = mock.MagicMock(id=1000)
        node._write_host_file = mock.MagicMock()
        node._compatibility_dockerfile = mock.MagicMock(return_value="FROM ubuntu\n")
        node.host_cmd = mock.MagicMock()

        # when
        node.setup_image_compatibility()

        # then
        assert node.image == "core-compat-1000-1-n1:latest"
        node._write_host_file.assert_called_once_with(
            Path("/tmp/n1.conf/Dockerfile.corecompat"), "FROM ubuntu\n"
        )
        node.host_cmd.assert_called_once_with(
            "docker build --network host -t core-compat-1000-1-n1:latest "
            "-f Dockerfile.corecompat .",
            cwd=Path("/tmp/n1.conf"),
        )

    def test_docker_image_compatibility_uses_exec_form_run(self):
        # given
        node = DockerNode.__new__(DockerNode)
        node.name = "n1"
        node._image_user = mock.MagicMock(return_value=None)

        # when
        dockerfile = node._compatibility_dockerfile("example:latest")

        # then
        assert 'RUN ["/bin/sh", "-euxc", "' in dockerfile
        assert "SHELL [\"/bin/sh\", \"-c\"]" not in dockerfile

    @pytest.mark.parametrize("node_type", [DockerNode, PodmanNode])
    def test_image_compatibility_repairs_archived_apt_sources(self, node_type):
        # given
        node = node_type.__new__(node_type)
        node.name = "n1"
        node._image_user = mock.MagicMock(return_value=None)

        # when
        dockerfile = node._compatibility_dockerfile("example:latest")

        # then
        assert "Acquire::Check-Valid-Until=false" in dockerfile
        assert "if ! apt_update; then apt_fix_sources; apt_update; fi" in dockerfile
        assert "archive.debian.org/debian" in dockerfile
        assert "old-releases.ubuntu.com/ubuntu" in dockerfile
        assert "done; };" in dockerfile

    def test_docker_prepare_compose_project_local(self):
        # given
        node = DockerNode.__new__(DockerNode)
        node.directory = Path("/tmp/n1.conf")
        node.server = None
        node._write_host_file = mock.MagicMock()

        with mock.patch("core.nodes.docker.shutil.copytree") as copytree:
            # when
            compose_path = node._prepare_compose_project(
                "/tmp/project/docker-compose.yml", "services:\n"
            )

        # then
        assert compose_path == Path("/tmp/n1.conf/docker-compose.yml")
        copytree.assert_called_once_with(
            Path("/tmp/project"),
            Path("/tmp/n1.conf"),
            dirs_exist_ok=True,
            symlinks=True,
        )
        node._write_host_file.assert_called_once_with(
            Path("/tmp/n1.conf/docker-compose.yml"), "services:\n"
        )

    def test_docker_prepare_compose_project_remote(self):
        # given
        node = DockerNode.__new__(DockerNode)
        node.directory = Path("/tmp/n1.conf")
        node.server = mock.MagicMock()
        node.host_cmd = mock.MagicMock()
        node._write_host_file = mock.MagicMock()

        # when
        compose_path = node._prepare_compose_project(
            "/tmp/project/docker-compose.yml", "services:\n"
        )

        # then
        assert compose_path == Path("/tmp/n1.conf/docker-compose.yml")
        node.host_cmd.assert_called_once_with(
            'src_dir=$(cd /tmp/project && pwd -P) && dst_dir=$(cd /tmp/n1.conf && pwd -P) && if [ "$src_dir" != "$dst_dir" ]; then cp -a "$src_dir"/. "$dst_dir"/; fi',
            shell=True,
        )
        node._write_host_file.assert_called_once_with(
            Path("/tmp/n1.conf/docker-compose.yml"), "services:\n"
        )

    def test_docker_compose_image_compatibility_override(self):
        # given
        node = DockerNode.__new__(DockerNode)
        node.name = "n1"
        node.id = 1
        node.compose_name = "web"
        node.directory = Path("/tmp/n1.conf")
        node.session = mock.MagicMock(id=1000)
        node._write_host_file = mock.MagicMock()
        node._compatibility_dockerfile = mock.MagicMock(return_value="FROM app\n")
        rendered = "services:\n  web:\n    image: vulhub/spring-boot-jetty:3.2.4\n"

        # when
        override_path = node._compose_image_compatibility_override(rendered)

        # then
        assert override_path == Path("/tmp/n1.conf/docker-compose.corecompat.yml")
        assert node._write_host_file.call_count == 2
        _, override = node._write_host_file.call_args_list[1].args
        assert "core-compat-1000-1-n1:latest" in override
        assert "Dockerfile.corecompat" in override
        assert "network: host" in override

    def test_docker_compose_checks_image_compatibility(self):
        # given
        node = DockerNode.__new__(DockerNode)
        node.image_compatibility = True
        node.compose = "/tmp/docker-compose.yml"

        # when
        result = node.should_check_image_compatibility()

        # then
        assert result
