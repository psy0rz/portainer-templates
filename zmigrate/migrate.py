"""Migrating one portainer compose stack, volumes included, from host A to host B."""

import datetime
import sys
import time

import docker_volumes
import portainer
import zfs_datasets
from remote_host import RemoteHost


class MigrationError(Exception):
    pass


class Server:
    """A configured server: ssh access plus its portainer API."""

    def __init__(self, host_config, dry_run=False, verbose=False):
        self.config = host_config
        self.name = host_config.name
        self.host = RemoteHost(host_config, dry_run=dry_run, verbose=verbose)
        self.portainer = portainer.PortainerClient(
            host_config, dry_run=dry_run, verbose=verbose
        )


def human_size(byte_count):
    if byte_count is None:
        return "?"
    size = float(byte_count)
    for unit in ["B", "K", "M", "G", "T", "P"]:
        if size < 1024 or unit == "P":
            return "%.1f%s" % (size, unit)
        size /= 1024


def step(message):
    print("\n==> %s" % message, flush=True)


def snapshot_label(suffix):
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    return "zmigrate-%s-%s" % (stamp, suffix)


def confirm(question, assume_yes):
    if assume_yes:
        return True
    try:
        answer = input("%s [y/N] " % question).strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def resolve_stack_volumes(server, stack_name):
    """Volumes of the stack on this server, with their zfs datasets filled in."""
    volumes = docker_volumes.stack_volumes(server.host, stack_name)
    if not volumes:
        return []

    mountpoint_map = zfs_datasets.dataset_by_mountpoint(server.host)
    for volume in volumes:
        volume.source_dataset = mountpoint_map.get(volume.mountpoint)
        if volume.source_dataset:
            volume.used_bytes = zfs_datasets.used_bytes(server.host, volume.source_dataset)
    return volumes


def preflight(source, dest, stack_name, volumes, dest_root_dataset, force):
    """Checks everything that must hold before a single byte is moved.

    Fatal problems are about data that zmigrate cannot move at all; they are never
    waived, because the stack would be deleted on the source while part of its data
    stayed behind. Only the 'destination is not empty' problems can be forced.
    """
    fatal_problems = []
    forceable_problems = []

    for server in (source, dest):
        for required_command in ("zfs", "docker"):
            if not server.host.command_exists(required_command):
                fatal_problems.append(
                    "%s: '%s' not available over ssh" % (server.name, required_command)
                )

    if dest.portainer.find_stack(stack_name):
        forceable_problems.append(
            "%s: a stack named '%s' already exists" % (dest.name, stack_name)
        )

    for volume in volumes:
        if not volume.is_zfs:
            fatal_problems.append(
                "volume '%s' uses driver '%s', not zfs (zmigrate only moves zfs volumes)"
                % (volume.name, volume.driver)
            )
        elif not volume.source_dataset:
            fatal_problems.append(
                "volume '%s' has no zfs dataset for mountpoint %s"
                % (volume.name, volume.mountpoint)
            )
        else:
            # The plugin either names a volume after the dataset leaf ("shop_db") or
            # after its full path ("tank/docker/volumes/shop_db"); keep whichever it uses.
            if "/" in volume.name:
                dest_dataset = volume.name
            else:
                dest_dataset = "%s/%s" % (dest_root_dataset, volume.name)
            volume.dest_dataset = dest_dataset
            if zfs_datasets.dataset_exists(dest.host, dest_dataset):
                forceable_problems.append(
                    "%s: dataset %s already exists" % (dest.name, dest_dataset)
                )
            if docker_volumes.volume_exists(dest.host, volume.name):
                forceable_problems.append(
                    "%s: docker volume %s already exists" % (dest.name, volume.name)
                )

    if forceable_problems and force:
        print("preflight problems ignored because of --force:")
        for problem in forceable_problems:
            print("  ! %s" % problem)
        forceable_problems = []

    problems = fatal_problems + forceable_problems
    if problems:
        raise MigrationError("preflight failed:\n  - %s" % "\n  - ".join(problems))


