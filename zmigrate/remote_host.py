"""Running shell commands on a portainer server over ssh."""

import json
import shlex
import subprocess
import sys


# Commands that only read state. In dry-run mode a command must either be marked
# changes_state=True (then it is printed, never executed) or consist purely of these,
# so a new mutating command can never quietly run during a dry run.
READ_ONLY_COMMANDS = [
    "zfs list",
    "zfs get",
    "docker volume ls",
    "docker volume inspect",
    "docker ps",
    "docker inspect",
    "docker compose ls",
    "command -v",
    "true",
]

SHELL_OPERATORS = ["&&", "||", ";", "|"]


class DryRunViolation(Exception):
    """A command that is not known to be read-only tried to run during a dry run."""


def is_read_only_command(remote_command):
    """True when every part of the shell command only reads state."""
    segments = [remote_command]
    for operator in SHELL_OPERATORS:
        segments = [part for segment in segments for part in segment.split(operator)]
    for segment in segments:
        stripped = segment.strip()
        if not stripped:
            return False
        if not any(stripped.startswith(prefix) for prefix in READ_ONLY_COMMANDS):
            return False
    return True


class RemoteCommandError(Exception):
    def __init__(self, host_name, remote_command, exit_code, stderr_text):
        self.host_name = host_name
        self.remote_command = remote_command
        self.exit_code = exit_code
        self.stderr_text = stderr_text
        super().__init__(
            "[%s] command failed (exit %s): %s\n%s"
            % (host_name, exit_code, remote_command, stderr_text.strip())
        )


def quote(value):
    """Shell-quote a single argument for use inside a remote command string."""
    return shlex.quote(str(value))


class RemoteHost:
    """Executes commands on one server. All commands are plain shell strings."""

    def __init__(self, host_config, dry_run=False, verbose=False):
        self.name = host_config.name
        self.ssh_target = host_config.ssh_target
        self.ssh_options = list(host_config.ssh_options)
        self.dry_run = dry_run
        self.verbose = verbose

    def ssh_argv(self, remote_command):
        return ["ssh"] + self.ssh_options + [self.ssh_target, remote_command]

    def run(self, remote_command, check=True, capture_output=True, changes_state=False):
        """Runs remote_command on the host and returns its stdout as text.

        Commands marked with changes_state=True are only printed in dry-run mode.
        """
        if self.dry_run:
            if changes_state:
                print("[%s] (dry-run) %s" % (self.name, remote_command))
                return ""
            if not is_read_only_command(remote_command):
                raise DryRunViolation(
                    "[%s] refusing to run an unrecognised command during a dry run: %s"
                    % (self.name, remote_command)
                )

        if self.verbose:
            print("[%s] %s" % (self.name, remote_command), file=sys.stderr)

        completed = subprocess.run(
            self.ssh_argv(remote_command),
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
        )
        stdout_text = completed.stdout or ""
        stderr_text = completed.stderr or ""
        if check and completed.returncode != 0:
            raise RemoteCommandError(
                self.name, remote_command, completed.returncode, stderr_text
            )
        return stdout_text

    def run_json(self, remote_command):
        output = self.run(remote_command)
        return json.loads(output) if output.strip() else None

    def command_exists(self, command_name):
        result = subprocess.run(
            self.ssh_argv("command -v %s" % quote(command_name)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.returncode == 0


def run_local_pipeline(pipeline, dry_run=False, description=None):
    """Runs a local /bin/bash pipeline (used to pipe zfs send into zfs recv)."""
    if description:
        print(description)
    if dry_run:
        print("(dry-run) %s" % pipeline)
        return

    completed = subprocess.run(
        ["/bin/bash", "-o", "pipefail", "-c", pipeline], text=True
    )
    if completed.returncode != 0:
        raise RemoteCommandError(
            "local", pipeline, completed.returncode, "pipeline failed"
        )
