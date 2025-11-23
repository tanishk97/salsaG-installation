# SalsaGate MCP Server

An MCP (Model Context Protocol) server that enables AI assistants to install and manage SalsaGate supply chain security.

## Features

- **salsag_check**: Check if SalsaGate is installed in a directory
- **salsag_install**: Install SalsaGate with custom configuration
- **salsag_verify_config**: Verify configuration is valid
- **salsag_status**: Get trust ledger status and recent entries
- **salsag_uninstall**: Remove SalsaGate from a directory

## Installation

### For Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

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

Or if installed locally:

```json
{
  "mcpServers": {
    "salsag-mcp": {
      "command": "python",
      "args": ["-m", "salsag_mcp.server"],
      "cwd": "/path/to/salsag-mcp"
    }
  }
}
```

### For Claude Code

Add to your Claude Code MCP settings:

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

### Local Development

```bash
cd salsag-mcp
pip install -e .
python -m salsag_mcp.server
```

## Usage

Once configured, you can ask Claude to:

### Check Installation Status
> "Check if SalsaGate is installed in my current project"

### Install SalsaGate
> "Install SalsaGate with staging bucket 'my-staging-bucket' and website bucket 'my-website-bucket'"

### Verify Configuration
> "Verify my SalsaGate configuration is correct"

### Check Status
> "Show me the SalsaGate trust ledger status"

### Uninstall
> "Remove SalsaGate from this project"

## Tools Reference

### salsag_check

Check if SalsaGate is installed in a directory.

**Parameters:**
- `directory` (optional): Path to check (defaults to current directory)

**Returns:** Installation status, file presence, and configuration details.

### salsag_install

Install SalsaGate in a directory.

**Parameters:**
- `directory` (optional): Installation path (defaults to current directory)
- `staging_bucket` (required): S3 bucket for staging artifacts
- `website_bucket` (required): S3 bucket for production
- `ledger_table` (optional): DynamoDB table name (default: trust-ledger)
- `region` (optional): AWS region (default: us-east-1)

**Creates:**
- `salsag.yml` - Configuration file
- `buildspec.yml` - CodeBuild verification spec
- `.github/workflows/salsagate-pipeline.yml` - GitHub Actions workflow

### salsag_verify_config

Verify SalsaGate configuration is valid.

**Parameters:**
- `directory` (optional): Path to verify (defaults to current directory)

**Returns:** Validation status, errors, and warnings.

### salsag_status

Get trust ledger status and recent entries.

**Parameters:**
- `directory` (optional): Path with salsag.yml (defaults to current directory)

**Returns:** Configuration summary and recent trust ledger entries.

### salsag_uninstall

Remove SalsaGate files from a directory.

**Parameters:**
- `directory` (optional): Path to uninstall from (defaults to current directory)

**Returns:** List of removed files.

## Requirements

- Python 3.10+
- AWS CLI (for status queries)
- MCP SDK

## License

MIT License - UC Berkeley MICS Capstone Project
