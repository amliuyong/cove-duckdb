"""Qualification and immutable-reference business task entrypoints."""

import hashlib
import importlib
import importlib.metadata
import json
import platform
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from cove_duckdb.contracts.validation import validate
from cove_duckdb.contracts.validation import ContractError
from cove_duckdb.control.http import decode_json
from cove_duckdb.control.registry import ControlError
from .parquet import describe, write


def installed_environment():
    root = Path("/opt/cove")
    environment = json.loads((root / "environment.json").read_text())
    lock = (root / "requirements.lock").read_bytes()
    if (hashlib.sha256(lock).hexdigest() != environment["dependency_lock_sha256"]
            or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != environment["adapter_sha256"]
            or platform.python_version() != environment["python_version"]
            or platform.machine() != "aarch64"):
        raise RuntimeError("ENVIRONMENT_IDENTITY_MISMATCH")
    return environment


def qualify():
    """Check the installed environment without fetching code or business inputs."""
    environment = installed_environment()
    versions = {}
    for package in environment["packages"]:
        name, expected = package["name"], package["version"]
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise RuntimeError("ENVIRONMENT_DEPENDENCY_MISMATCH")
        versions[name] = actual
        for module in package["import_modules"]:
            importlib.import_module(module)
    # Data environments qualify real native wheels, not merely installed metadata.
    if "pandas" in versions and "pyarrow" in versions:
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq

        schema = [
            {"name": "id", "type": "BIGINT", "nullable": False},
            {"name": "amount", "type": "DECIMAL(30,2)", "nullable": False},
            {"name": "observed", "type": "TIMESTAMPTZ", "nullable": False},
            {"name": "tags", "type": "VARCHAR[]", "nullable": False},
            {"name": "payload", "type": "BLOB", "nullable": False},
            {"name": "attributes", "type": "JSON", "nullable": False},
        ]
        row = [9007199254740993, Decimal("900719925474099.01"),
               datetime(2026, 10, 16, tzinfo=timezone.utc), ["typed"], b"\x00\xff", '{"valid":true}']
        with tempfile.TemporaryDirectory(prefix="cove-environment-check-") as directory:
            path = Path(directory) / "typed.parquet"
            descriptor = write(path, schema, [[row]], maximum_rows=1, maximum_bytes=1048576)
            actual = describe(path, schema, maximum_bytes=1048576, expected=descriptor)
            if actual != descriptor:
                raise RuntimeError("ENVIRONMENT_PARQUET_CONTRACT_MISMATCH")
            table = pq.read_table(path)
            first = table.to_pylist()[0]
            if (first["id"] != row[0] or first["amount"] != row[1]
                    or first["observed"] != row[2] or first["tags"] != row[3]
                    or first["payload"] != row[4] or json.loads(first["attributes"]) != {"valid": True}
                    or pa.__version__ != versions["pyarrow"]
                    or pd.Series([row[0]], dtype="int64").iloc[0] != row[0]):
                raise RuntimeError("ENVIRONMENT_TYPED_VALUES_MISMATCH")
            validate("input_manifest", {
                "contract_version": 1, "dataset": "dwd.environment_check", "release_id": "input_check",
                "schema": schema, "watermark": {"ods_sequence": 1}, "files": [{
                    "s3_uri": "s3://qualification-bucket/typed.parquet", "object_version": "check",
                    "sha256": descriptor["sha256"], "rows": 1, "bytes": descriptor["bytes"]}],
            })
    if "duckdb" in versions and "pyarrow" in versions:
        sql_check()
    return {"status": "ENVIRONMENT_IMPORT_AND_CONTRACT_PASS",
            "source_commit": environment["source_commit"],
            "adapter_sha256": environment["adapter_sha256"],
            "dependency_lock_sha256": environment["dependency_lock_sha256"],
            "python_version": platform.python_version(), "platform": "linux_arm64",
            "packages": versions}


