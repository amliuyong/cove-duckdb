"""Only the native writer publishes fixed inputs; normal roles cannot delete them."""

import fnmatch
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("input_infrastructure", ROOT / "infra/template.py")


class InputDeployment(unittest.TestCase):
    def setUp(self):
        module = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(module)
        self.resources = module.template()["Resources"]

    def statements(self, role):
        # A conditional statement (Fn::If) is checked as granted.
        return [value["Fn::If"][1] if "Fn::If" in value else value
                for policy in self.resources[role]["Properties"]["Policies"]
                for value in policy["PolicyDocument"]["Statement"]]

    def actions_for(self, role, key):
        actions = set()
        for statement in self.statements(role):
            resources = statement["Resource"]
            for resource in resources if isinstance(resources, list) else [resources]:
                pattern = resource.get("Fn::Sub", "") if isinstance(resource, dict) else resource
                if fnmatch.fnmatch("${DataBucket.Arn}/" + key, pattern):
                    actions.update(value for value in statement["Action"] if value.startswith("s3:"))
        return actions

    def test_only_writer_can_publish_inputs_and_cannot_reclaim_retained_versions(self):
        key = "spaces/fixture/inputs/gen_original/input_original/exec_original/orders/part-00000.parquet"
        self.assertEqual(self.actions_for("WriterRole", key),
                         {"s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"})
        for role in ["QueryRole", "IntakeRole", "SyncRole", "WriterControlRole"]:
            self.assertFalse(self.actions_for(role, key), role)
        for key in ["spaces/fixture/inputs/unbound/file", "spaces/fixture/other/gen_original/file"]:
            self.assertFalse(self.actions_for("WriterRole", key), key)

    def test_original_version_discovery_is_limited_to_fixed_input_prefixes(self):
        statements = [value for value in self.statements("WriterRole")
                      if "s3:ListBucketVersions" in value["Action"]]
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertEqual(statement["Resource"], {"Fn::GetAtt": ["DataBucket", "Arn"]})
        patterns = statement["Condition"]["StringLike"]["s3:prefix"]
        self.assertTrue(any(fnmatch.fnmatch("spaces/fixture/inputs/gen_original/input_original/file", p)
                            for p in patterns))
        for prefix in ["spaces/fixture/gen_original/warehouse/", "spaces/fixture/query-results/gen_original/file",
                       "spaces/fixture/inputs/unbound/file", "spaces/"]:
            self.assertFalse(any(fnmatch.fnmatch(prefix, p) for p in patterns), prefix)


if __name__ == "__main__":
    unittest.main()
