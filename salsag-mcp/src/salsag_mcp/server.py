"""
SalsaGate MCP Server

Provides tools to install and verify SalsaGate supply chain security in repositories.
"""

import os
import json
import subprocess
import shutil
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Initialize MCP server
server = Server("salsag-mcp")

# Installation repo URL
INSTALL_REPO = "https://github.com/tanishk97/salsaG-installation"
INSTALL_REPO_RAW = "https://raw.githubusercontent.com/tanishk97/salsaG-installation/main"


def check_file_exists(directory: str, filename: str) -> bool:
    """Check if a file exists in the given directory."""
    return (Path(directory) / filename).exists()


def read_yaml_config(filepath: str) -> dict:
    """Read and parse a YAML configuration file."""
    try:
        import yaml
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        return {"error": str(e)}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available SalsaGate MCP tools."""
    return [
        Tool(
            name="salsag_check",
            description="Check if SalsaGate is installed in a directory. Returns installation status and configuration details.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Path to the directory to check (defaults to current directory)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="salsag_install",
            description="Install SalsaGate in a directory. Creates configuration files and sets up the trust pipeline.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Path to the directory to install SalsaGate (defaults to current directory)"
                    },
                    "staging_bucket": {
                        "type": "string",
                        "description": "S3 bucket name for staging artifacts"
                    },
                    "website_bucket": {
                        "type": "string",
                        "description": "S3 bucket name for production website"
                    },
                    "ledger_table": {
                        "type": "string",
                        "description": "DynamoDB table name for trust ledger (default: trust-ledger)"
                    },
                    "region": {
                        "type": "string",
                        "description": "AWS region (default: us-east-1)"
                    }
                },
                "required": ["staging_bucket", "website_bucket"]
            }
        ),
        Tool(
            name="salsag_verify_config",
            description="Verify that SalsaGate configuration is valid and complete.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Path to the directory to verify (defaults to current directory)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="salsag_status",
            description="Get the status of SalsaGate including trust ledger entries and recent verifications.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Path to the directory with salsag.yml (defaults to current directory)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="salsag_uninstall",
            description="Remove SalsaGate configuration files from a directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Path to the directory to uninstall from (defaults to current directory)"
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    if name == "salsag_check":
        return await handle_check(arguments)
    elif name == "salsag_install":
        return await handle_install(arguments)
    elif name == "salsag_verify_config":
        return await handle_verify_config(arguments)
    elif name == "salsag_status":
        return await handle_status(arguments)
    elif name == "salsag_uninstall":
        return await handle_uninstall(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def handle_check(arguments: dict[str, Any]) -> list[TextContent]:
    """Check if SalsaGate is installed."""
    directory = arguments.get("directory", os.getcwd())
    directory = os.path.expanduser(directory)

    result = {
        "directory": directory,
        "installed": False,
        "files": {
            "salsag.yml": False,
            "buildspec.yml": False,
            "workflow": False
        },
        "config": None,
        "issues": []
    }

    # Check for salsag.yml
    salsag_yml = Path(directory) / "salsag.yml"
    if salsag_yml.exists():
        result["files"]["salsag.yml"] = True
        result["config"] = read_yaml_config(str(salsag_yml))
    else:
        result["issues"].append("salsag.yml not found")

    # Check for buildspec.yml
    buildspec = Path(directory) / "buildspec.yml"
    if buildspec.exists():
        result["files"]["buildspec.yml"] = True
        # Check if it contains SalsaG verification
        with open(buildspec, 'r') as f:
            content = f.read()
            if "salsaG verify" not in content and "salsag" not in content.lower():
                result["issues"].append("buildspec.yml exists but doesn't contain SalsaG verification")
    else:
        result["issues"].append("buildspec.yml not found")

    # Check for GitHub workflow
    workflow_dir = Path(directory) / ".github" / "workflows"
    if workflow_dir.exists():
        workflows = list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml"))
        for wf in workflows:
            with open(wf, 'r') as f:
                if "salsag" in f.read().lower():
                    result["files"]["workflow"] = True
                    break
        if not result["files"]["workflow"]:
            result["issues"].append("No GitHub workflow with SalsaG integration found")
    else:
        result["issues"].append(".github/workflows directory not found")

    # Determine if installed
    result["installed"] = all(result["files"].values())

    # Format output
    status = "INSTALLED" if result["installed"] else "NOT INSTALLED"
    output = f"""SalsaGate Status: {status}

