# SalsaG CLI - Trust Pipeline Tool

🔒 **Portable cryptographic signing and verification for supply chain security**

## Installation

```bash
# Install from source
cd salsag-cli
pip install -e .

# Verify installation
salsaG --version
```

## Quick Start

### 1. Initialize Configuration
```bash
salsaG init
# Follow prompts to configure AWS settings
```

### 2. Sign and Attest Artifacts
```bash
# Sign a directory
salsaG start --artifact ./dist

# Sign a single file
salsaG start --artifact ./app.zip

# Dry run (show what would happen)
salsaG start --artifact ./dist --dry-run
```

### 3. Verify Artifacts
```bash
# Verify from trust ledger
salsaG verify --artifact site-abc123.tgz

# Check ledger status
salsaG status
```

## Commands

### `salsaG start`
**Sign, attest, and store artifact in trust pipeline**

- 📦 Packages artifact into tarball
- 📋 Generates SBOM (Software Bill of Materials)
- 📜 Creates SLSA provenance
- 🔐 Signs with cosign (keyless)
- ☁️ Uploads to S3 staging bucket
- 📊 Records in DynamoDB trust ledger

### `salsaG verify`
**Verify artifact from trust ledger**

- 🏦 Queries DynamoDB for verification status
- 📋 Shows digest and timestamp
- ✅/❌ Returns verification result

### `salsaG status`
**Show trust ledger statistics**

- 📊 Total artifacts processed
- ✅ Verified count
- ❌ Failed count

### `salsaG init`
**Initialize configuration file**

- 🔧 Interactive setup
- 📝 Creates `salsag.yml` config file

## Configuration

Create `salsag.yml` in your project:

```yaml
# SalsaG Trust Pipeline Configuration
aws:
  region: us-east-1
  staging_bucket: my-staging-bucket
  ledger_table: trust-ledger

signing:
  oidc_issuer: "https://token.actions.githubusercontent.com"
  identity_regexp: "https://github.com/.+"

artifacts:
  compression: "gzip"
  include_sbom: true
  include_provenance: true
```

## Prerequisites

### Required Tools
- **cosign** - Install from [sigstore.dev](https://docs.sigstore.dev/cosign/installation/)
- **AWS CLI** - Configured with appropriate permissions

### AWS Permissions
Your AWS credentials need:
- S3: `PutObject`, `GetObject` on staging bucket
- DynamoDB: `PutItem`, `GetItem`, `Scan` on ledger table

## Examples

### Basic Usage
```bash
# Initialize config
salsaG init

# Sign your build artifacts
salsaG start --artifact ./build

# Verify later
salsaG verify --artifact build.tgz
```

### CI/CD Integration
```bash
# In your CI/CD pipeline
npm run build
salsaG start --artifact ./dist --config ./ci/salsag.yml

# Verify in deployment stage
salsaG verify --artifact dist.tgz --config ./ci/salsag.yml
```

### Custom Configuration
```bash
# Override config values
salsaG start \
  --artifact ./app \
  --bucket my-custom-bucket \
  --table my-custom-table
```

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Local CLI     │    │   AWS S3         │    │   DynamoDB      │
│                 │    │   (Staging)      │    │   (Ledger)      │
├─────────────────┤    ├──────────────────┤    ├─────────────────┤
│ • Package       │───▶│ • Signed tarballs│    │ • Verification  │
│ • Generate SBOM │    │ • Signatures     │    │   status        │
│ • Create SLSA   │    │ • Certificates   │    │ • SHA digests   │
│ • Sign (cosign) │    │ • Attestations   │    │ • Timestamps    │
│ • Upload        │    │ • SBOMs          │    │ • Audit trail   │
│ • Record        │───▶│ • Provenance     │───▶│                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Benefits

✅ **Portable** - Works on any machine with Python + cosign  
✅ **Simple** - Single command for complete trust pipeline  
✅ **Configurable** - YAML-based configuration  
✅ **Integrated** - Uses existing AWS infrastructure  
✅ **Auditable** - Complete verification history  
✅ **Secure** - Keyless signing with GitHub OIDC  

## Troubleshooting

### Common Issues

**cosign not found**
```bash
# Install cosign
curl -O -L "https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64"
sudo mv cosign-linux-amd64 /usr/local/bin/cosign
sudo chmod +x /usr/local/bin/cosign
```

**AWS permissions error**
```bash
# Check AWS configuration
aws sts get-caller-identity
aws s3 ls s3://your-staging-bucket
```

**DynamoDB table not found**
```bash
# Create table
aws dynamodb create-table \
  --table-name trust-ledger \
  --attribute-definitions AttributeName=object_key,AttributeType=S \
  --key-schema AttributeName=object_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```
