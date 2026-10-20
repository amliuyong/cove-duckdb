"""us-west-2 on-demand list prices used for cost observation (USD).

Retrieved 2026-10-18 from the AWS Price List API (GetProducts, us-east-1
endpoint) for regionCode us-west-2. These are list prices: free tier, savings
plans, credits, taxes and tiered discounts are not applied.
"""

RETRIEVED = "2026-10-18"
SOURCES = [
    "AWS Price List API GetProducts AWSLambda usagetype USW2-Lambda-GB-Second-ARM (Tier-1), USW2-Request-ARM",
    "AWS Price List API GetProducts AmazonECS usagetype USW2-Fargate-ARM-vCPU-Hours:perCPU, USW2-Fargate-ARM-GB-Hours",
    "AWS Price List API GetProducts AmazonS3 usagetype USW2-TimedStorage-ByteHrs (first 50 TB), "
    "USW2-Requests-Tier1, USW2-Requests-Tier2",
    "AWS Price List API GetProducts AmazonECR usagetype USW2-TimedStorage-ByteHrs",
    "AWS Price List API GetProducts CodeBuild usagetype USW2-Build-Min:ARM:g1.small (BUILD_GENERAL1_SMALL)",
]
LAMBDA_ARM_GB_SECOND = 0.0000133334
LAMBDA_ARM_REQUEST = 0.0000002
FARGATE_ARM_VCPU_HOUR = 0.03238
FARGATE_ARM_GB_HOUR = 0.00356
S3_STANDARD_GB_MONTH = 0.023
S3_PUT_REQUEST = 0.000005
S3_GET_REQUEST = 0.0000004
ECR_GB_MONTH = 0.10
CODEBUILD_ARM_SMALL_MINUTE = 0.0034
# Fargate bills per second with a one-minute minimum per task.
FARGATE_MINIMUM_SECONDS = 60
# The sole writer and query tasks: 2 vCPU / 4 GiB ARM Fargate (deployed task definitions).
SHARED_TASK_VCPU, SHARED_TASK_GB = 2, 4
MONTH_SECONDS = 30 * 86400
GIB = 1073741824


def fargate_second(vcpu, gb):
    return vcpu * FARGATE_ARM_VCPU_HOUR / 3600 + gb * FARGATE_ARM_GB_HOUR / 3600
