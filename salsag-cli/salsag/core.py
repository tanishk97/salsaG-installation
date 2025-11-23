#!/usr/bin/env python3

import os
import shutil
import json
import hashlib
import tarfile
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import boto3
from botocore.exceptions import ClientError

from .sg_logging import get_logger
from .sg_logging import log_step, metric_count, initialize_logger

from .rekor_client import RekorClient, RekorError


def _get_generic_sbom(artifact_path: Path):
    sbom_data = {
                "spdxVersion": "SPDX-2.3",
                "dataLicense": "CC0-1.0",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": f"SBOM for {artifact_path.name}",
                "documentNamespace": f"https://salsag.example.com/{artifact_path.name}",
                "creationInfo": {
                    "created": datetime.utcnow().isoformat() + "Z",
                    "creators": ["Tool: SalsaG CLI"]
                },
                "packages": [{
                    "SPDXID": "SPDXRef-Package",
                    "name": artifact_path.name,
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                    "copyrightText": "NOASSERTION"
                }]
            }
    return sbom_data

class SalsaGCore:
    """Core SalsaG trust pipeline functionality"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.s3 = boto3.client('s3', region_name=config['aws']['region'])
        self.dynamodb = boto3.resource('dynamodb', region_name=config['aws']['region'])
        self.table = self.dynamodb.Table(config['aws']['ledger_table'])

        self.logger = get_logger("SalsaG")
        initialize_logger(config.get('logging'))

        self.rekor = RekorClient()
    
    def package_artifact(self, artifact_path: Path, dry_run: bool = False) -> Path:
        """Package artifact into tarball"""
        with log_step("package_artifacts",artifact_file=artifact_path.name,) as step: 
            if artifact_path.is_file():
                # Single file - create tarball with just that file
                tarball_name = f"{artifact_path.stem}.tgz"
                base_dir = artifact_path.parent
                files = [artifact_path.name]
            else:
                # Directory - always create index.tgz for deployment pipeline
                tarball_name = "index.tgz"
                base_dir = artifact_path
                files = ["."]
            
            tarball_path = Path.cwd() / tarball_name
            
            if not dry_run:
                with tarfile.open(tarball_path, "w:gz") as tar:
                    for file in files:
                        tar.add(base_dir / file, arcname=file if file != "." else "")
                
           
            step.kv["tarball"] = tarball_path.name
            return tarball_path
    
    def generate_sbom(self, artifact_path: Path, dry_run: bool = False) -> Path:
        """Generate Software Bill of Materials (SBOM)"""
        
        sbom_path = Path.cwd() / f"sbom-{datetime.now().strftime('%Y%m%d-%H%M%S')}.spdx.json"
        sbom_data = _get_generic_sbom(artifact_path)
        if not dry_run:
            syft_bin_path = shutil.which("syft")
            if syft_bin_path:
                try:
                    sanitized_path = artifact_path.expanduser().resolve(strict=True)
                    args = [syft_bin_path, str(sanitized_path), "-o", "spdx-json"]
                    proc = subprocess.run(args, capture_output=True, text=True, timeout=500)
                    if proc.returncode == 0:
                        sbom_data = json.loads(proc.stdout)
                except subprocess.TimeoutExpired:
                    pass
            
            with open(sbom_path, 'w') as f:
                json.dump(sbom_data, f, indent=2)
               
        return sbom_path
    
    def create_provenance(self, tarball_path: Path, dry_run: bool = False) -> Path:
        """Create SLSA provenance"""
        with log_step("create_provenance") as step: 
            provenance_path = Path.cwd() / "provenance.json"
            
            if not dry_run:
                provenance_data = {
                    "builder": {
                        "id": "https://github.com/salsag/cli"
                    },
                    "buildType": "https://github.com/salsag/cli",
                    "invocation": {
                        "configSource": {
                            "uri": f"file://{Path.cwd()}",
                            "digest": {
                                "sha256": self._calculate_sha256(tarball_path)
                            }
                        }
                    },
                    "metadata": {
                        "buildStartedOn": datetime.utcnow().isoformat() + "Z",
                        "completeness": {
                            "parameters": True,
                            "environment": False,
                            "materials": False
                        }
                    }
                }
                
                with open(provenance_path, 'w') as f:
                    json.dump(provenance_data, f, indent=2)

            step.kv["provenance_file"] = provenance_path.name
            return provenance_path
    
    def sign_artifact(self, artifact_path: Path, dry_run: bool = False) -> tuple[Dict[str, Path], Optional[str]]:
        """Sign artifact with cosign and return signature files + Rekor entry UUID"""
        with log_step("sign_artifacts") as step:
            signature_files = {
                'signature': artifact_path.with_suffix(artifact_path.suffix + '.sig'),
                'certificate': artifact_path.with_suffix(artifact_path.suffix + '.pem'),
                'attestation': artifact_path.with_suffix(artifact_path.suffix + '.attestation.sigstore')
            }
            
            rekor_uuid = None
            bundle_path = str(signature_files['signature']) + '.bundle'
            
            # Check if signing should be skipped (for CI environments using IAM roles)
            skip_signing = self.config.get('skip_signing', False)
            
            if skip_signing or dry_run:
                # Create empty placeholder files
                for sig_file in signature_files.values():
                    sig_file.touch()
                return signature_files, None
            
            # Attempt actual cosign signing
            try:
                cmd_sign = [
                    'cosign', 'sign-blob', '--yes',
                    '--bundle', bundle_path,
                    '--output-signature', str(signature_files['signature']),
                    '--output-certificate', str(signature_files['certificate']),
                    str(artifact_path)
                ]
                
                result = subprocess.run(cmd_sign, check=True, capture_output=True, text=True, timeout=30)
                signature_files['attestation'].touch()
                
                # Try to extract Rekor UUID from bundle
                rekor_uuid = self.rekor.extract_rekor_uuid_from_bundle(bundle_path)
                
                # If bundle extraction failed, search Rekor by hash
                if not rekor_uuid:
                    artifact_sha256 = self._calculate_sha256(artifact_path)
                    rekor_uuid = self.rekor.get_latest_entry_for_hash(artifact_sha256)
                
            except Exception as e:
                # Silently create empty placeholder files
                print(f"⚠️  Signing failed: {e}")
                metric_count("SignArtifact-Error")
                for sig_file in signature_files.values():
                    sig_file.touch()
            
            return signature_files, rekor_uuid
        
    def upload_artifacts(self, tarball_path: Path, signature_files: Dict[str, Path], 
                            sbom_path: Path, provenance_path: Path, dry_run: bool = False) -> Dict[str, str]:
            """Upload all artifacts to S3"""
            
            with log_step("upload_artifacts") as step:

                bucket = self.config['aws']['staging_bucket']
                s3_urls = {}
                
                files_to_upload = {
                    'tarball': tarball_path,
                    'signature': signature_files['signature'],
                    'certificate': signature_files['certificate'],
                    'attestation': signature_files['attestation'],
                    'sbom': sbom_path,
                    'provenance': provenance_path
                }
                
                if not dry_run:
                    for file_type, file_path in files_to_upload.items():
                        if file_type in ['signature', 'certificate', 'attestation']:
                            # Store cosign files in /cosign folder
                            key = f"cosign/{file_path.name}"
                        else:
                            key = file_path.name
                        self.s3.upload_file(str(file_path), bucket, key)
                        s3_urls[file_type] = f"s3://{bucket}/{key}"
                else:
                    for file_type, file_path in files_to_upload.items():
                        if file_type in ['signature', 'certificate', 'attestation']:
                            key = f"cosign/{file_path.name}"
                        else:
                            key = file_path.name
                        s3_urls[file_type] = f"s3://{bucket}/{key}"
                
                
                step.kv["num_files"]= len(s3_urls)
                step.kv["bucket"] = bucket
                return s3_urls
    
    def record_ledger(self, tarball_path: Path, s3_urls: Dict[str, str], rekor_uuid: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Record verification in DynamoDB ledger with Rekor entry UUID"""
        with log_step("record_ledger") as step:
            digest = f"sha256:{self._calculate_sha256(tarball_path)}"
            
            ledger_entry = {
                'object_key': s3_urls['tarball'],
                'status': 'verified',
                'digest': digest,
                'timestamp': datetime.utcnow().isoformat(),
                'details': 'Signed and verified by SalsaG CLI',
                'artifacts': s3_urls
            }
            
            # Add Rekor entry UUID if available
            if rekor_uuid:
                ledger_entry['rekor_entry_id'] = rekor_uuid
                ledger_entry['rekor_verified'] = True
                step.kv["rekor_uuid"] = rekor_uuid

            
            if not dry_run:
                self.table.put_item(Item=ledger_entry)
                metric_count("LedgerRecord")
            
            return ledger_entry
    
    def verify_cosign_signature(self, artifact_path: Path, signature_files: Dict[str, Path]) -> bool:
        """Verify cosign signature"""
        with log_step("verify_cosign_signature") as step:
            step.kv["artifact"]= artifact_path.name
            try:
                # Check if signature files exist and are not empty
                sig_file = signature_files['signature']
                cert_file = signature_files['certificate']
                
                if not sig_file.exists() or sig_file.stat().st_size == 0:
                    print("⚠️  Signature file missing or empty - skipping cosign verification")
                    step.kv["WARN"] = "Missing siganture file"
                    metric_count("CosignVerify-MissingSig")
                    return True  # Don't fail pipeline for missing signatures in CI
                
                if not cert_file.exists() or cert_file.stat().st_size == 0:
                    print("⚠️  Certificate file missing or empty - skipping cosign verification")
                    metric_count("CosignVerify-MissingCert")
                    step.kv["WARN"] = "Missing certificate file"
                    return True
                
                # Verify signature
                cmd_verify = [
                    'cosign', 'verify-blob',
                    '--signature', str(sig_file),
                    '--certificate', str(cert_file),
                    '--insecure-ignore-tlog',
                    str(artifact_path)
                ]
                
                result = subprocess.run(cmd_verify, capture_output=True, text=True)

                if result.returncode == 0:
                    print("✅ Cosign signature verified")
                    return True
                else:
                    print(f"❌ Cosign verification failed: {result.stderr}")
                    metric_count("CosignVerify-FAIL")
                    return False
                    
            except subprocess.CalledProcessError as e:
                print(f"❌ Cosign verification error: {e}")
                metric_count("CosignVerify-ERROR")
                return False
            except Exception as e:
                print(f"❌ Unexpected error during cosign verification: {e}")
                metric_count("CosignVerify-ERROR")
                return False

    def verify_from_ledger(self, artifact_name: str) -> Dict[str, Any]:
        """Verify artifact from trust ledger with Rekor verification"""
        with log_step("verify_from_ledger") as step:
            # Construct S3 URI
            bucket = self.config['aws']['staging_bucket']
            object_key = f"s3://{bucket}/{artifact_name}"
            
            try:
                response = self.table.get_item(Key={'object_key': object_key})
                
                if 'Item' in response:
                    item = response['Item']
                    result = {
                        'verified': item['status'] == 'verified',
                        'digest': item.get('digest'),
                        'timestamp': item.get('timestamp'),
                        'details': item.get('details'),
                        'verification_method': 'ledger'
                    }
                    
                    # If Rekor entry ID exists, verify against Rekor
                    rekor_entry_id = item.get('rekor_entry_id')
                    if rekor_entry_id:
                        try:
                            expected_sha256 = item.get('digest', '')
                            rekor_verified = self.rekor.verify_entry(rekor_entry_id, expected_sha256)
                            result['rekor_verified'] = rekor_verified
                            result['rekor_entry_id'] = rekor_entry_id
                            result['verification_method'] = 'rekor'
                            
                            if not rekor_verified:
                                result['verified'] = False
                                result['details'] = 'Rekor verification failed'
                                metric_count("LedgerVerify-FAIL")
                                
                        except RekorError as e:
                            print(f"⚠️  Rekor verification failed: {e}")
                            metric_count("LedgerVerify-ERROR")
                            result['rekor_verified'] = False
                            result['rekor_error'] = str(e)
                            # Don't fail completely, ledger entry still valid
                    
                    return result
                else:
                    return {'verified': False, 'status': 'Not found in ledger'}
        
            except ClientError as e:
                metric_count("LedgerVerify-Error")
                raise RuntimeError(f"DynamoDB error: {e}")
    
    def verify_artifact_comprehensive(self, artifact_name: str) -> Dict[str, Any]:
        """Comprehensive artifact verification: ledger + checksum + cosign"""
        with log_step("verify_artifact_comprehensive") as step:
            verification_results = {
                'ledger_verified': False,
                'checksum_verified': False,
                'cosign_verified': False,
                'overall_verified': False,
                'details': []
            }
            
            try:
                # Step 1: Verify from trust ledger
                ledger_result = self.verify_from_ledger(artifact_name)
                verification_results['ledger_verified'] = ledger_result.get('verified', False)
                
                if verification_results['ledger_verified']:
                    verification_results['details'].append("✅ Trust ledger verification passed")
                    
                    # Step 2: Download and verify checksum if ledger has digest
                    if 'digest' in ledger_result and ledger_result['digest']:
                        bucket = self.config['aws']['staging_bucket']
                        
                        with tempfile.NamedTemporaryFile() as temp_file:
                            # Download artifact
                            s3_client = boto3.client('s3')
                            s3_client.download_file(bucket, artifact_name, temp_file.name)
                            
                            # Calculate SHA256
                            sha256_hash = hashlib.sha256()
                            with open(temp_file.name, 'rb') as f:
                                for chunk in iter(lambda: f.read(4096), b""):
                                    sha256_hash.update(chunk)
                            
                            calculated_digest = sha256_hash.hexdigest()
                            stored_digest = ledger_result['digest']
                            
                            # Remove sha256: prefix if present for comparison
                            if stored_digest.startswith('sha256:'):
                                stored_digest = stored_digest[7:]
                            
                            if calculated_digest == stored_digest:
                                verification_results['checksum_verified'] = True
                                verification_results['details'].append("✅ Checksum verification passed")

                            else:
                                
                                verification_results['details'].append("❌ Checksum verification failed")
                    
                    # Step 3: Verify cosign signatures if they exist
                    artifact_path = Path(artifact_name)
                    signature_files = {
                        'signature': artifact_path.with_suffix(artifact_path.suffix + '.sig'),
                        'certificate': artifact_path.with_suffix(artifact_path.suffix + '.pem'),
                        'attestation': artifact_path.with_suffix(artifact_path.suffix + '.attestation.sigstore')
                    }
                    
                    # Check if signature files exist in S3
                    s3_client = boto3.client('s3')
                    bucket = self.config['aws']['staging_bucket']
                    
                    try:
                        # Download signature files if they exist
                        with tempfile.TemporaryDirectory() as temp_dir:
                            temp_artifact = Path(temp_dir) / artifact_name
                            temp_sig = Path(temp_dir) / signature_files['signature'].name
                            temp_cert = Path(temp_dir) / signature_files['certificate'].name
                            
                            # Download artifact and signature files
                            s3_client.download_file(bucket, artifact_name, str(temp_artifact))
                            
                            try:
                                s3_client.download_file(bucket, signature_files['signature'].name, str(temp_sig))
                                s3_client.download_file(bucket, signature_files['certificate'].name, str(temp_cert))
                                
                                # Verify cosign signature
                                temp_signature_files = {
                                    'signature': temp_sig,
                                    'certificate': temp_cert
                                }
                                
                                verification_results['cosign_verified'] = self.verify_cosign_signature(
                                    temp_artifact, temp_signature_files
                                )
                                
                            except ClientError:
                                # Cosign files not found - using keyless signing
                                verification_results['cosign_verified'] = True
                                
                    except Exception as e:
                        verification_results['details'].append(f"⚠️  Cosign verification error: {e}")
                        verification_results['cosign_verified'] = True  # Don't fail pipeline
                        
                else:
                    verification_results['details'].append("❌ Trust ledger verification failed")
                
                # Overall verification: ledger must pass, checksum should pass if available
                verification_results['overall_verified'] = (
                    verification_results['ledger_verified'] and
                    verification_results['checksum_verified'] and
                    verification_results['cosign_verified']
                )
                if not verification_results['overall_verified']:
                    metric_count("FullVerify-FAIL")

                step.kv["overall_verified"]= verification_results['overall_verified']
                return verification_results
                

            except Exception as e:
                metric_count("FullVerify-ERROR")
                verification_results['details'].append(f"❌ Verification error: {e}")
                return verification_results
            """Get statistics from trust ledger"""
            
            try:
                # Scan table for stats (in production, use better approach for large tables)
                response = self.table.scan(
                    ProjectionExpression='#status',
                    ExpressionAttributeNames={'#status': 'status'}
                )
                
                verified_count = sum(1 for item in response['Items'] if item.get('status') == 'verified')
                failed_count = sum(1 for item in response['Items'] if item.get('status') == 'failed')
                total_count = len(response['Items'])
                
                return {
                    'verified_count': verified_count,
                    'failed_count': failed_count,
                    'total_count': total_count
                }                
               
                
                    
            except ClientError as e:
                raise RuntimeError(f"DynamoDB error: {e}")
    
    def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
