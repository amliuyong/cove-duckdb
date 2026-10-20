"""The AWS account a deployment runs in: never part of the source.

Services receive it as `COVE_ACCOUNT` from their stack. Runtime functions and tasks carry no environment
variables, so they ask STS once per process; GetCallerIdentity needs no IAM permission.
"""

import os
import re

_resolved = None


def account():
    global _resolved
    if _resolved is None:
        value = os.environ.get("COVE_ACCOUNT")
        if value is None:
            import boto3

            value = boto3.client("sts", region_name="us-west-2").get_caller_identity()["Account"]
        if not re.fullmatch(r"[0-9]{12}", value):
            raise RuntimeError("COVE_ACCOUNT must be the 12-digit deployment account")
        _resolved = value
    return _resolved
