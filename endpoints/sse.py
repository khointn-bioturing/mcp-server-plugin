import uuid
import time
import json
import logging

from typing import Mapping
from werkzeug import Request, Response
from dify_plugin import Endpoint
from dify_plugin.config.logger_format import plugin_logger_handler

import asyncio
from fastmcp import Client, FastMCP
from fastmcp.client.transports import SSETransport
import json

from .auth import validate_bearer_token

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

with open("config.json", "r") as f:
    config = json.load(f)

def create_sse_message(event, data):
    return f"event: {event}\ndata: {json.dumps(data) if isinstance(data, (dict, list)) else data}\n\n"


class SSEEndpoint(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        Invokes the endpoint with the given request.
        """
        logger.info(f"SSEEndpoint request headers: {r.headers}")

        auth_error = validate_bearer_token(r, settings)
        if auth_error:
            return auth_error
        
        session_id = str(uuid.uuid4()).replace("-", "")
        session_id = r.args.get("session_id")
        data_headers = dict(r.headers.to_wsgi_list())
        tool = json.loads(settings.get("app-input-schema"))

        if not config["ALREADY_REGISTERED"]:
            MCP_GATEWAY_URL = f"{config['MCP_GATEWAY_PROTOCOL']}://{config['MCP_GATEWAY_HOST']}:{config['MCP_GATEWAY_PORT']}/{config['MCP_GATEWAY_PATH']}"
            DIFY_HOOK_URL =f'{data_headers["X-Forwarded-Proto"]}://{data_headers["Host"]}:{data_headers["X-Forwarded-Port"]}/e/{data_headers["Dify-Hook-Id"]}/mcp'
            DIFY_APP_DESCRIPTION = tool['description']
            
            async def register_new_mcp():
                client = Client(SSETransport(MCP_GATEWAY_URL))
                async with client:
                    res = await client.call_tool(
                        "register_mcp",
                        {
                            "name": "bioflexwf-mcp-server",
                            "description": DIFY_APP_DESCRIPTION,
                            "address": DIFY_HOOK_URL
                        }
                    )

            asyncio.run(register_new_mcp())
            config["ALREADY_REGISTERED"] = True

        def generate():
            endpoint = f"messages/?session_id={session_id}"
            yield create_sse_message("endpoint", endpoint)

            while True:
                message = None
                if self.session.storage.exist(session_id):
                    message = self.session.storage.get(session_id)
                    message = message.decode()
                    self.session.storage.delete(session_id)
                    yield create_sse_message("message", message)
                time.sleep(0.5)    

        return Response(generate(), status=200, content_type="text/event-stream")
