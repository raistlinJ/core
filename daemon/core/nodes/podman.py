import json
import logging
import os
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

from mako.template import Template

from core.emulator.distributed import DistributedServer
from core.errors import CoreCommandError, CoreError
from core.executables import BASH
from core.nodes.base import CoreNode, CoreNodeOptions

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.emulator.session import Session

PODMAN: str = "podman"
PODMAN_COMPOSE: str = "podman-compose"


@dataclass
class PodmanOptions(CoreNodeOptions):
    image: str = "ubuntu"
    """image used when creating container"""
    binds: list[tuple[str, str]] = field(default_factory=list)
    """bind mount source and destinations to setup within container"""
    volumes: list[tuple[str, str, bool, bool]] = field(default_factory=list)
    """
    volume mount source, destination, unique, delete to setup within container

    unique is True for node unique volume naming
    delete is True for deleting volume mount during shutdown
    """
    compose: str = None
    """
    Path to a compose file, if one should be used for this node.
    """
    compose_name: str = None
    """
    Service name to start, within the provided compose file.
    """
    image_compatibility: bool = False
    docker_command: str = "tail -f /dev/null"
    run_image_default: bool = False


@dataclass
class VolumeMount:
    src: str
    """volume mount name"""
    dst: str
    """volume mount destination directory"""
    unique: bool = True
    """True to create a node unique prefixed name for this volume"""
    delete: bool = True
    """True to delete the volume during shutdown"""
    path: str = None
    """path to the volume on the host"""


