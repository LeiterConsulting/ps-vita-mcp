"""Standalone control MCP entry point, also useful for isolated qualification."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'resident'))
from bridge import configuration
from mcp.server.fastmcp import FastMCP
from control.bridge_tools import register
mcp=FastMCP('Vita Control',log_level='WARNING')
register(mcp,configuration,ROOT)
if __name__=='__main__': mcp.run()
