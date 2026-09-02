"""ZFS dataset lookups and zfs send/recv between two hosts."""

from remote_host import quote, run_local_pipeline


class ZfsError(Exception):
    pass


def dataset_by_mountpoint(host):
    """Returns {mountpoint: dataset name} for all filesystems on the host."""
    output = host.run("zfs list -H -t filesystem -o name,mountpoint")
    mapping = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        dataset_name, mountpoint = line.split("\t", 1)
        mapping[mountpoint] = dataset_name
    return mapping


def dataset_exists(host, dataset):
    output = host.run(
        "zfs list -H -o name %s 2>/dev/null || true" % quote(dataset)
    ).strip()
    return output == dataset


def snapshot_exists(host, dataset, snapshot_name):
    full_name = "%s@%s" % (dataset, snapshot_name)
    output = host.run(
        "zfs list -H -t snapshot -o name %s 2>/dev/null || true" % quote(full_name)
    ).strip()
    return output == full_name


def list_snapshots(host, dataset):
    output = host.run(
        "zfs list -H -t snapshot -o name -s creation -d 1 %s 2>/dev/null || true"
        % quote(dataset)
    )
    return [line.split("@", 1)[1] for line in output.splitlines() if "@" in line]


def used_bytes(host, dataset):
    output = host.run("zfs list -H -p -o used %s" % quote(dataset)).strip()
    return int(output) if output.isdigit() else None


def local_mountpoint(host, dataset):
    """The mountpoint only when it is set on the dataset itself, else None."""
    output = host.run(
        "zfs get -H -o source,value mountpoint %s" % quote(dataset)
    ).strip()
    if not output:
        return None
    property_source, mountpoint = output.split("\t", 1)
    return mountpoint if property_source == "local" else None


def create_snapshot(host, dataset, snapshot_name):
    host.run(
        "zfs snapshot %s" % quote("%s@%s" % (dataset, snapshot_name)),
        changes_state=True,
    )


def destroy_snapshot(host, dataset, snapshot_name):
    host.run(
        "zfs destroy %s" % quote("%s@%s" % (dataset, snapshot_name)),
        check=False,
        changes_state=True,
    )


def assert_destroyable(dataset):
    """Refuses anything that is not clearly one volume dataset.

    Guards against destroying a pool root or a half-filled-in name: 'zfs destroy -r'
    on 'tank' would take the whole server with it.
    """
    if not dataset or not dataset.strip():
        raise ZfsError("refusing to destroy an empty dataset name")
    if dataset.strip() != dataset or "@" in dataset or dataset.endswith("/"):
        raise ZfsError("refusing to destroy suspicious dataset name %r" % dataset)
    if len(dataset.split("/")) < 2:
        raise ZfsError(
            "refusing to destroy %r: that is a pool root, not a volume dataset" % dataset
        )


def destroy_dataset(host, dataset):
    assert_destroyable(dataset)
    host.run("zfs destroy -r %s" % quote(dataset), changes_state=True)


def is_mounted(host, dataset):
    return host.run("zfs get -H -o value mounted %s" % quote(dataset)).strip() == "yes"


def parent_dataset(dataset):
    return dataset.rsplit("/", 1)[0] if "/" in dataset else dataset


def detect_root_dataset(host, docker_volumes):
    """Guesses the dataset the docker-zfs-plugin manages, from existing volumes."""
    mountpoint_map = dataset_by_mountpoint(host)
    parents = set()
    for volume in docker_volumes:
        dataset = mountpoint_map.get(volume.mountpoint)
        if dataset:
            parents.add(parent_dataset(dataset))
    if len(parents) == 1:
        return parents.pop()
    return None


def send_receive(
    source_host,
    dest_host,
    source_dataset,
    dest_dataset,
    snapshot_name,
    from_snapshot=None,
    direct=False,
    compress=False,
    dry_run=False,
):
    """Streams one dataset to the other host.

    direct=False pipes the stream through this machine (A -> here -> B),
    direct=True lets host A ssh straight into host B (needs ssh access A -> B).
    """
    # The hosts decide too: a dry-run host must never end up in a real stream.
    dry_run = dry_run or source_host.dry_run or dest_host.dry_run
    send_command = "zfs send -Lce -p -v"
    if from_snapshot:
        send_command += " -i %s" % quote("@" + from_snapshot)
    send_command += " %s" % quote("%s@%s" % (source_dataset, snapshot_name))

    receive_command = "zfs receive -u %s" % quote(dest_dataset)
    if from_snapshot:
        receive_command = "zfs receive -u -F %s" % quote(dest_dataset)

    if compress:
        send_command += " | zstd -3 -T0"
        receive_command = "zstd -d | " + receive_command

    source_ssh = " ".join(quote(part) for part in source_host.ssh_argv(send_command))
    dest_ssh = " ".join(quote(part) for part in dest_host.ssh_argv(receive_command))

    if direct:
        inner = "%s | ssh %s %s %s" % (
            send_command,
            " ".join(quote(option) for option in dest_host.ssh_options),
            quote(dest_host.ssh_target),
            quote(receive_command),
        )
        pipeline = " ".join(quote(part) for part in source_host.ssh_argv(inner))
    else:
        pipeline = "%s | %s" % (source_ssh, dest_ssh)

    run_local_pipeline(pipeline, dry_run=dry_run)


def finish_receive(dest_host, source_host, source_dataset, dest_dataset, dry_run=False):
    """Applies a locally-set mountpoint, mounts the received dataset and checks it.

    An unmounted dataset is fatal: the containers on the destination would happily
    write into the empty mountpoint directory of the parent filesystem instead.
    """
    dry_run = dry_run or source_host.dry_run or dest_host.dry_run
    mountpoint = local_mountpoint(source_host, source_dataset)
    if mountpoint:
        dest_host.run(
            "zfs set mountpoint=%s %s" % (quote(mountpoint), quote(dest_dataset)),
            changes_state=True,
        )
    dest_host.run(
        "zfs mount %s 2>/dev/null || true" % quote(dest_dataset), changes_state=True
    )
    if dry_run:
        return
    if not is_mounted(dest_host, dest_dataset):
        raise ZfsError(
            "%s is not mounted on %s after receiving it; check its mountpoint and "
            "canmount properties" % (dest_dataset, dest_host.name)
        )