Directory: {directory}

Files:
  - salsag.yml: {"✓" if result["files"]["salsag.yml"] else "✗"}
  - buildspec.yml: {"✓" if result["files"]["buildspec.yml"] else "✗"}
  - GitHub Workflow: {"✓" if result["files"]["workflow"] else "✗"}
"""

    if result["config"] and "error" not in result["config"]:
        aws_config = result["config"].get("aws", {})
        output += f"""
Configuration:
  - Region: {aws_config.get("region", "not set")}
  - Staging Bucket: {aws_config.get("staging_bucket", "not set")}
  - Ledger Table: {aws_config.get("ledger_table", "not set")}
"""

    if result["issues"]:
        output += f"\nIssues:\n"
        for issue in result["issues"]:
            output += f"  - {issue}\n"

    return [TextContent(type="text", text=output)]


async def handle_install(arguments: dict[str, Any]) -> list[TextContent]:
    """Install SalsaGate in a directory."""
    directory = arguments.get("directory", os.getcwd())
    directory = os.path.expanduser(directory)
    staging_bucket = arguments.get("staging_bucket")
    website_bucket = arguments.get("website_bucket")
    ledger_table = arguments.get("ledger_table", "trust-ledger")
    region = arguments.get("region", "us-east-1")

    if not staging_bucket or not website_bucket:
        return [TextContent(type="text", text="Error: staging_bucket and website_bucket are required")]

    try:
        # Create directories
        os.makedirs(directory, exist_ok=True)
        os.makedirs(os.path.join(directory, ".github", "workflows"), exist_ok=True)

        # Create salsag.yml
        salsag_config = f"""# SalsaGate Configuration
# Generated by salsag-mcp

aws:
  region: {region}
  staging_bucket: {staging_bucket}
  ledger_table: {ledger_table}

logging:
  cloudwatch:
    level: "INFO"
    log_group: "/salsagate/deploy"
    stream_name: "verification-metrics"
    region: {region}
"""
        with open(os.path.join(directory, "salsag.yml"), 'w') as f:
            f.write(salsag_config)

        # Create buildspec.yml
        buildspec_content = f"""version: 0.2

phases:
  install:
    runtime-versions:
      python: 3.9
    commands:
      - echo "Installing SalsaG CLI..."
      - pip install git+https://github.com/tanishk97/salsaG-installation.git#subdirectory=salsag-cli
      - curl -O -L "https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-amd64"
      - sudo mv cosign-linux-amd64 /usr/local/bin/cosign
      - sudo chmod +x /usr/local/bin/cosign

  pre_build:
    commands:
      - echo "Verifying artifact..."
      - |
        if salsaG verify --artifact index.tgz --config salsag.yml; then
          echo "Verification PASSED"
        else
          echo "Verification FAILED"
          exit 1
        fi

  build:
    commands:
      - aws s3 cp s3://{staging_bucket}/index.tgz ./verified-index.tgz
      - tar -xzf verified-index.tgz
      - aws s3 sync . s3://{website_bucket}/ --exclude "*.tgz" --exclude "*.yml" --exclude ".git/*"

  post_build:
    commands:
      - echo "Deployment complete"
"""
        with open(os.path.join(directory, "buildspec.yml"), 'w') as f:
            f.write(buildspec_content)

        # Create GitHub workflow
        workflow_content = f"""name: SalsaGate Pipeline

