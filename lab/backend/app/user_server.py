"""lab-user: the demo gRPC user directory. Internal network only; fixed data, no database.

    python -m app.user_server        (listens on :50051, or GRPC_PORT)
"""

import asyncio
import os

from grpc import aio

from app.proto import user_pb2, user_pb2_grpc

DEMO_USERS = {"1": "Alice", "2": "Bob", "3": "Charlie"}
UNKNOWN_NAME = "Unknown"
DEFAULT_PORT = 50051


class UserService(user_pb2_grpc.UserServiceServicer):
    async def GetUser(self, request, context):  # noqa: N802 (generated name)
        return user_pb2.User(id=request.id, name=DEMO_USERS.get(request.id, UNKNOWN_NAME))


def build_server(address: str = f"[::]:{DEFAULT_PORT}") -> tuple[aio.Server, int]:
    server = aio.server()
    user_pb2_grpc.add_UserServiceServicer_to_server(UserService(), server)
    port = server.add_insecure_port(address)
    return server, port


async def serve() -> None:  # pragma: no cover - process entry point
    server, _ = build_server("[::]:" + os.environ.get("GRPC_PORT", str(DEFAULT_PORT)))
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(serve())
