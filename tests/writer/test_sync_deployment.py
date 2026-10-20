"""Public proxy isolation is enforced by the generated deployment boundary."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("sync_infrastructure", ROOT / "infra/template.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SyncDeployment(unittest.TestCase):
    def setUp(self):
        self.template = MODULE.template()
        self.resources = self.template["Resources"]

    def test_only_sync_security_group_reaches_business_write_listener(self):
        ingress = [value["Properties"] for value in self.resources.values()
                   if value["Type"] == "AWS::EC2::SecurityGroupIngress"
                   and value["Properties"]["GroupId"] == {"Ref": "WriterSecurityGroup"}]
        allowed = [item for item in ingress if item["FromPort"] <= 8082 <= item["ToPort"]]
        self.assertEqual(len(allowed), 1)
        self.assertEqual(allowed[0]["SourceSecurityGroupId"], {"Ref": "SyncSecurityGroup"})
        self.assertNotIn("CidrIp", allowed[0])
        self.assertNotIn("CidrIpv6", allowed[0])

    def test_proxy_role_cannot_archive_queue_or_modify_authority(self):
        role = self.resources["SyncRole"]["Properties"]
        statements = [item for policy in role["Policies"] for item in policy["PolicyDocument"]["Statement"]]
        actions = {action for item in statements for action in item["Action"]}
        self.assertFalse(any(action.startswith(("s3:", "sqs:", "lambda:")) for action in actions))
        self.assertEqual({action for action in actions if action.startswith("dynamodb:")}, {"dynamodb:GetItem"})
        key_reads = next(item for item in statements if "dynamodb:GetItem" in item["Action"])
        self.assertEqual(set(key_reads["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"]),
                         {"SPACE#*", "KEYHASH#*", "WRITER#PRIMARY"})

    def test_both_public_routes_require_authorizer_and_have_bounded_integration(self):
        for name in ["SyncWriteRoute", "SyncStatusRoute"]:
            route = self.resources[name]["Properties"]
            self.assertEqual(route["AuthorizationType"], "CUSTOM")
            self.assertIn("AuthorizerId", route)
        self.assertEqual(self.resources["SyncIntegration"]["Properties"]["TimeoutInMillis"], 30000)
        self.assertEqual(self.resources["Sync"]["Properties"]["Timeout"], 28)
        self.assertEqual(self.template["Parameters"]["SyncEnabled"]["Default"], "false")


if __name__ == "__main__":
    unittest.main()