class PodmanNode(CoreNode):
    """
    Provides logic for creating a Podman based node.
    """

    def __init__(
        self,
        session: "Session",
        _id: int = None,
        name: str = None,
        server: DistributedServer = None,
        options: PodmanOptions = None,
    ) -> None:
        """
        Create a PodmanNode instance.

        :param session: core session instance
        :param _id: node id
        :param name: node name
        :param server: remote server node
            will run on, default is None for localhost
        :param options: options for creating node
        """
        options = options or PodmanOptions()
        super().__init__(session, _id, name, server, options)
        self.image: str = options.image
        self.compose: str | None = options.compose
        self.compose_name: str | None = options.compose_name
        self.image_compatibility: bool = options.image_compatibility
        self.docker_command: str = options.docker_command
        self.run_image_default: bool = options.run_image_default
        self.binds: list[tuple[str, str]] = options.binds
        self.runtime_container: str = self.name
        self.volumes: dict[str, VolumeMount] = {}
        for src, dst, unique, delete in options.volumes:
            src_name = self._unique_name(src) if unique else src
            self.volumes[src] = VolumeMount(src_name, dst, unique, delete)

    @classmethod
    def create_options(cls) -> PodmanOptions:
        """
        Return default creation options, which can be used during node creation.

        :return: podman options
        """
        return PodmanOptions()

    def create_cmd(self, args: str, shell: bool = False) -> str:
        """
        Create command used to run commands within the context of a node.

        :param args: command arguments
        :param shell: True to run shell like, False otherwise
        :return: node command
        """
        if shell:
            args = f"{BASH} -c {shlex.quote(args)}"
        return f"{PODMAN} exec {self.runtime_container} {args}"

    def _resolve_runtime_container(self) -> str:
        """
        Resolve actual runtime container object for compose services.

        :return: container id/name to use for inspect/exec
        :raises CoreError: when compose service has no running container
        """
        if not self.compose:
            return self.name
        container = self.host_cmd(
            f"{PODMAN_COMPOSE} ps -q {self.compose_name}", cwd=self.directory
        ).strip()
        if not container:
            raise CoreError(
                f"compose service has no running container: {self.compose_name}"
            )
        return container

    def create_net_cmd(self, args: str, shell: bool = False) -> str:
        """
        Create command used to run network commands within the context of a node.

        :param args: command arguments
        :param shell: True to run shell like, False otherwise
        :return: node command
        """
        if shell:
            args = f"{BASH} -c {shlex.quote(args)}"
        return f"nsenter -t {self.pid} -n -- {args}"

    def _unique_name(self, name: str) -> str:
        """
        Creates a session/node unique prefixed name for the provided input.

        :param name: name to make unique
        :return: unique session/node prefixed name
        """
        return f"{self.session.id}.{self.id}.{name}"

    def alive(self) -> bool:
        """
        Check if the node is alive.

        :return: True if node is alive, False otherwise
        """
        try:
            running = self.host_cmd(
                f"{PODMAN} inspect -f '{{{{.State.Running}}}}' {self.runtime_container}"
            )
            return json.loads(running)
        except CoreCommandError:
            return False

    def startup(self) -> None:
        """
        Create a podman container instance for the specified image.

        :return: nothing
        """
        with self.lock:
            if self.up:
                raise CoreError(f"starting node({self.name}) that is already up")
            # create node directory
            self.makenodedir()
            hostname = self.name.replace("_", "-")
            startup_command = (self.docker_command or "").strip()
            if self.compose:
                if not self.compose_name:
                    raise CoreError(
                        "a compose name is required when using a compose file"
                    )
                compose_path = os.path.expandvars(self.compose)
                data = self.host_cmd(f"cat {compose_path}")
                template = Template(data)
                rendered = template.render_unicode(
                    node=self,
                    hostname=hostname,
                    podman=PODMAN,
                    podman_compose=PODMAN_COMPOSE
                )
                rendered = rendered.replace('"', r'\"')
                rendered = "\\n".join(rendered.splitlines())
                compose_path = self.directory / "podman-compose.yml"
                self.host_cmd(f'printf "{rendered}" >> {compose_path}', shell=True)
                self.host_cmd(
                    f"{PODMAN_COMPOSE} up -d {self.compose_name}", cwd=self.directory
                )
                self.runtime_container = self._resolve_runtime_container()
            else:
                # setup commands for creating bind/volume mounts
                binds = ""
                for src, dst in self.binds:
                    binds += f"--mount type=bind,source={src},target={dst} "
                volumes = ""
                for volume in self.volumes.values():
                    volumes += (
                        f"--mount type=volume,"
                        f"source={volume.src},target={volume.dst} "
                    )
                # Always start with keepalive; run startup/default commands post-boot.
                cmd = "tail -f /dev/null"
                if self.run_image_default:
                    logger.info(
                        "node(%s) run_image_default enabled, will exec image default after boot",
                        self.name,
                    )
                elif startup_command:
                    logger.info(
                        "node(%s) will exec startup command after boot: %s",
                        self.name,
                        startup_command,
                    )
                # Clean up stale container names from interrupted runs.
                self.host_cmd(
                    f"{PODMAN} rm -f {self.name} >/dev/null 2>&1 || true",
                    shell=True,
                )
                run_cmd = (
                    f"{PODMAN} run -td --init --net=none --hostname {hostname} "
                    f"--name {self.name} --sysctl net.ipv6.conf.all.disable_ipv6=0 "
                    f"{binds} {volumes} "
                    f"--privileged {self.image} {cmd}"
                )
                self.host_cmd(run_cmd)
                running = self.host_cmd(
                    f"{PODMAN} inspect -f '{{{{.State.Running}}}}' {self.name}"
                ).strip().lower()
                if running != "true":
                    logger.warning(
                        "node(%s) container exited immediately; recreating with keepalive",
                        self.name,
                    )
                    self.host_cmd(f"{PODMAN} rm -f {self.name}")
                    keepalive_cmd = (
                        f"{PODMAN} run -td --init --net=none --hostname {hostname} "
                        f"--name {self.name} --sysctl net.ipv6.conf.all.disable_ipv6=0 "
                        f"{binds} {volumes} "
                        f"--privileged {self.image} tail -f /dev/null"
                    )
                    self.host_cmd(keepalive_cmd)
                # setup symlinks for bind and volume mounts within
                for src, dst in self.binds:
                    link_path = self.host_path(Path(dst), True)
                    self.host_cmd(f"ln -s {src} {link_path}")
                for volume in self.volumes.values():
                    volume.path = self.host_cmd(
                        f"{PODMAN} volume inspect -f '{{{{.Mountpoint}}}}' {volume.src}"
                    )
                    link_path = self.host_path(Path(volume.dst), True)
                    self.host_cmd(f"ln -s {volume.path} {link_path}")
                self.runtime_container = self.name
            self.pid = int(
                self.host_cmd(
                    f"{PODMAN} inspect -f '{{{{.State.Pid}}}}' {self.runtime_container}"
                ).strip()
            )
            logger.debug("node(%s) pid: %s", self.name, self.pid)
            self.up = True
            if self.image_compatibility:
                self.check_image_compatibility()
            if self.run_image_default:
                self.run_default_command()
            elif startup_command and not self.compose:
                self.run_startup_command(startup_command)

    def run_startup_command(self, command: str) -> None:
        """
        Run configured startup command string within the running container.
        """
        try:
            wrapped = shlex.quote(f"{command} > /tmp/core-startup.log 2>&1")
            self.host_cmd(f"{PODMAN} exec -d {self.runtime_container} sh -c {wrapped}")
            logger.info(
                "node(%s) startup command launched (see /tmp/core-startup.log)",
                self.name,
            )
        except Exception as e:
            logger.error("node(%s) failed startup command launch: %s", self.name, e)

    def run_default_command(self) -> None:
        """
        Inspects the image and runs its default ENTRYPOINT/CMD.
        """
        logger.info("node(%s) attempting to run image default command", self.name)
        try:
            image = self.image
            if not image:
                # for compose, try to find image from running container
                image = self.host_cmd(
                    f"{PODMAN} inspect -f '{{{{.Config.Image}}}}' {self.runtime_container}"
                ).strip()
                logger.info("node(%s) discovered image: %s", self.name, image)

            if not image:
                logger.warning("node(%s) could not determine image for default command", self.name)
                return

            # get image config
            data = self.host_cmd(f"{PODMAN} inspect -f '{{{{json .Config}}}}' {image}")
            config = json.loads(data)
            entrypoint = config.get("Entrypoint") or []
            cmd = config.get("Cmd") or []

            # handle case where entrypoint/cmd might be None or not list
            if not isinstance(entrypoint, list):
                entrypoint = [entrypoint] if entrypoint else []
            if not isinstance(cmd, list):
                cmd = [cmd] if cmd else []

            full_cmd = entrypoint + cmd
            if full_cmd:
                cmd_str = " ".join(shlex.quote(x) for x in full_cmd)
                logger.info("node(%s) running default command: %s", self.name, cmd_str)
                # run in background using a shell to ensure environment is set
                # and redirect output to a log file for debugging
                time.sleep(0.5)
                # we use wait=False because we don't want to block session startup
                try:
                    self.cmd(f"{cmd_str} > /tmp/core-startup.log 2>&1", wait=False, shell=True)
                    logger.info("node(%s) default command launched (see /tmp/core-startup.log)", self.name)
                except Exception as e:
                    logger.error("node(%s) failed to launch default command: %s", self.name, e)
            else:
                logger.warning("node(%s) image %s has no default ENTRYPOINT or CMD", self.name, image)
        except Exception as e:
            logger.error("node(%s) failed to run default command: %s", self.name, e)

    def check_image_compatibility(self) -> None:
        """
        Checks for required packages and attempts to install them if missing.
        """
        required_tools = ["bash", "ip"]
        missing_tools = []
        for tool in required_tools:
            try:
                self.cmd(f"which {tool}")
            except CoreCommandError:
                missing_tools.append(tool)

        if not missing_tools:
            return

        logger.info("node(%s) missing tools: %s", self.name, missing_tools)
        # try to install missing tools using common package managers
        # 1. apt-get (Debian/Ubuntu)
        # 2. apk (Alpine)
        # 3. yum (CentOS/Fedora)
        install_cmds = [
            ("apt-get update && apt-get install -y", ["bash", "iproute2"]),
            ("apk add", ["bash", "iproute2"]),
            ("yum install -y", ["bash", "iproute"]),
        ]

        for pkg_manager, packages in install_cmds:
            try:
                self.cmd(f"which {pkg_manager.split()[0]}")
                # check which of the missing tools map to these packages
                to_install = []
                if "bash" in missing_tools:
                    to_install.append(packages[0])
                if "ip" in missing_tools:
                    to_install.append(packages[1])

                if to_install:
                    logger.info("node(%s) attempting to install %s using %s", self.name, to_install, pkg_manager)
                    self.cmd(f"{pkg_manager} {' '.join(to_install)}")
                    return # success
            except CoreCommandError:
                continue

    def shutdown(self) -> None:
        """
        Shutdown logic.

        :return: nothing
        """
        # nothing to do if node is not up
        if not self.up:
            return
        with self.lock:
            self.ifaces.clear()
            if self.compose:
                self.host_cmd(f"{PODMAN_COMPOSE} down -t 0", cwd=self.directory)
            else:
                self.host_cmd(f"{PODMAN} rm -f {self.name}")
                for volume in self.volumes.values():
                    if volume.delete:
                        self.host_cmd(f"{PODMAN} volume rm {volume.src}")
            self.up = False

    def termcmdstring(self, sh: str = "/bin/sh") -> str:
        """
        Create a terminal command string.

        :param sh: shell to execute command in
        :return: str
        """
        terminal = f"{PODMAN} exec -it {self.name} {sh}"
        if self.server is None:
            return terminal
        else:
            return f"ssh -X -f {self.server.host} xterm -e {terminal}"

    def create_dir(self, dir_path: Path) -> None:
        """
        Create a private directory.

        :param dir_path: path to create
        :return: nothing
        """
        logger.debug("creating node dir: %s", dir_path)
        self.cmd(f"mkdir -p {dir_path}")

    def mount(self, src_path: str, target_path: str) -> None:
        """
        Create and mount a directory.

        :param src_path: source directory to mount
        :param target_path: target directory to create
        :return: nothing
        :raises CoreCommandError: when a non-zero exit status occurs
        """
        logger.debug("mounting source(%s) target(%s)", src_path, target_path)
        raise Exception("not supported")

    def create_file(self, file_path: Path, contents: str, mode: int = 0o644) -> None:
        """
        Create a node file with a given mode.

        :param file_path: name of file to create
        :param contents: contents of file
        :param mode: mode for file
        :return: nothing
        """
        logger.debug("node(%s) create file(%s) mode(%o)", self.name, file_path, mode)
        temp = NamedTemporaryFile(delete=False)
        temp.write(contents.encode())
        temp.close()
        temp_path = Path(temp.name)
        directory = file_path.parent
        if str(directory) != ".":
            self.cmd(f"mkdir -m {0o755:o} -p {directory}")
        if self.server is not None:
            self.server.remote_put(temp_path, temp_path)
        self.host_cmd(f"{PODMAN} cp {temp_path} {self.name}:{file_path}")
        self.cmd(f"chmod {mode:o} {file_path}")
        if self.server is not None:
            self.host_cmd(f"rm -f {temp_path}")
        temp_path.unlink()

    def copy_file(self, src_path: Path, dst_path: Path, mode: int = None) -> None:
        """
        Copy a file to a node, following symlinks and preserving metadata.
        Change file mode if specified.

        :param dst_path: file name to copy file to
        :param src_path: file to copy
        :param mode: mode to copy to
        :return: nothing
        """
        logger.info(
            "node file copy file(%s) source(%s) mode(%o)", dst_path, src_path, mode or 0
        )
        self.cmd(f"mkdir -p {dst_path.parent}")
        if self.server:
            temp = NamedTemporaryFile(delete=False)
            temp_path = Path(temp.name)
            src_path = temp_path
            self.server.remote_put(src_path, temp_path)
        self.host_cmd(f"{PODMAN} cp {src_path} {self.name}:{dst_path}")
        if mode is not None:
            self.cmd(f"chmod {mode:o} {dst_path}")
