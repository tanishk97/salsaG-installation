#!/usr/bin/env python3

import click
import os
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .core import SalsaGCore
from .config import load_config

console = Console()

@click.group()
@click.version_option(version="1.0.0")
def main():
    """🔒 SalsaG Trust Pipeline CLI
    
    Cryptographic signing and verification for supply chain security.
    """
    pass

@main.command()
@click.option('--artifact', '-a', required=True, help='Path to artifact directory or file')
@click.option('--config', '-c', default='salsag.yml', help='Configuration file path')
@click.option('--bucket', '-b', help='S3 staging bucket (overrides config)')
@click.option('--table', '-t', help='DynamoDB table (overrides config)')
@click.option('--dry-run', is_flag=True, help='Show what would be done without executing')
def start(artifact, config, bucket, table, dry_run):
    """🚀 Start trust pipeline: sign, attest, and store artifact"""
    
    console.print(Panel.fit("🔒 SalsaG Trust Pipeline", style="bold blue"))
    
    # Load configuration
    try:
        cfg = load_config(config)
        if bucket:
            cfg['aws']['staging_bucket'] = bucket
        if table:
            cfg['aws']['ledger_table'] = table
    except Exception as e:
        console.print(f"❌ Config error: {e}", style="red")
        sys.exit(1)
    
    # Validate artifact path
    artifact_path = Path(artifact)
    if not artifact_path.exists():
        console.print(f"❌ Artifact not found: {artifact}", style="red")
        sys.exit(1)
    
    if dry_run:
        console.print("🔍 DRY RUN - No changes will be made", style="yellow")
    
    # Initialize SalsaG core
    core = SalsaGCore(cfg)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        
        try:
            # Step 1: Package artifact
            task1 = progress.add_task("📦 Packaging artifact...", total=None)
            tarball_path = core.package_artifact(artifact_path, dry_run)
            progress.update(task1, description="✅ Artifact packaged")
            
            # Step 2: Generate SBOM
            task2 = progress.add_task("📋 Generating SBOM...", total=None)
            sbom_path = core.generate_sbom(artifact_path, dry_run)
            progress.update(task2, description="✅ SBOM generated")
            
            # Step 3: Create provenance
            task3 = progress.add_task("📜 Creating SLSA provenance...", total=None)
            provenance_path = core.create_provenance(tarball_path, dry_run)
            progress.update(task3, description="✅ Provenance created")
            
            # Step 4: Sign with cosign
            task4 = progress.add_task("🔐 Signing with cosign...", total=None)
            signature_files, rekor_uuid = core.sign_artifact(tarball_path, dry_run)
            progress.update(task4, description="✅ Artifact signed")
            
            # Step 5: Upload to S3
            task5 = progress.add_task("☁️ Uploading to S3...", total=None)
            s3_urls = core.upload_artifacts(tarball_path, signature_files, sbom_path, provenance_path, dry_run)
            progress.update(task5, description="✅ Uploaded to S3")
            
            # Step 6: Record in ledger
            task6 = progress.add_task("📊 Recording in ledger...", total=None)
            ledger_entry = core.record_ledger(tarball_path, s3_urls, rekor_uuid, dry_run)
            progress.update(task6, description="✅ Recorded in ledger")
            
        except Exception as e:
            console.print(f"\n❌ Pipeline failed: {e}", style="red")
            sys.exit(1)
    
    console.print("\n🎉 Trust pipeline completed successfully!", style="green bold")
    if not dry_run:
        console.print(f"📋 Artifact: {tarball_path.name}")
        console.print(f"🏦 Ledger: {cfg['aws']['ledger_table']}")

@main.command()
@click.option('--artifact', '-a', required=True, help='Artifact name to verify')
@click.option('--config', '-c', default='salsag.yml', help='Configuration file path')
def verify(artifact, config):
    """🔍 Verify artifact from trust ledger"""
    
    console.print(Panel.fit("🔍 SalsaG Verification", style="bold green"))
    
    try:
        cfg = load_config(config)
        core = SalsaGCore(cfg)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("🔍 Verifying artifact integrity...", total=None)
            result = core.verify_artifact_comprehensive(artifact)
            progress.remove_task(task)
        
        # Show all verification details
        for detail in result['details']:
            console.print(f"  {detail}")
        
        if result['overall_verified']:
            console.print(f"✅ Artifact VERIFIED", style="green bold")
        else:
            console.print(f"❌ Artifact VERIFICATION FAILED", style="red bold")
            sys.exit(1)  # Exit with error code when verification fails
            
    except Exception as e:
        console.print(f"❌ Verification failed: {e}", style="red")
        sys.exit(1)

@main.command()
@click.option('--config', '-c', default='salsag.yml', help='Configuration file path')
def status(config):
    """📊 Show trust ledger status"""
    
    console.print(Panel.fit("📊 SalsaG Status", style="bold cyan"))
    
    try:
        cfg = load_config(config)
        core = SalsaGCore(cfg)
        
        stats = core.get_ledger_stats()
        
        console.print(f"🏦 Ledger Table: {cfg['aws']['ledger_table']}")
        console.print(f"✅ Verified Artifacts: {stats['verified_count']}")
        console.print(f"❌ Failed Artifacts: {stats['failed_count']}")
        console.print(f"📊 Total Records: {stats['total_count']}")
        
    except Exception as e:
        console.print(f"❌ Status check failed: {e}", style="red")
        sys.exit(1)

@main.command()
def init():
    """🔧 Initialize SalsaG configuration"""
    
    console.print(Panel.fit("🔧 SalsaG Configuration", style="bold yellow"))
    
    config_path = Path("salsag.yml")
    if config_path.exists():
        if not click.confirm("Configuration file exists. Overwrite?"):
            return
    
    # Interactive configuration
    aws_region = click.prompt("AWS Region", default="us-east-1")
    staging_bucket = click.prompt("S3 Staging Bucket")
    ledger_table = click.prompt("DynamoDB Ledger Table", default="trust-ledger")
    
    config_content = f"""# SalsaG Trust Pipeline Configuration
aws:
  region: {aws_region}
  staging_bucket: {staging_bucket}
  ledger_table: {ledger_table}

signing:
  oidc_issuer: "https://token.actions.githubusercontent.com"
  identity_regexp: "https://github.com/.+"

artifacts:
  compression: "gzip"
  include_sbom: true
  include_provenance: true
"""
    
    config_path.write_text(config_content)
    console.print(f"✅ Configuration saved to {config_path}", style="green")

if __name__ == "__main__":
    main()
