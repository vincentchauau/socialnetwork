"""gRPC client for lab-user: ONE channel for the life of the process."""

import grpc
from grpc import aio

from app.interfaces import Unavailable
from app.proto import user_pb2, user_pb2_grpc

CALL_TIMEOUT_SECONDS = 2.0


class GrpcUserDirectory:
    def __init__(self, target: str = "lab-user:50051", channel: aio.Channel | None = None) -> None:
        self._channel = channel or aio.insecure_channel(target)
        self._stub = user_pb2_grpc.UserServiceStub(self._channel)

    async def get_user(self, user_id: str, timeout: float = CALL_TIMEOUT_SECONDS) -> str:
        try:
            reply = await self._stub.GetUser(user_pb2.GetUserRequest(id=user_id), timeout=timeout)
        except grpc.RpcError as exc:
            raise Unavailable("grpc") from exc
        return reply.name

    async def ping(self) -> bool:
        try:
            await self.get_user("1", timeout=1.0)
        except Unavailable:
            return False
        return True

    async def close(self) -> None:
        await self._channel.close()
