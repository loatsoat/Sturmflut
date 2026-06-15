import importlib
import os
import subprocess
import sys


def load_grpc_support(base_dir):
    try:
        grpc = importlib.import_module('grpc')
        candidate_proto_dirs = [
            os.path.join(base_dir, 'proto'),
            os.path.join(os.path.dirname(base_dir), 'leitstelle', 'proto'),
            os.path.join(os.path.dirname(base_dir), 'sensoren', 'proto'),
        ]
        proto_dir = next((path for path in candidate_proto_dirs if os.path.exists(path)), candidate_proto_dirs[0])
        out_dir = os.path.join(base_dir, 'grpc_gen')
        os.makedirs(out_dir, exist_ok=True)

        subprocess.run([
            sys.executable,
            '-m',
            'grpc_tools.protoc',
            f'-I{proto_dir}',
            f'--python_out={out_dir}',
            f'--grpc_python_out={out_dir}',
            os.path.join(proto_dir, 'assignment.proto'),
        ], check=True, capture_output=True)

        if out_dir not in sys.path:
            sys.path.insert(0, out_dir)

        assignment_pb2 = importlib.import_module('assignment_pb2')
        assignment_pb2_grpc = importlib.import_module('assignment_pb2_grpc')
        return grpc, assignment_pb2, assignment_pb2_grpc
    except Exception as exc:
        print('gRPC setup failed:', exc)
        return None, None, None