on:
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - '**.html'
      - '**.css'
      - '**.js'

env:
  AWS_REGION: {region}
  STAGING_BUCKET: {staging_bucket}
  WEBSITE_BUCKET: {website_bucket}

jobs:
  build-sign-deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install SalsaG CLI
        run: pip install git+https://github.com/tanishk97/salsaG-installation.git#subdirectory=salsag-cli

      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{{{ secrets.AWS_ROLE_ARN }}}}
          aws-region: {region}

      - name: Build and Package
        run: |
          mkdir -p dist
          cp -r *.html dist/ 2>/dev/null || true
          cp -r *.css dist/ 2>/dev/null || true
          cp -r *.js dist/ 2>/dev/null || true
          cd dist && tar -czf ../index.tgz . && cd ..

      - name: Upload to Staging
        run: aws s3 cp index.tgz s3://{staging_bucket}/index.tgz

      - name: Invoke Signing Service
        run: |
          BUILD_ID=$(aws codebuild start-build \\
            --project-name salsag-artifact-signer \\
            --environment-variables-override name=ARTIFACT_KEY,value=index.tgz \\
            --query 'build.id' --output text)

          for i in {{1..30}}; do
            STATUS=$(aws codebuild batch-get-builds --ids $BUILD_ID --query 'builds[0].buildStatus' --output text)
            if [ "$STATUS" = "SUCCEEDED" ]; then break; fi
            if [ "$STATUS" = "FAILED" ]; then exit 1; fi
            sleep 5
          done
"""
        with open(os.path.join(directory, ".github", "workflows", "salsagate-pipeline.yml"), 'w') as f:
            f.write(workflow_content)

        output = f"""SalsaGate installed successfully!

Directory: {directory}

Files created:
  ✓ salsag.yml
  ✓ buildspec.yml
  ✓ .github/workflows/salsagate-pipeline.yml

Configuration:
  - Region: {region}
  - Staging Bucket: {staging_bucket}
  - Website Bucket: {website_bucket}
  - Ledger Table: {ledger_table}

Next steps:
1. Add AWS_ROLE_ARN to your GitHub repository secrets
2. Ensure AWS resources exist (S3 buckets, DynamoDB table, CodeBuild projects)
3. Push changes to trigger the pipeline
"""
        return [TextContent(type="text", text=output)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error installing SalsaGate: {str(e)}")]


async def handle_verify_config(arguments: dict[str, Any]) -> list[TextContent]:
    """Verify SalsaGate configuration."""
    directory = arguments.get("directory", os.getcwd())
    directory = os.path.expanduser(directory)

    issues = []
    warnings = []

    # Check salsag.yml
    salsag_yml = Path(directory) / "salsag.yml"
    if not salsag_yml.exists():
        return [TextContent(type="text", text="Error: salsag.yml not found. Run salsag_install first.")]

    config = read_yaml_config(str(salsag_yml))
    if "error" in config:
        return [TextContent(type="text", text=f"Error reading salsag.yml: {config['error']}")]

    # Validate required fields
    aws_config = config.get("aws", {})

    if not aws_config.get("staging_bucket"):
        issues.append("aws.staging_bucket is not set")
    elif aws_config.get("staging_bucket") == "YOUR_STAGING_BUCKET":
        issues.append("aws.staging_bucket still has placeholder value")

    if not aws_config.get("ledger_table"):
        warnings.append("aws.ledger_table is not set (will use default: trust-ledger)")

    if not aws_config.get("region"):
        warnings.append("aws.region is not set (will use default: us-east-1)")

    # Check logging config
    if not config.get("logging"):
        warnings.append("logging configuration not set (CloudWatch metrics will be disabled)")

    # Build output
    if issues:
        status = "INVALID"
    elif warnings:
        status = "VALID (with warnings)"
    else:
        status = "VALID"

    output = f"""Configuration Status: {status}

