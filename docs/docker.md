# Docker Node Support

## Overview

Provided below is some information for helping setup and use Docker
nodes within a CORE scenario.

## Installation

### Debian Systems

```shell
sudo apt install docker.io
```

### RHEL Systems

## Configuration

Custom configuration required to avoid iptable rules being added and removing
the need for the default docker network, since core will be orchestrating
connections between nodes.

Place the file below in **/etc/docker/daemon.json**

```json
{
  "bridge": "none",
  "iptables": false
}
```

## Group Setup

To use Docker nodes within the python GUI, you will need to make sure the
user running the GUI is a member of the docker group.

```shell
# add group if does not exist
sudo groupadd docker

# add user to group
sudo usermod -aG docker $USER

# to get this change to take effect, log out and back in or run the following
newgrp docker
```

## Image Requirements

CORE configures Docker node interfaces and stock default routes from the host
network namespace, so compose-backed application images do not need `ip`,
`ping`, or `ethtool` for CORE to attach them to a scenario. CORE also avoids
installing packages into compose-backed application containers, since those
images are often purpose-built and may have pinned, archived, or intentionally
limited package repositories.

Non-compose Docker nodes can attempt to install basic networking tools such as
`ip`, `ping`, and `ethtool` when a container starts, using common package
managers such as `apt-get`, `apk`, or `yum`. For repeatable scenarios, or when
you want those tools available inside the container terminal, build them into
the image instead.

Example Dockerfile:

```
FROM ubuntu:latest
RUN apt-get update
RUN apt-get install -y iproute2 iputils-ping ethtool
```

Build image:

```shell
sudo docker build -t <name> .
```

## Tools and Versions Tested With

* Docker version 18.09.5, build e8ff056
* nsenter from util-linux 2.31.1
