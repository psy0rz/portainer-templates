"""Finding the docker volumes that belong to a compose stack."""

import json

from remote_host import quote

ZFS_DRIVER_NAMES = ("zfs", "zfs-volume-plugin", "zfs:latest")


class DockerVolume:
    def __init__(self, name, driver, mountpoint, labels):
        self.name = name
        self.driver = driver
        self.mountpoint = mountpoint
        self.labels = labels or {}
        self.source_dataset = None
        self.dest_dataset = None
        self.used_bytes = None

    @property
    def is_zfs(self):
        return self.driver in ZFS_DRIVER_NAMES or self.driver.startswith("zfs")

    def __repr__(self):
        return "DockerVolume(%s, driver=%s, dataset=%s)" % (
            self.name,
            self.driver,
            self.source_dataset,
        )


COMPOSE_PROJECT_LABEL = "com.docker.compose.project"


def stack_volumes(host, stack_name):
    """All volumes of a compose project, by label and by the project_ name prefix.

    A volume that carries the label of *another* compose project is never returned,
    even when its name starts with this stack's name (stack "shop" must not claim
    the volume "shop_extra_data" of a stack called "shop_extra").
    """
    labelled = host.run(
        "docker volume ls --quiet --filter label=%s=%s"
        % (COMPOSE_PROJECT_LABEL, quote(stack_name))
    ).split()
    all_names = host.run("docker volume ls --quiet").split()
    prefixed = [name for name in all_names if name.startswith(stack_name + "_")]

    candidate_names = sorted(set(labelled) | set(prefixed))
    if not candidate_names:
        return []

    volumes = []
    for volume in inspect_volumes(host, candidate_names):
        owning_project = volume.labels.get(COMPOSE_PROJECT_LABEL)
        if owning_project and owning_project != stack_name:
            print("    skipping %s, it belongs to stack '%s'" % (volume.name, owning_project))
            continue
        volumes.append(volume)
    return volumes


def inspect_volumes(host, volume_names):
    quoted_names = " ".join(quote(name) for name in volume_names)
    inspected = json.loads(host.run("docker volume inspect %s" % quoted_names))
    return [
        DockerVolume(
            entry["Name"],
            entry.get("Driver", ""),
            entry.get("Mountpoint", ""),
            entry.get("Labels"),
        )
        for entry in inspected
    ]


def all_volumes(host):
    """Every docker volume on the host (used to detect the plugin root dataset)."""
    volume_names = host.run("docker volume ls --quiet").split()
    return inspect_volumes(host, volume_names) if volume_names else []


def volume_exists(host, volume_name):
    existing = host.run("docker volume ls --quiet").split()
    return volume_name in existing


def running_containers(host, stack_name):
    output = host.run(
        "docker ps --format '{{.Names}}\t{{.Status}}' "
        "--filter label=com.docker.compose.project=%s" % quote(stack_name)
    )
    return [line for line in output.splitlines() if line.strip()]
