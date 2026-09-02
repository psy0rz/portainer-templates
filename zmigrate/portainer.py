"""Minimal Portainer CE API client (stdlib only)."""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

STACK_TYPE_COMPOSE = 2


class PortainerError(Exception):
    pass


class PortainerClient:
    def __init__(self, host_config, dry_run=False, verbose=False):
        self.host_name = host_config.name
        self.base_url = host_config.portainer_url
        self.api_key = host_config.api_key
        self.configured_endpoint_id = host_config.endpoint_id
        self.dry_run = dry_run
        self.verbose = verbose
        self.ssl_context = None
        if not host_config.verify_tls:
            self.ssl_context = ssl.create_default_context()
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

    # -- plumbing ---------------------------------------------------------

    def _request(self, method, path, query=None, body=None, changes_state=False):
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)

        if self.dry_run:
            if changes_state:
                print("[%s] (dry-run) %s %s" % (self.host_name, method, url))
                return {}
            if method != "GET":
                raise PortainerError(
                    "[%s] refusing to send %s %s during a dry run" % (self.host_name, method, url)
                )

        encoded_body = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=encoded_body, method=method)
        request.add_header("X-API-Key", self.api_key)
        if encoded_body is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, context=self.ssl_context) as response:
                payload = response.read().decode()
        except urllib.error.HTTPError as http_error:
            detail = http_error.read().decode(errors="replace")
            raise PortainerError(
                "[%s] %s %s failed: %s %s\n%s"
                % (self.host_name, method, url, http_error.code, http_error.reason, detail)
            )
        except urllib.error.URLError as url_error:
            raise PortainerError("[%s] cannot reach %s: %s" % (self.host_name, url, url_error))

        return json.loads(payload) if payload.strip() else {}

    # -- endpoints (docker environments) ----------------------------------

    def endpoint_id(self):
        """The portainer environment id to operate on."""
        if self.configured_endpoint_id is not None:
            return self.configured_endpoint_id

        endpoints = self._request("GET", "/api/endpoints")
        if not endpoints:
            raise PortainerError("[%s] portainer has no environments" % self.host_name)
        if len(endpoints) > 1:
            names = ", ".join("%s=%s" % (e["Id"], e["Name"]) for e in endpoints)
            raise PortainerError(
                "[%s] multiple portainer environments (%s), set 'endpoint_id' in the config"
                % (self.host_name, names)
            )
        return endpoints[0]["Id"]

    # -- stacks -----------------------------------------------------------

    def list_stacks(self):
        return self._request("GET", "/api/stacks") or []

    def find_stack(self, stack_name):
        for stack in self.list_stacks():
            if stack.get("Name") == stack_name:
                return stack
        return None

    def get_stack_file(self, stack_id):
        response = self._request("GET", "/api/stacks/%s/file" % stack_id)
        return response.get("StackFileContent", "")

    def create_compose_stack(self, stack_name, compose_text, environment):
        """Creates and deploys a standalone compose stack, returns the new stack."""
        body = {
            "name": stack_name,
            "stackFileContent": compose_text,
            "env": environment,
            "fromAppTemplate": False,
        }
        query = {"endpointId": self.endpoint_id()}
        try:
            return self._request(
                "POST",
                "/api/stacks/create/standalone/string",
                query=query,
                body=body,
                changes_state=True,
            )
        except PortainerError as create_error:
            if "404" not in str(create_error):
                raise
            # Portainer older than 2.15 only knows the generic create route.
            legacy_query = dict(query, type=STACK_TYPE_COMPOSE, method="string")
            return self._request(
                "POST", "/api/stacks", query=legacy_query, body=body, changes_state=True
            )

    def stop_stack(self, stack_id):
        return self._request(
            "POST",
            "/api/stacks/%s/stop" % stack_id,
            query={"endpointId": self.endpoint_id()},
            changes_state=True,
        )

    def start_stack(self, stack_id):
        return self._request(
            "POST",
            "/api/stacks/%s/start" % stack_id,
            query={"endpointId": self.endpoint_id()},
            changes_state=True,
        )

    def delete_stack(self, stack_id):
        return self._request(
            "DELETE",
            "/api/stacks/%s" % stack_id,
            query={"endpointId": self.endpoint_id(), "external": "false"},
            changes_state=True,
        )


def environment_of(stack):
    """The stack Env list in the shape the create call expects."""
    return [
        {"name": entry.get("name"), "value": entry.get("value")}
        for entry in (stack.get("Env") or [])
    ]