File: {salsag_yml}

Current Configuration:
  - Region: {aws_config.get("region", "not set")}
  - Staging Bucket: {aws_config.get("staging_bucket", "not set")}
  - Ledger Table: {aws_config.get("ledger_table", "not set")}
  - Logging: {"enabled" if config.get("logging") else "disabled"}
"""

    if issues:
        output += "\nErrors (must fix):\n"
        for issue in issues:
            output += f"  ✗ {issue}\n"

    if warnings:
        output += "\nWarnings:\n"
        for warning in warnings:
            output += f"  ! {warning}\n"

    if not issues and not warnings:
        output += "\n✓ Configuration is valid and complete"

    return [TextContent(type="text", text=output)]


async def handle_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get SalsaGate status including trust ledger."""
    directory = arguments.get("directory", os.getcwd())
    directory = os.path.expanduser(directory)

    # Check if salsag.yml exists
    salsag_yml = Path(directory) / "salsag.yml"
    if not salsag_yml.exists():
        return [TextContent(type="text", text="Error: salsag.yml not found. SalsaGate not installed.")]

    config = read_yaml_config(str(salsag_yml))
    if "error" in config:
        return [TextContent(type="text", text=f"Error reading config: {config['error']}")]

    aws_config = config.get("aws", {})
    ledger_table = aws_config.get("ledger_table", "trust-ledger")
    region = aws_config.get("region", "us-east-1")

    output = f"""SalsaGate Status

Configuration:
  - Region: {region}
  - Staging Bucket: {aws_config.get("staging_bucket", "not set")}
  - Ledger Table: {ledger_table}

"""

    # Try to query DynamoDB
    try:
        result = subprocess.run(
            ["aws", "dynamodb", "scan", "--table-name", ledger_table,
             "--region", region, "--max-items", "10"],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            items = data.get("Items", [])
            count = data.get("Count", 0)

            output += f"Trust Ledger: {count} entries\n\n"

            if items:
                output += "Recent Entries:\n"
                for item in items[:5]:
                    obj_key = item.get("object_key", {}).get("S", "unknown")
                    status = item.get("status", {}).get("S", "unknown")
                    timestamp = item.get("timestamp", {}).get("S", "unknown")
                    output += f"  - {obj_key}\n"
                    output += f"    Status: {status}, Time: {timestamp}\n"
        else:
            output += f"Trust Ledger: Unable to query\n"
            output += f"  Error: {result.stderr}\n"

    except subprocess.TimeoutExpired:
        output += "Trust Ledger: Query timed out\n"
    except FileNotFoundError:
        output += "Trust Ledger: AWS CLI not found\n"
    except Exception as e:
        output += f"Trust Ledger: Error - {str(e)}\n"

    return [TextContent(type="text", text=output)]


async def handle_uninstall(arguments: dict[str, Any]) -> list[TextContent]:
    """Remove SalsaGate files."""
    directory = arguments.get("directory", os.getcwd())
    directory = os.path.expanduser(directory)

    removed = []
    not_found = []

    # Files to remove
    files_to_remove = [
        "salsag.yml",
        "buildspec.yml",
        ".github/workflows/salsagate-pipeline.yml"
    ]

    for filepath in files_to_remove:
        full_path = Path(directory) / filepath
        if full_path.exists():
            full_path.unlink()
            removed.append(filepath)
        else:
            not_found.append(filepath)

    output = f"""SalsaGate Uninstall

Directory: {directory}

"""

    if removed:
        output += "Removed:\n"
        for f in removed:
            output += f"  ✓ {f}\n"

    if not_found:
        output += "\nNot found (skipped):\n"
        for f in not_found:
            output += f"  - {f}\n"

    if removed:
        output += "\nSalsaGate has been uninstalled."
    else:
        output += "\nNo SalsaGate files found to remove."

    return [TextContent(type="text", text=output)]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