def sql_check():
    """The installed DuckDB runs the controlled SQL path and denies external access."""
    import duckdb
    from .sql_task import check_schema, connect, seal, statement

    with tempfile.TemporaryDirectory(prefix="cove-sql-check-") as directory:
        connection = connect(directory, 64 * 1048576)
        try:
            connection.execute("CREATE TABLE source (amount DECIMAL(38,2) NOT NULL)")
            connection.execute("INSERT INTO source VALUES ('999999999999999999999999999999999999.99')")
            seal(connection)
            query = statement(connection, "SELECT CAST(sum(amount) AS DECIMAL(38,2)) AS total FROM source")
            check_schema(connection, query, [{"name": "total", "type": "DECIMAL(38,2)", "nullable": False}])
            if connection.execute(query).fetchone()[0] != Decimal("999999999999999999999999999999999999.99"):
                raise RuntimeError("ENVIRONMENT_SQL_VALUE_MISMATCH")
            try:
                connection.execute("SELECT * FROM read_csv('/etc/hostname')")
            except duckdb.PermissionException:
                pass
            else:
                raise RuntimeError("ENVIRONMENT_SQL_EXTERNAL_ACCESS")
        finally:
            connection.close()


def lambda_handler(event, context):
    if event == {"operation": "environment_check"}:
        return qualify()
    return execute_task(event, "lambda",
                        remaining_seconds=context.get_remaining_time_in_millis() / 1000,
                        invocation={"executor": "lambda", "request_id": context.aws_request_id,
                                    "function_arn": context.invoked_function_arn,
                                    "memory_mb": int(context.memory_limit_in_mb)})


def ecs_identity():
    """The running Fargate task's own ARN from the local ECS metadata endpoint."""
    import os
    from urllib.request import urlopen

    endpoint = os.environ.get("ECS_CONTAINER_METADATA_URI_V4", "")
    if not endpoint.startswith("http://169.254.170.2/"):
        return {"executor": "ecs_task", "task_arn": None}
    with urlopen(endpoint + "/task", timeout=5) as response:
        task = json.load(response)
    return {"executor": "ecs_task", "task_arn": task["TaskARN"],
            "task_definition": task["Family"] + ":" + str(task["Revision"])}


def execute_task(event, executor, *, remaining_seconds=None, invocation=None):
    import boto3
    from botocore.config import Config
    from .task_adapter import TaskAdapter

    environment = installed_environment()
    if environment["executor"] != executor:
        raise RuntimeError("ENVIRONMENT_EXECUTOR_MISMATCH")
    try:
        return TaskAdapter(boto3.client("s3", region_name="us-west-2",
            config=Config(retries={"total_max_attempts": 1}, connect_timeout=3, read_timeout=10)),
            environment).execute(event, remaining_seconds=remaining_seconds, invocation=invocation)
    except ControlError as error:
        return {"status": "UNKNOWN" if error.code == "TASK_UPLOAD_ORIGINAL_UNKNOWN" else "FAILED",
                **getattr(error, "receipt", {}), "code": error.code, "publication_status": "NOT_PUBLISHED"}
    except (ContractError, ValueError, UnicodeError):
        return {"status": "FAILED", "code": "TASK_CONTRACT_INVALID", "publication_status": "NOT_PUBLISHED"}
    except OSError:
        return {"status": "FAILED", "code": "TASK_IO_FAILED", "publication_status": "NOT_PUBLISHED"}


def main():
    arguments = sys.argv[1:]
    if arguments == ["--environment-check"]:
        result = qualify()
    elif len(arguments) == 2 and arguments[0] == "--task-event" and len(arguments[1].encode()) <= 16384:
        result = execute_task(decode_json(arguments[1].encode()), "ecs_task", invocation=ecs_identity())
    else:
        raise ValueError("IMMUTABLE_TASK_EVENT_REQUIRED")
    print(json.dumps(result, sort_keys=True))
    if result.get("status") in {"FAILED", "UNKNOWN"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
