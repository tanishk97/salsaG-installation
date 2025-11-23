#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name="salsag",
    version="1.0.0",
    description="SalsaG Trust Pipeline CLI - Cryptographic signing and verification for supply chain security",
    author="UC Berkeley Cyber295 Capstone",
    packages=find_packages(),
    install_requires=[
        "click>=8.0.0",
        "boto3>=1.26.0",
        "pyyaml>=6.0",
        "requests>=2.28.0",
        "cryptography>=3.4.0",
        "rich>=12.0.0",
        "anchore_syft>=1.18.1",
        "watchtower>=3.4.0",
        "python-json-logger>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "salsaG=salsag.cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8+",
    ],
)
