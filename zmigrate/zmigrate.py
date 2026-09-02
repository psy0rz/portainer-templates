#!/usr/bin/env python3
"""zmigrate - move a portainer compose stack, including its zfs volumes, between servers.

  zmigrate.py hosts
  zmigrate.py list srv1
  zmigrate.py show srv1 mywebshop
  zmigrate.py migrate srv1 srv2 mywebshop --presync
"""

import argparse
import sys

import config
import docker_volumes
import migrate
from migrate import MigrationError, Server, human_size
from portainer import PortainerError
from remote_host import RemoteCommandError


def build_argument_parser():
    parser = argparse.ArgumentParser(
        prog="zmigrate",
        description="Move a portainer stack and its zfs volumes from one server to another.",
    )
    parser.add_argument("-c", "--config", dest="config_path",
                        help="path to the hosts config (default: ./zmigrate.json or ~/.config/zmigrate/hosts.json)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every ssh command")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("hosts", help="list the configured servers")

    list_command = subcommands.add_parser("list", help="list the stacks on a server")
    list_command.add_argument("host")

    show_command = subcommands.add_parser("show", help="show a stack with its volumes and datasets")
    show_command.add_argument("host")
    show_command.add_argument("stack")

    migrate_command = subcommands.add_parser("migrate", help="migrate a stack between two servers")
    migrate_command.add_argument("source_host")
    migrate_command.add_argument("dest_host")
    migrate_command.add_argument("stack")
    migrate_command.add_argument("--presync", action="store_true",
                                 help="send a first copy while the stack still runs, then only "
                                      "send the difference during downtime")
    migrate_command.add_argument("--direct", action="store_true",
                                 help="stream straight from the source to the destination server "
                                      "(needs ssh access from source to destination)")
    migrate_command.add_argument("--compress", action="store_true",
                                 help="compress the stream with zstd (needs zstd on both servers)")
    migrate_command.add_argument("--dest-root-dataset",
                                 help="parent dataset for the volumes on the destination, "
                                      "overrides the config")
    migrate_command.add_argument("--purge-source-volumes", action="store_true",
                                 help="destroy the source datasets after a successful migration")
    migrate_command.add_argument("--no-rollback", action="store_true",
                                 help="do not restart the stack on the source when something fails")
    migrate_command.add_argument("--verify-delay", type=int, default=10, metavar="SECONDS",
                                 help="wait this long before checking the containers on the "
                                      "destination (default: 10)")
    migrate_command.add_argument("--force", action="store_true",
                                 help="continue even when preflight checks fail")
    migrate_command.add_argument("-y", "--yes", dest="assume_yes", action="store_true",
                                 help="do not ask for confirmation")
    migrate_command.add_argument("-n", "--dry-run", action="store_true",
                                 help="only show what would happen, change nothing")
    return parser


def command_hosts(hosts):
    for name in sorted(hosts):
        host_config = hosts[name]
        print("%-12s %-28s %s" % (name, host_config.ssh_target, host_config.portainer_url))


def command_list(hosts, arguments):
    server = Server(config.get_host(hosts, arguments.host), verbose=arguments.verbose)
    stacks = server.portainer.list_stacks()
    if not stacks:
        print("no stacks on %s" % server.name)
        return
    print("%-6s %-30s %s" % ("ID", "NAME", "STATUS"))
    for stack in sorted(stacks, key=lambda entry: entry.get("Name", "")):
        status = "running" if stack.get("Status") == 1 else "stopped"
        print("%-6s %-30s %s" % (stack.get("Id"), stack.get("Name"), status))


def command_show(hosts, arguments):
    server = Server(config.get_host(hosts, arguments.host), verbose=arguments.verbose)
    stack = server.portainer.find_stack(arguments.stack)
    if not stack:
        raise MigrationError("%s: no stack named '%s'" % (server.name, arguments.stack))

    print("stack:     %s (id %s)" % (stack.get("Name"), stack.get("Id")))
    print("status:    %s" % ("running" if stack.get("Status") == 1 else "stopped"))
    for entry in stack.get("Env") or []:
        print("env:       %s=%s" % (entry.get("name"), entry.get("value")))

    volumes = migrate.resolve_stack_volumes(server, arguments.stack)
    total_bytes = 0
    for volume in volumes:
        total_bytes += volume.used_bytes or 0
        print("volume:    %-38s %-6s %-40s %s"
              % (volume.name, volume.driver, volume.source_dataset or "-",
                 human_size(volume.used_bytes)))
    if volumes:
        print("total:     %s" % human_size(total_bytes))

    for line in docker_volumes.running_containers(server.host, arguments.stack):
        print("container: %s" % line.replace("\t", "  "))


def command_migrate(hosts, arguments):
    source = Server(
        config.get_host(hosts, arguments.source_host),
        dry_run=arguments.dry_run, verbose=arguments.verbose,
    )
    dest = Server(
        config.get_host(hosts, arguments.dest_host),
        dry_run=arguments.dry_run, verbose=arguments.verbose,
    )
    if source.name == dest.name:
        raise MigrationError("source and destination are the same host")
    migrate.migrate_stack(source, dest, arguments.stack, arguments)


def main():
    parser = build_argument_parser()
    arguments = parser.parse_args()
    try:
        hosts = config.load_hosts(arguments.config_path)
        if arguments.command == "hosts":
            command_hosts(hosts)
        elif arguments.command == "list":
            command_list(hosts, arguments)
        elif arguments.command == "show":
            command_show(hosts, arguments)
        elif arguments.command == "migrate":
            command_migrate(hosts, arguments)
    except (config.ConfigError, MigrationError, PortainerError, RemoteCommandError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