def transfer_volumes(
    source, dest, volumes, snapshot_name, from_snapshot=None, direct=False,
    compress=False, dry_run=False,
):
    for volume in volumes:
        zfs_datasets.create_snapshot(source.host, volume.source_dataset, snapshot_name)
        print(
            "    %s  %s -> %s  (%s%s)"
            % (
                volume.name,
                volume.source_dataset,
                volume.dest_dataset,
                human_size(volume.used_bytes),
                ", incremental" if from_snapshot else "",
            )
        )
        zfs_datasets.send_receive(
            source.host,
            dest.host,
            volume.source_dataset,
            volume.dest_dataset,
            snapshot_name,
            from_snapshot=from_snapshot,
            direct=direct,
            compress=compress,
            dry_run=dry_run,
        )
        zfs_datasets.finish_receive(
            dest.host, source.host, volume.source_dataset, volume.dest_dataset,
            dry_run=dry_run,
        )


def verify_received(dest, volumes, final_snapshot, dry_run):
    """Names of datasets whose arrival on the destination could not be confirmed.

    Source data is only ever destroyed when every volume exists on the destination,
    is mounted, and carries the snapshot that was just sent.
    """
    if dry_run:
        return [volume.dest_dataset for volume in volumes]

    unconfirmed = []
    for volume in volumes:
        arrived = (
            volume.dest_dataset
            and zfs_datasets.dataset_exists(dest.host, volume.dest_dataset)
            and zfs_datasets.is_mounted(dest.host, volume.dest_dataset)
            and (
                final_snapshot is None
                or zfs_datasets.snapshot_exists(dest.host, volume.dest_dataset, final_snapshot)
            )
        )
        if not arrived:
            unconfirmed.append(volume.dest_dataset or volume.name)
    return unconfirmed


