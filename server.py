"""
OpenText Content Server — MCP Server
=====================================
Exposes OpenText Content Server REST API v2 as MCP tools for Claude Desktop.

Tools (12):
  - search_documents
  - get_node
  - browse_folder
  - get_node_categories
  - get_node_versions
  - get_category_schema
  - get_category_definition
  - search_business_workspaces
  - get_archivelink_documents
  - create_folder
  - get_server_info
  - whoami

Resources (3):
  - config://server
  - reference://sap-bo-types
  - reference://ot-subtypes

Auth: OTCSTicket-based session with auto-refresh before 30-min timeout.

Prerequisites:
    pip install mcp httpx python-dotenv

Author: Sandesh Nair (sandesh.nair@gmail.com)
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

OT_BASE_URL  = os.getenv("OT_BASE_URL", "https://your-ot-instance.com").rstrip("/")
OT_USERNAME  = os.getenv("OT_USERNAME", "")
OT_PASSWORD  = os.getenv("OT_PASSWORD", "")
OT_API_BASE  = os.getenv("OT_API_BASE", f"{OT_BASE_URL}/cs/cs/api/v2")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("opentext-mcp")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP("opentext-content-server")

# ---------------------------------------------------------------------------
# HTTP Client with OTCSTicket Auth
# ---------------------------------------------------------------------------
class OTClient:
    TICKET_TTL_MINUTES = 25  # Refresh before the 30-min OT expiry

    def __init__(self):
        self._ticket: Optional[str] = None
        self._ticket_ts: Optional[datetime] = None
        self._http = httpx.Client(timeout=30.0, verify=True)

    def _ticket_expired(self) -> bool:
        if not self._ticket or not self._ticket_ts:
            return True
        return datetime.now() - self._ticket_ts > timedelta(minutes=self.TICKET_TTL_MINUTES)

    def _authenticate(self) -> str:
        logger.info("Authenticating with OpenText Content Server...")
        resp = self._http.post(
            f"{OT_BASE_URL}/api/v1/auth",
            data={"username": OT_USERNAME, "password": OT_PASSWORD},
        )
        resp.raise_for_status()
        ticket = resp.json().get("ticket") or resp.json().get("otcsticket")
        if not ticket:
            raise ValueError(f"No ticket in auth response: {resp.text}")
        self._ticket = ticket
        self._ticket_ts = datetime.now()
        logger.info("Authentication successful.")
        return ticket

    def ticket(self) -> str:
        if self._ticket_expired():
            self._authenticate()
        return self._ticket

    def get(self, path: str, params: dict = None) -> dict:
        headers = {"OTCSTicket": self.ticket()}
        url = f"{OT_API_BASE}{path}"
        resp = self._http.get(url, headers=headers, params=params or {})
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, data: dict = None, json: dict = None) -> dict:
        headers = {"OTCSTicket": self.ticket()}
        url = f"{OT_API_BASE}{path}"
        resp = self._http.post(url, headers=headers, data=data, json=json)
        resp.raise_for_status()
        return resp.json()


_client = OTClient()

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_documents(query: str, limit: int = 20, location_id: int = None) -> dict:
    """
    Full-text search across OpenText Content Server.

    Args:
        query:       Search terms (supports OT search syntax)
        limit:       Max results to return (default 20)
        location_id: Optional node ID to scope search to a specific folder

    Returns:
        List of matching nodes with name, ID, type, location, and modified date.
    """
    try:
        params = {
            "where": query,
            "limit": limit,
            "modifier": "relatedto",
            "lookfor": "allwords"
        }
        if location_id:
            params["location_id1"] = location_id

        result = _client.get("/search", params=params)
        hits = result.get("results", [])
        return {
            "total": len(hits),
            "results": [
                {
                    "id": h.get("data", {}).get("properties", {}).get("id"),
                    "name": h.get("data", {}).get("properties", {}).get("name"),
                    "type": h.get("data", {}).get("properties", {}).get("type"),
                    "parent_id": h.get("data", {}).get("properties", {}).get("parent_id"),
                    "modify_date": h.get("data", {}).get("properties", {}).get("modify_date"),
                }
                for h in hits
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_category_schema(category_id: int, node_id: int = None) -> dict:
    """
    Retrieve the full schema (attribute names, types) for a category definition.

    Args:
        category_id: Node ID of the category definition
        node_id:     A node that has this category applied (for values)

    Returns:
        List of attributes with key, name, type, and current value.
    """
    try:
        # Get attribute definitions from the category template node
        schema_result = _client.get(f"/nodes/{category_id}/categories")

        # Get values if a node_id is provided
        values = {}
        if node_id:
            val_result = _client.get(f"/nodes/{node_id}/categories/{category_id}")
            values = (
                val_result.get("results", {})
                          .get("data", {})
                          .get("categories", {})
            )

        fields = []
        results = schema_result.get("results", [])
        for item in results:
            data = item.get("data", {})
            cats = data.get("categories", {})
            defs = data.get("definitions", cats)
            for key, attr in defs.items():
                if not key.startswith(f"{category_id}_"):
                    continue
                if isinstance(attr, dict):
                    fields.append({
                        "key": key,
                        "name": attr.get("name") or attr.get("title") or key,
                        "type": attr.get("type"),
                        "required": attr.get("required", False),
                        "value": values.get(key),
                    })
                else:
                    fields.append({
                        "key": key,
                        "name": key,
                        "value": values.get(key),
                    })

        return {
            "category_id": category_id,
            "attribute_count": len(fields),
            "attributes": fields,
            "raw_schema": schema_result if not fields else None,
        }
    except Exception as e:
        return {"error": str(e)}
        
        
@mcp.tool()
def browse_folder(folder_id: int, page: int = 1, limit: int = 50) -> dict:
    """
    List the children of a folder or container node.
    Args:
        folder_id: Node ID of the folder to browse
        page:      Page number (default 1)
        limit:     Items per page (default 50)
    Returns:
        List of child nodes with ID, name, type, and modified date.
    """
    try:
        result = _client.get(
            f"/nodes/{folder_id}/nodes",
            params={"page": page, "limit": limit},
        )
        if isinstance(result, list):
            items = result
        elif isinstance(result.get("results"), list):
            items = result.get("results", [])
        else:
            items = (
                result.get("results", {}).get("data", [])
                or result.get("data", [])
                or []
            )

        def extract(i):
            if "data" in i and "properties" in i.get("data", {}):
                p = i["data"]["properties"]
            else:
                p = i
            return {
                "id": p.get("id"),
                "name": p.get("name"),
                "type": p.get("type"),
                "modify_date": p.get("modify_date"),
                "size": p.get("size"),
            }

        return {
            "folder_id": folder_id,
            "page": page,
            "count": len(items),
            "children": [extract(i) for i in items],
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_category_definition(category_id: int) -> dict:
    """
    Retrieve the raw XML definition of a category to extract attribute names.

    Args:
        category_id: Node ID of the category definition

    Returns:
        Raw category definition with attribute names and types.
    """
    try:
        import xml.etree.ElementTree as ET

        # Fetch the category version content (returns XML in CS)
        resp = _client._http.get(
            f"{OT_API_BASE}/nodes/{category_id}/versions/1/content",
            headers={"OTCSTicket": _client.ticket()},
        )
        resp.raise_for_status()

        # Try to parse as XML
        try:
            root = ET.fromstring(resp.text)
            attributes = []
            for attr in root.iter("Attribute"):
                attributes.append({
                    "key": attr.get("Key") or attr.get("key"),
                    "name": attr.get("Name") or attr.get("name") or attr.get("DisplayName"),
                    "type": attr.get("Type") or attr.get("type"),
                    "required": attr.get("Required") or attr.get("required"),
                    "default": attr.get("DefaultValue") or attr.get("default_value"),
                })
            return {
                "category_id": category_id,
                "attribute_count": len(attributes),
                "attributes": attributes,
                "raw_text": resp.text if not attributes else None,
            }
        except ET.ParseError:
            # Not XML — return raw text for inspection
            return {
                "category_id": category_id,
                "raw_text": resp.text[:2000],
            }

    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_node_categories(node_id: int) -> dict:
    """
    Retrieve all category metadata attributes assigned to a node.

    Args:
        node_id: Node ID

    Returns:
        Category names and their attribute key-value pairs.
    """
    try:
        return _client.get(f"/nodes/{node_id}/categories")
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_node_versions(node_id: int) -> dict:
    """
    List version history for a document node.

    Args:
        node_id: Node ID of the document

    Returns:
        List of versions with version number, file size, modified by, and date.
    """
    try:
        result = _client.get(f"/nodes/{node_id}/versions")
        versions = result.get("data", [])
        return {
            "node_id": node_id,
            "version_count": len(versions),
            "versions": [
                {
                    "version_number": v.get("version_number"),
                    "file_size": v.get("file_size"),
                    "owner": v.get("owner"),
                    "modify_date": v.get("modify_date"),
                    "mime_type": v.get("mime_type"),
                }
                for v in versions
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def search_business_workspaces(bo_type: str, bo_id: str) -> dict:
    """
    Find xECM Business Workspaces linked to a SAP Business Object.

    Args:
        bo_type: SAP Business Object type (e.g. BUS2012, KNA1, LFA1, BKPF)
        bo_id:   SAP Business Object ID / key (e.g. PO number, vendor number)

    Returns:
        Matching Business Workspaces with node ID, name, and workspace type.
    """
    try:
        result = _client.get(
            "/businessworkspaces",
            params={"bo_type": bo_type, "bo_id": bo_id},
        )
        workspaces = result.get("results", {}).get("data", [])
        return {
            "bo_type": bo_type,
            "bo_id": bo_id,
            "count": len(workspaces),
            "workspaces": [
                {
                    "id": w.get("id"),
                    "name": w.get("name"),
                    "workspace_type_name": w.get("workspace_type_name"),
                    "modify_date": w.get("modify_date"),
                }
                for w in workspaces
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_archivelink_documents(
    sap_object_type: str,
    sap_object_id: str,
    doc_type: str = "",
) -> dict:
    """
    Query SAP ArchiveLink-stored documents for a given SAP object.

    Args:
        sap_object_type: SAP object type (e.g. BKPF, EKKO, KNA1)
        sap_object_id:   SAP object key / ID
        doc_type:        Optional ArchiveLink document type filter

    Returns:
        List of archived documents with archive ID, document ID, and content type.

    Note:
        Adjust the endpoint path to match your HTTP Content Server / OAC0 config.
    """
    try:
        params = {
            "sap_object_type": sap_object_type,
            "sap_object_id": sap_object_id,
        }
        if doc_type:
            params["doc_type"] = doc_type
        result = _client.get("/archivelink/documents", params=params)
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def create_folder(parent_id: int, name: str) -> dict:
    """
    Create a new folder inside a parent node.

    Args:
        parent_id: Node ID of the parent folder/container
        name:      Name for the new folder

    Returns:
        New folder node ID, name, and creation date.
    """
    try:
        result = _client.post(
            "/nodes",
            data={"type": 0, "parent_id": parent_id, "name": name},
        )
        return {
            "created": True,
            "id": result.get("id"),
            "name": result.get("name"),
            "create_date": result.get("create_date"),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_server_info() -> dict:
    """
    Retrieve OpenText Content Server version and instance information.

    Returns:
        Server version, mobile server version, and server metadata.
    """
    try:
        return _client.get("/serverinfo")
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def whoami() -> dict:
    """
    Return the currently authenticated user's profile and permissions.

    Returns:
        Username, display name, email, and group memberships.
    """
    try:
        return _client.get("/members/me")
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Resources (read-only reference data)
# ---------------------------------------------------------------------------

@mcp.resource("config://server")
def server_config() -> str:
    """Current server configuration (non-sensitive)."""
    return (
        f"OT_BASE_URL: {OT_BASE_URL}\n"
        f"OT_API_BASE: {OT_API_BASE}\n"
        f"OT_USERNAME: {OT_USERNAME}\n"
        f"Ticket TTL:  {OTClient.TICKET_TTL_MINUTES} minutes\n"
    )


@mcp.resource("reference://sap-bo-types")
def sap_bo_types() -> str:
    """SAP Business Object type reference for use with search_business_workspaces."""
    return """
SAP Business Object Types — xECM Reference
===========================================
BUS2012  Purchase Order (ME21N/ME23N)
BUS2105  Purchase Requisition (ME51N/ME53N)
BUS2081  Goods Receipt / Material Document (MIGO)
BKPF     Accounting Document (FB03)
KNA1     Customer Master (XD03)
LFA1     Vendor Master (XK03)
DRAW     DMS Document Info Record (CV03N)
PREL     HR Personnel File (PA20)
VBAK     Sales Order (VA03)
EQUI     Equipment Master (IE03)
BUS1006  Business Partner (BP)
PROJ     WBS / Project (CJ20N)
"""


@mcp.resource("reference://ot-subtypes")
def ot_subtypes() -> str:
    """OpenText node subtype reference."""
    return """
OpenText Node Type Reference
=============================
0    Folder
1    Shortcut / Alias
2    URL
144  Document
146  Compound Document
202  Task List
204  Project
207  Discussion
215  Channel
258  Search Query
299  LiveReport
731  Record Folder
736  Physical Object
848  Business Workspace (xECM)
"""

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")