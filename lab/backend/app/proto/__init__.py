"""gRPC stubs for user.proto.

The generated modules are NOT committed: the Dockerfile generates them at image build, and importing this
package generates them on first use (tests, local runs) with grpcio-tools. protoc emits absolute imports
(`import user_pb2`), so this directory is put on sys.path.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def ensure_generated() -> None:
    if (HERE / "user_pb2.py").exists() and (HERE / "user_pb2_grpc.py").exists():
        return
    command = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{HERE}", f"--python_out={HERE}", f"--grpc_python_out={HERE}", str(HERE / "user.proto"),
    ]
    subprocess.run(command, check=True)


ensure_generated()
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import user_pb2  # noqa: E402
import user_pb2_grpc  # noqa: E402

__all__ = ["user_pb2", "user_pb2_grpc"]