def migrate_stack(source, dest, stack_name, options):
    dry_run = options.dry_run
    if dry_run:
        print("DRY RUN: nothing is stopped, sent, created or deleted.")

    step("Reading stack '%s' from %s" % (stack_name, source.name))
    source_stack = source.portainer.find_stack(stack_name)
    if not source_stack:
        raise MigrationError("%s: no stack named '%s'" % (source.name, stack_name))
    compose_text = source.portainer.get_stack_file(source_stack["Id"])
    stack_environment = portainer.environment_of(source_stack)
    print("    stack id %s, %d env var(s), %d bytes of compose"
          % (source_stack["Id"], len(stack_environment), len(compose_text)))

    step("Collecting volumes")
    volumes = resolve_stack_volumes(source, stack_name)
    if not volumes:
        print("    (this stack has no docker volumes)")
    for volume in volumes:
        print("    %-40s %-6s %s (%s)"
              % (volume.name, volume.driver, volume.source_dataset, human_size(volume.used_bytes)))

    dest_root_dataset = options.dest_root_dataset or dest.config.zfs_root_dataset
    if not dest_root_dataset and volumes:
        dest_root_dataset = zfs_datasets.detect_root_dataset(
            dest.host, docker_volumes.all_volumes(dest.host)
        )
        if dest_root_dataset:
            print("    detected zfs root dataset on %s: %s" % (dest.name, dest_root_dataset))
    if not dest_root_dataset and volumes:
        source_roots = {zfs_datasets.parent_dataset(v.source_dataset) for v in volumes if v.source_dataset}
        if len(source_roots) == 1:
            dest_root_dataset = source_roots.pop()
            print("    using the source root dataset on %s: %s" % (dest.name, dest_root_dataset))
    if not dest_root_dataset and volumes:
        raise MigrationError(
            "cannot determine the zfs root dataset on %s, set 'zfs_root_dataset' in the "
            "config or pass --dest-root-dataset" % dest.name
        )

    step("Preflight checks")
    preflight(source, dest, stack_name, volumes, dest_root_dataset, options.force)
    print("    ok")

    if not confirm(
        "Migrate stack '%s' from %s to %s?" % (stack_name, source.name, dest.name),
        options.assume_yes or dry_run,
    ):
        raise MigrationError("aborted by user")

    presync_snapshot = None
    if volumes and options.presync:
        step("Pre-sync while the stack keeps running (reduces downtime)")
        presync_snapshot = snapshot_label("presync")
        transfer_volumes(
            source, dest, volumes, presync_snapshot, direct=options.direct,
            compress=options.compress, dry_run=dry_run,
        )

    step("Stopping stack on %s" % source.name)
    source.portainer.stop_stack(source_stack["Id"])

    created_stack_id = None
    final_snapshot = None
    try:
        if volumes:
            step("Transferring volumes")
            final_snapshot = snapshot_label("final")
            transfer_volumes(
                source, dest, volumes, final_snapshot,
                from_snapshot=presync_snapshot, direct=options.direct,
                compress=options.compress, dry_run=dry_run,
            )

        step("Creating stack on %s" % dest.name)
        created_stack = dest.portainer.create_compose_stack(
            stack_name, compose_text, stack_environment
        )
        created_stack_id = created_stack.get("Id")
        if not dry_run:
            print("    created stack id %s" % created_stack_id)

        step("Verifying the stack on %s" % dest.name)
        if dry_run:
            print("    (dry-run) skipped")
        else:
            time.sleep(options.verify_delay)
            container_lines = docker_volumes.running_containers(dest.host, stack_name)
            for line in container_lines:
                print("    %s" % line.replace("\t", "  "))
            if not container_lines:
                raise MigrationError(
                    "no running containers for '%s' on %s after deploy"
                    % (stack_name, dest.name)
                )
    except BaseException as migration_error:
        # BaseException so that a ctrl-c during the transfer rolls back too, instead
        # of leaving the stack stopped on both servers.
        print("\n!! migration failed: %s" % migration_error, file=sys.stderr)
        if options.no_rollback:
            print("!! --no-rollback: the stack stays stopped on %s" % source.name,
                  file=sys.stderr)
            raise

        if created_stack_id:
            # Never leave both copies running: the destination one is the incomplete one.
            print("!! removing the half-migrated stack on %s" % dest.name, file=sys.stderr)
            try:
                dest.portainer.delete_stack(created_stack_id)
            except Exception as cleanup_error:
                print("!! could not remove it, do it by hand: %s" % cleanup_error,
                      file=sys.stderr)
        for volume in volumes:
            if volume.dest_dataset:
                print("!! received data kept on %s: %s (destroy it before retrying)"
                      % (dest.name, volume.dest_dataset), file=sys.stderr)

        print("!! restarting the stack on %s" % source.name, file=sys.stderr)
        source.portainer.start_stack(source_stack["Id"])
        raise

    step("Removing stack '%s' from %s" % (stack_name, source.name))
    if confirm("Delete the stack on %s now?" % source.name, options.assume_yes or dry_run):
        source.portainer.delete_stack(source_stack["Id"])
        print("    stack %s (volumes kept)" % ("would be deleted" if dry_run else "deleted"))
    else:
        print("    kept, the stack stays stopped on %s" % source.name)
        return

    if volumes and dry_run:
        print("\n(dry-run) source datasets on %s would be kept until verified" % source.name)
    elif volumes:
        unconfirmed_datasets = verify_received(dest, volumes, final_snapshot, dry_run)
        if unconfirmed_datasets:
            print("\n!! not offering to destroy anything on %s: could not confirm %s on %s"
                  % (source.name, ", ".join(unconfirmed_datasets), dest.name),
                  file=sys.stderr)
        elif options.purge_source_volumes and confirm(
            "Destroy the %d source dataset(s) on %s?" % (len(volumes), source.name),
            options.assume_yes,
        ):
            step("Destroying source datasets on %s" % source.name)
            for volume in volumes:
                print("    zfs destroy -r %s" % volume.source_dataset)
                zfs_datasets.destroy_dataset(source.host, volume.source_dataset)
        else:
            print("\nSource data kept on %s. Remove it when you are happy with %s:"
                  % (source.name, dest.name))
            for volume in volumes:
                print("    ssh %s zfs destroy -r %s"
                      % (source.host.ssh_target, volume.source_dataset))

    if dry_run:
        step("Dry run finished: nothing was changed on %s or %s" % (source.name, dest.name))
    else:
        step("Done: '%s' now runs on %s" % (stack_name, dest.name))
