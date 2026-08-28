# 0003 — Pinned to MCP 1.x for agent-framework compatibility

## Context
The MCP SDK released 2.x, renaming FastMCP to MCPServer. The server was
migrated to 2.x. Installing agent-framework then silently downgraded mcp to
1.29.1, because agent-framework requires mcp<2. The test suite caught it
immediately.

## Decision
Stay on mcp 1.x and the FastMCP API until agent-framework supports 2.x.

## Rationale
The agent runtime is the harder dependency to replace. A tool server API
rename is a two-line change; swapping the agent framework is not.

## Consequences
- The tool server is on a superseded MCP major version.
- Revisit when agent-framework relaxes the constraint.
- The unit tests are what made this a five-minute problem rather than a
  confusing runtime failure later.