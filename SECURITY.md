# Security

Security fixes are made for the latest release (currently 1.0.0). The deployment security model is summarized in the [installation guide](docs/installation.md#13-安全要点).

Please do not put API Keys, cloud credentials, private data, or exploit details in ordinary issues or pull requests.

For a confidential report, use GitHub's **Report a vulnerability** feature when it is enabled. If it is unavailable, contact the repository owner through an existing private channel before sharing sensitive details.

The documented authentication model uses opaque Bearer API Keys with server-side hashes, expiry, revocation, space-bound scopes, and separate management permissions. SQL execution requires server-side authorization and runtime isolation; a read-only database attachment alone is not a complete security boundary.

Custom Python is published by trusted, authorized space members with `pipeline:manage`. Approved execution profiles restrict input datasets, staging access and resources; they do not grant native warehouse writes. A shared pipeline role is not an IAM sandbox for each attempt. Input/output hashes, immutable object versions and authoritative publication fencing remain necessary even when compute times out or runs more than once.
