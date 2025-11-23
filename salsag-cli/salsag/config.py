#!/usr/bin/env python3

import yaml
from pathlib import Path
from typing import Dict, Any

def load_config(config_path: str) -> Dict[str, Any]:
    """Load SalsaG configuration from YAML file"""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    # Validate required fields
    required_fields = [
        'aws.region',
        'aws.staging_bucket', 
        'aws.ledger_table'
    ]
    
    for field in required_fields:
        keys = field.split('.')
        value = config
        for key in keys:
            if key not in value:
                raise ValueError(f"Missing required configuration: {field}")
            value = value[key]
    
    # Set defaults
    config.setdefault('signing', {})
    config['signing'].setdefault('oidc_issuer', 'https://token.actions.githubusercontent.com')
    config['signing'].setdefault('identity_regexp', 'https://github.com/.+')
    
    config.setdefault('artifacts', {})
    config['artifacts'].setdefault('compression', 'gzip')
    config['artifacts'].setdefault('include_sbom', True)
    config['artifacts'].setdefault('include_provenance', True)
    
    return config

def get_default_config() -> Dict[str, Any]:
    """Get default configuration template"""
    
    return {
        'aws': {
            'region': 'us-east-1',
            'staging_bucket': 'your-staging-bucket',
            'ledger_table': 'trust-ledger'
        },
        'signing': {
            'oidc_issuer': 'https://token.actions.githubusercontent.com',
            'identity_regexp': 'https://github.com/.+'
        },
        'artifacts': {
            'compression': 'gzip',
            'include_sbom': True,
            'include_provenance': True
        },
        # Default is to have no remote logging.
        # Supported logging include one or multiple options of:
        #   cloudwatch -> log to cloudwatch. cloudwatch_enabled must be set to True in aws settings
        #   syslog -> log to a local or remote syslog server
        #   local -> log to a local file, imcluding   
        #'logging':{
            #'cloudwatch':{
            #    'level': 'INFO',
            #    'region': us-east-2,
            #    'log_group':'SalsaGate',
            #    'stream_name':"cli"
            #}
            #'syslog':{
            #   'level':'DEBUG',
            #   'address':'/dev/log',
            #} 
        #}

    }
