# SalsaGate Installation

Supply chain security for your CI/CD pipeline using Sigstore keyless signing and Rekor transparency logs.

## What is SalsaGate?

SalsaGate provides cryptographic verification of software artifacts to ensure only signed, untampered code reaches production:

- **Keyless Signing**: Uses Sigstore OIDC identity (no keys to manage)
- **Tamper Detection**: SHA256 checksum validation blocks modified artifacts
- **Public Transparency**: All signatures logged to Rekor for public audit
- **Zero-Trust Deployment**: Artifacts blocked unless verified in trust ledger

## Quick Install (5 minutes)

### Prerequisites

- AWS CLI configured with appropriate permissions
- GitHub repository
- AWS resources created (see [AWS Setup](#aws-setup))

### One-Command Install

```bash
curl -sSL https://raw.githubusercontent.com/tanishk97/salsaG-installation/main/install.sh | bash -s -- \
  --staging-bucket YOUR_STAGING_BUCKET \
  --website-bucket YOUR_WEBSITE_BUCKET \
  --ledger-table YOUR_DYNAMODB_TABLE \
  --signer-project YOUR_CODEBUILD_SIGNER \
  --region us-east-1
```

Or clone and run locally:

```bash
git clone https://github.com/tanishk97/salsaG-installation.git
cd salsaG-installation
./install.sh --interactive
```

## Manual Installation

### Step 1: Copy Template Files

```bash
# From your project root
curl -sSL https://raw.githubusercontent.com/tanishk97/salsaG-installation/main/templates/salsag.yml -o salsag.yml
curl -sSL https://raw.githubusercontent.com/tanishk97/salsaG-installation/main/templates/buildspec.yml -o buildspec.yml
mkdir -p .github/workflows
curl -sSL https://raw.githubusercontent.com/tanishk97/salsaG-installation/main/templates/.github/workflows/salsagate-pipeline.yml -o .github/workflows/salsagate-pipeline.yml
```

### Step 2: Update Configuration

Edit `salsag.yml` with your AWS resource names:

```yaml
aws:
  region: us-east-1
  staging_bucket: YOUR_STAGING_BUCKET      # S3 bucket for artifacts
  ledger_table: YOUR_DYNAMODB_TABLE        # DynamoDB table name
```

### Step 3: Update Workflow

Edit `.github/workflows/salsagate-pipeline.yml`:

- Update `STAGING_BUCKET` and `WEBSITE_BUCKET`
- Update CodeBuild project name for signer
- Adjust build steps for your application

### Step 4: Install SalsaG CLI (for local testing)

```bash
pip install git+https://github.com/tanishk97/salsaG-installation.git#subdirectory=salsag-cli
```

## AWS Setup

### Required Resources

| Resource | Purpose |
|----------|---------|
| S3 Staging Bucket | Stores signed artifacts |
| S3 Website Bucket | Production deployment target |
| DynamoDB Table | Trust ledger (verification records) |
| CodeBuild Signer | Keyless signing service |
| CodeBuild Deploy | Verification + deployment |
| CodePipeline | Orchestration (optional) |

### Create Resources

```bash
# S3 Buckets
aws s3 mb s3://your-staging-bucket --region us-east-1
aws s3 mb s3://your-website-bucket --region us-east-1

# DynamoDB Trust Ledger
aws dynamodb create-table \
  --table-name trust-ledger \
  --attribute-definitions AttributeName=object_key,AttributeType=S \
  --key-schema AttributeName=object_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### CodeBuild Signer Setup

Create a CodeBuild project named `salsag-artifact-signer` with:
- **Environment**: Amazon Linux 2, Standard runtime
- **Buildspec**: Use `trust-service/buildspec-signer-keyless.yml` from this repo
- **Environment Variables**: `BUCKET` (your staging bucket name)
- **IAM Role**: Needs S3 read/write, DynamoDB write permissions

## How It Works

```
Developer Push --> GitHub Actions --> Build --> Upload to S3
                                                    |
                                                    v
                                           CodeBuild Signer
                                         (Sigstore keyless sign)
                                                    |
                                                    v
                                          Record in DynamoDB
                                                    |
                                                    v
                                          CodePipeline Deploy
                                                    |
                                                    v
                                              SalsaG Verify
                                        (Check ledger + checksum)
                                                    |
                                                    v
                                      [PASS] Deploy  OR  [FAIL] Block
```

## Verification Commands

```bash
# Verify an artifact locally
salsaG verify --artifact index.tgz --config salsag.yml

# Check trust ledger status
salsaG status --config salsag.yml

# Query ledger directly
aws dynamodb scan --table-name trust-ledger
```

## Monitoring (Optional)

The pipeline emits CloudWatch metrics under the `SalsaGate` namespace:

- `FullVerify-FAIL` - Verification failed (tampering detected)
- `LedgerVerify-FAIL` - Trust ledger check failed
- `LedgerRecord` - New artifact recorded

Create an alarm:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "SalsaGate-VerificationFailure" \
  --namespace "SalsaGate" \
  --metric-name "FullVerify-FAIL" \
  --dimensions Name=service.name,Value=salsagate-cli Name=deployment.environment,Value=dev \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --treat-missing-data notBreaching \
  --alarm-actions YOUR_SNS_TOPIC_ARN
```

## File Structure After Installation

```
your-repo/
├── .github/workflows/
│   └── salsagate-pipeline.yml   # CI/CD with trust pipeline
├── buildspec.yml                 # Deploy verification
├── salsag.yml                    # SalsaGate configuration
└── ... (your application files)
```

## MCP Server (AI-Assisted Installation)

Install and manage SalsaGate using AI assistants like Claude with the included MCP server.

### Setup for Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "salsag-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/tanishk97/salsaG-installation#subdirectory=salsag-mcp", "salsag-mcp"]
    }
  }
}
```

### Available Commands

Once configured, ask Claude:

- "Check if SalsaGate is installed in my project"
- "Install SalsaGate with staging bucket X and website bucket Y"
- "Verify my SalsaGate configuration"
- "Show SalsaGate trust ledger status"

See [salsag-mcp/README.md](salsag-mcp/README.md) for full documentation.

## Troubleshooting

### "Artifact not found in ledger"
- Signing service didn't complete - check CodeBuild signer logs

### "Checksum verification failed"
- Artifact was modified after signing - this is tampering detection working correctly

### "Rekor verification failed"
- Network issue reaching rekor.sigstore.dev - falls back to ledger-only verification

## License

MIT License - UC Berkeley MICS Capstone Project

## Links

- [Main Project Repository](https://github.com/tanishk97/MICS295Capstone)
- [Sigstore](https://sigstore.dev)
- [Rekor Transparency Log](https://rekor.sigstore.dev)
