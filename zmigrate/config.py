"""Loading and validation of the zmigrate host configuration."""

import json
import os

CONFIG_SEARCH_PATHS = [
    "./zmigrate.json",
    "~/.config/zmigrate/hosts.json",
    "~/.zmigrate.json",
]

REQUIRED_HOST_FIELDS = ["ssh", "portainer_url", "api_key"]


class ConfigError(Exception):
    pass


class HostConfig:
    """Everything zmigrate needs to talk to one portainer/docker/zfs server."""

    def __init__(self, name, settings):
        self.name = name
        missing_fields = [f for f in REQUIRED_HOST_FIELDS if not settings.get(f)]
        if missing_fields:
            raise ConfigError(
                "host '%s' is missing required field(s): %s"
                % (name, ", ".join(missing_fields))
            )

        self.ssh_target = settings["ssh"]
        self.ssh_options = settings.get("ssh_options", ["-o", "BatchMode=yes"])
        self.portainer_url = settings["portainer_url"].rstrip("/")
        self.api_key = settings["api_key"]
        self.endpoint_id = settings.get("endpoint_id")
        self.verify_tls = settings.get("verify_tls", True)
        # Parent dataset that the docker-zfs-plugin manages, e.g. "tank/docker/volumes".
        # Optional: autodetected from the existing volumes on the host when absent.
        self.zfs_root_dataset = settings.get("zfs_root_dataset")

    def __repr__(self):
        return "HostConfig(%s, %s)" % (self.name, self.ssh_target)


def find_config_file(explicit_path=None):
    if explicit_path:
        expanded = os.path.expanduser(explicit_path)
        if not os.path.exists(expanded):
            raise ConfigError("config file not found: %s" % explicit_path)
        return expanded

    for candidate in CONFIG_SEARCH_PATHS:
        expanded = os.path.expanduser(candidate)
        if os.path.exists(expanded):
            return expanded

    raise ConfigError(
        "no config file found, looked in: %s (see zmigrate.json.example)"
        % ", ".join(CONFIG_SEARCH_PATHS)
    )


def load_hosts(explicit_path=None):
    """Returns {host name: HostConfig}."""
    config_path = find_config_file(explicit_path)
    with open(config_path) as config_file:
        try:
            document = json.load(config_file)
        except ValueError as parse_error:
            raise ConfigError("%s is not valid json: %s" % (config_path, parse_error))

    host_settings = document.get("hosts")
    if not isinstance(host_settings, dict) or not host_settings:
        raise ConfigError("%s has no 'hosts' object" % config_path)

    return {name: HostConfig(name, settings) for name, settings in host_settings.items()}


def get_host(hosts, name):
    if name not in hosts:
        raise ConfigError(
            "unknown host '%s', configured hosts: %s" % (name, ", ".join(sorted(hosts)))
        )
    return hosts[name]
