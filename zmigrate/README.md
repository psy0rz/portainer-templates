# zmigrate

Move a Portainer compose stack, *including its ZFS volumes*, from one server to another.

Made for the setup in this repo: identical Docker hosts, Portainer as the stack manager,
Traefik in front, and every Docker volume backed by its own ZFS dataset through
[docker-zfs-plugin](https://github.com/csachs/docker-zfs-plugin).

What it does, in order:

1. Reads the stack (compose file + environment) from Portainer on the source.
2. Finds the stack's Docker volumes and the ZFS dataset behind each one.
3. Preflight: destination stack name free, destination datasets free, `zfs`/`docker` reachable.
4. Optional `--presync`: a full `zfs send` while the stack keeps running.
5. Stops the stack on the source (through the Portainer API).
6. Snapshots and `zfs send | zfs receive`s every volume (incremental after a presync).
7. Creates and deploys the stack on the destination through the Portainer API.
8. Checks that containers are actually running there.
9. Deletes the stack on the source. Source datasets are kept unless you ask otherwise.

If anything fails after step 5, the stack is started again on the source and nothing is
deleted (`--no-rollback` turns that off).

## Requirements

* Python 3.7+ on the machine you run this from (no third-party packages).
* Key-based ssh from your machine to both servers, as a user that may run `zfs` and `docker`.
* A Portainer API key ("access token") per server.
* `--direct` additionally needs ssh from the source server to the destination server.
* `--compress` needs `zstd` on both servers.

## Configuration

Copy the example and fill in your servers:

```sh
cp zmigrate.json.example zmigrate.json
$EDITOR zmigrate.json
chmod 600 zmigrate.json
```

`zmigrate.json` is looked up in the working directory, then `~/.config/zmigrate/hosts.json`,
then `~/.zmigrate.json`; `-c FILE` overrides that. It holds API keys, so it is gitignored.

| field | meaning |
| --- | --- |
| `ssh` | ssh target, e.g. `root@srv1.example.com` |
| `ssh_options` | extra ssh arguments (default `-o BatchMode=yes`) |
| `portainer_url` | base url of Portainer on that server |
| `api_key` | Portainer access token (`ptr_...`) |
| `endpoint_id` | Portainer environment id; only needed when the server has more than one |
| `verify_tls` | set to `false` for a self-signed Portainer certificate |
| `zfs_root_dataset` | parent dataset the zfs plugin manages, e.g. `tank/docker/volumes` |

`zfs_root_dataset` is optional: zmigrate derives it from the existing volumes on the
destination, and otherwise reuses the source's parent dataset.

## Usage

```sh
./zmigrate.py hosts                       # configured servers
./zmigrate.py list srv1                   # stacks on srv1
./zmigrate.py show srv1 mywebshop         # volumes, datasets, sizes, containers

./zmigrate.py migrate srv1 srv2 mywebshop --dry-run
./zmigrate.py migrate srv1 srv2 mywebshop --presync
```

Useful flags for `migrate`:

| flag | effect |
| --- | --- |
| `--presync` | copy first while the stack runs, then only send the difference during downtime |
| `--direct` | stream source → destination directly instead of through your machine |
| `--compress` | pipe the stream through `zstd` |
| `--dest-root-dataset DS` | put the volumes under another parent dataset on the destination |
| `--purge-source-volumes` | destroy the source datasets after a successful migration |
| `--verify-delay N` | seconds to wait before checking containers on the destination (default 10) |
| `-y`, `--yes` | no confirmation questions |
| `-n`, `--dry-run` | print every change without making it |
| `--force` | continue when the *destination* is not empty (never waives a volume it cannot move) |

### Downtime

Without `--presync` the stack is down for the whole transfer. With `--presync` it is down
only for the incremental send plus the deploy, so use it for anything large.

## Safety

The rules that keep a bad run from costing data:

* A volume that is not on zfs, or whose dataset cannot be found, aborts the migration and
  `--force` does not waive it — otherwise the stack would be deleted on the source while
  part of its data stayed behind. `--force` only ignores "the destination already has this".
* A volume that carries another compose project's label is never claimed, even when its name
  starts with this stack's name.
* After receiving, a dataset that is not actually mounted on the destination is fatal:
  containers would otherwise write into the empty mountpoint directory of the parent filesystem.
* Any failure, ctrl-c included, removes the half-migrated stack on the destination and starts
  the stack again on the source. The source is never deleted in that path.
* The source stack is only deleted after containers are seen running on the destination, and
  source datasets are only destroyed (`--purge-source-volumes`) after every dataset is confirmed
  to exist, be mounted, and carry the snapshot that was just sent.
* `zfs destroy` refuses anything that is not clearly one volume dataset - a pool root, an empty
  or half-filled-in name never reaches the command line.
* `--dry-run` is fail-safe, not opt-in: during a dry run every ssh command that is not
  recognisably read-only (`zfs list/get`, `docker volume ls/inspect`, `docker ps`) is refused
  rather than executed, and the Portainer client refuses every non-GET request. So a dry run
  reads state, prints the exact commands it would run, and can change nothing - not even
  through a future command that forgets to mark itself.

## Notes and caveats

* Only volumes with the `zfs` driver are migrated. Bind mounts (like the `./z_fix-*.conf`
  files in these templates) come from the compose file and need no copying; other volume
  drivers make the preflight fail.
* The snapshots that zmigrate makes (`zmigrate-<timestamp>-presync|final`) are kept on both
  sides. Delete them when you no longer need a fallback.
* Source datasets are kept by default, so a rollback is `zmigrate.py migrate srv2 srv1 <stack>`
  after removing the leftovers on srv1, or simply recreating the stack on srv1.
* Volumes keep their name (`<stack>_<volume>`), so the stack must have the same name on both
  servers.
* If `docker volume ls` on the destination does not show a received dataset, restart the zfs
  volume plugin there — it enumerates the datasets under its root dataset at startup.
* DNS/Traefik: the certificate is requested again on the destination, so point the hostname
  at the new server right after the migration.
* zmigrate never touches `/var/lib/docker` itself, only the volume datasets.
