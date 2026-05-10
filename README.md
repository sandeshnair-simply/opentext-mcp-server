# OpenText Content Server — MCP Server

> Connect Claude AI directly to OpenText Content Server via the Model Context Protocol (MCP).  
> Built by [Sandesh Nair](https://www.linkedin.com/in/sandesh-nair) | 

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![MCP](https://img.shields.io/badge/MCP-FastMCP-purple)
![OpenText](https://img.shields.io/badge/OpenText-CS%2025.x-green)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## What This Does

This MCP server exposes OpenText Content Server REST API v2 as tools that Claude Desktop can call natively. Ask Claude in plain English — it figures out which tool to call, passes the right parameters, and returns results directly in the chat.

**Example prompts:**
- _"Search for all Purchase Contracts"_
- _"Browse folder 25402"_
- _"Get the category metadata for node 25409"_
- _"Show me the category schema for category 18989"_
- _"Find business workspaces linked to SAP PO 4500012345"_

---

## Tools (12)

| Tool | Description |
|------|-------------|
| `search_documents` | Full-text search across Content Server |
| `get_node` | Get full properties of any node by ID |
| `browse_folder` | List children of a folder or workspace |
| `get_node_categories` | Get category metadata values for a node |
| `get_node_versions` | List version history for a document |
| `get_category_schema` | Retrieve category attribute schema |
| `get_category_definition` | Decode raw CS category binary to field names |
| `search_business_workspaces` | Find xECM workspaces linked to SAP BOs |
| `get_archivelink_documents` | Query SAP ArchiveLink stored documents |
| `create_folder` | Create a new folder in Content Server |
| `get_server_info` | Get CS version and instance info |
| `whoami` | Return authenticated user profile |

---

## Resources (3)

| Resource URI | Description |
|---|---|
| `config://server` | Current server config (non-sensitive) |
| `reference://sap-bo-types` | SAP Business Object type reference |
| `reference://ot-subtypes` | OpenText node subtype reference |

---

## Prerequisites

- Python 3.10+
- Claude Desktop (latest)
- OpenText Content Server 23.x or 25.x with REST API v2 enabled
- A valid CS user account with appropriate permissions

```bash
pip install mcp httpx python-dotenv
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/opentext-mcp-server.git
cd opentext-mcp-server
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install mcp httpx python-dotenv
```

### 3. Configure your environment

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

```env
OT_BASE_URL=https://your-ot-instance.com/cs/cs
OT_USERNAME=your_username
OT_PASSWORD=your_password
OT_API_BASE=https://your-ot-instance.com/cs/cs/api/v2
```

> **Important:** The `OT_BASE_URL` should end at `/cs/cs` — do NOT include `/api/v1/auth` in the base URL or you will get a double-path authentication error.

### 4. Configure Claude Desktop

Edit your Claude Desktop config file:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "opentext-content-server": {
      "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\opentext_mcp_server\\server.py"]
    }
  }
}
```

### 5. Restart Claude Desktop

Fully quit Claude Desktop (system tray → Quit), then reopen. Check the MCP logs to confirm all 12 tools loaded:

```
Server started and connected successfully
Processing request of type ListToolsRequest
```

---

## Architecture

```
Claude Desktop
     │
     │  MCP (stdio transport)
     ▼
server.py  (FastMCP)
     │
     │  OTCSTicket auth (auto-refresh every 25 min)
     ▼
OpenText Content Server REST API v2
     │
     ├── /search
     ├── /nodes/{id}
     ├── /nodes/{id}/nodes
     ├── /nodes/{id}/categories
     ├── /nodes/{id}/versions
     ├── /businessworkspaces
     └── /archivelink/documents
```

---

## Authentication

This server uses **OTCSTicket** session-based authentication:

1. On first tool call, `POST /api/v1/auth` with username + password
2. Ticket cached in memory with a 25-minute TTL (before the 30-min CS expiry)
3. Auto-refreshes transparently on expiry — no manual re-auth needed

Credentials are loaded from `.env` and never logged or returned in tool responses.

---

## Tested Against

| Environment | Version |
|---|---|
| OpenText Content Server | 25.2 |
| OpenText Aviator Demo | ai.content-aviator.cloud |
| Python | 3.11 |
| FastMCP | 1.27.1 |
| Claude Desktop | Latest |

---

## Known Limitations

- `browse_folder` returns a 500 for transport package folders (CS system restriction)
- `get_category_schema` endpoint varies by CS version — use `get_category_definition` for reliable attribute name resolution on CS 25.x
- ArchiveLink tool endpoint path may need adjustment to match your `OAC0` configuration in SAP

---

## Contributing

Pull requests welcome. If you're extending this for a specific SAP integration (VIM, xECM, SuccessFactors), open an issue first to discuss the approach.

---

## License

MIT — free to use, modify, and distribute.

---

## Author

**Sandesh Nair**  
Senior Manager, Accenture Global OpenText Practice  
CCA-F Certified | OpenText + SAP Integration Specialist  
[LinkedIn](https://www.linkedin.com/in/sandesh-nair) | [GitHub](https://github.com/YOUR_USERNAME)

