"""Entry point for running salsag-mcp as a module."""

import asyncio
from .server import main

if __name__ == "__main__":
    asyncio.run(main())
