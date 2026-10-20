"""Stack and runtime resource names of one Cove deployment environment.

Every environment is an independent installation named by COVE_ENVIRONMENT: its stacks and the runtime
resources its environment builder creates never share a name or an IAM wildcard with another environment.
"""

import os
import re

RESERVED = {"env", "core", "control", "builder"}


def environment_name(value=None):
    name = value or os.environ.get("COVE_ENVIRONMENT", "")
    if not re.fullmatch(r"[a-z][a-z0-9]{1,11}", name) or name in RESERVED:
        raise RuntimeError("Set COVE_ENVIRONMENT to 2-12 lowercase letters/digits (not env, core, control or builder)")
    return name


def names(value=None):
    name = environment_name(value)
    return {"environment": name, "baseline": "cove-duck-" + name + "-core", "control": "cove-duck-" + name + "-control",
            "environments": "cove-duck-" + name + "-builder", "runtime_prefix": "cove-duck-" + name + "-env-"}
