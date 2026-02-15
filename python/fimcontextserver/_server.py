"""JSON-RPC 2.0 protocol loop over stdin/stdout (newline-delimited)."""

import json
import logging
import sys

from fimcontextserver._handler import Handler

log = logging.getLogger(__name__)


class Server:
    def __init__(self):
        self._handler = Handler()

    def run(self):
        """Read JSON-RPC requests from stdin, dispatch, write responses to stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            response = self._handle_line(line)
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()

            if self._handler.should_exit:
                break

    def _handle_line(self, line: str) -> dict | None:
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            log.warning("malformed JSON: %s", e)
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"parse error: {e}"},
            }

        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if not method:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "missing method"},
            }

        log.debug("request: method=%s id=%s", method, req_id)

        dispatch = {
            "initialize": self._handler.handle_initialize,
            "getContext": self._handler.handle_get_context,
            "shutdown": self._handler.handle_shutdown,
        }

        handler_fn = dispatch.get(method)
        if handler_fn is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"unknown method: {method}"},
            }

        try:
            result = handler_fn(params)
        except Exception as e:
            log.exception("handler error for %s", method)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(e)},
            }

        return {"jsonrpc": "2.0", "id": req_id, "result": result}
