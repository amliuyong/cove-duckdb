"""Account-level backup vault, retained independently of every environment's lifecycle.

One versioned, encrypted, owner-enforced bucket that no environment teardown
empties: environment deletion never reaches it and the bucket itself is
retained when this stack is deleted. Objects are written once (conditional
creation) and read by exact version; access is TLS-only.
"""

STACK = "colvenna-isle-backups"


def template(source_commit):
    tags = [{"Key": "Project", "Value": "colvenna-isle"}, {"Key": "Environment", "Value": "backups"},
            {"Key": "SourceCommit", "Value": source_commit}]
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Colvenna Isle backup vault (retained; outside environment lifecycles)",
        "Resources": {
            "Vault": {"Type": "AWS::S3::Bucket", "DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain",
                      "Properties": {
                          "VersioningConfiguration": {"Status": "Enabled"},
                          "BucketEncryption": {"ServerSideEncryptionConfiguration": [
                              {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
                          "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
                          "PublicAccessBlockConfiguration": {
                              "BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True,
                              "RestrictPublicBuckets": True},
                          "Tags": tags}},
            "VaultPolicy": {"Type": "AWS::S3::BucketPolicy", "Properties": {
                "Bucket": {"Ref": "Vault"},
                "PolicyDocument": {"Version": "2012-10-17", "Statement": [{
                    "Sid": "TlsOnly", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
                    "Resource": [{"Fn::GetAtt": ["Vault", "Arn"]}, {"Fn::Sub": "${Vault.Arn}/*"}],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]}}},
        },
        "Outputs": {"Bucket": {"Value": {"Ref": "Vault"}}, "SourceCommit": {"Value": source_commit}},
    }
