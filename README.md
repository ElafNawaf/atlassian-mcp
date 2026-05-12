# Atlassian MCP Server

Standalone MCP server for Atlassian products (Jira, Bitbucket, Confluence, Bamboo) — 116 tools over stdio or HTTP.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.template .env
# Edit .env with your Atlassian credentials

# 3. Run (stdio mode — for Cursor, Claude Code, etc.)
python server.py

# 3b. Run (HTTP mode)
MCP_TRANSPORT=streamable-http python server.py
```

## Tools (28)

### Jira (8)
| Tool | Description |
|------|-------------|
| `mcp_jira_search_issues` | Search issues using JQL |
| `mcp_jira_get_issue` | Get issue details |
| `mcp_jira_create_issue` | Create a new issue |
| `mcp_jira_update_issue` | Update an existing issue |
| `mcp_jira_add_comment` | Add a comment to an issue |
| `mcp_jira_create_subtasks` | Create subtasks under a parent |
| `mcp_jira_transition_issue` | Transition issue status |
| `mcp_jira_get_project_info` | Get project metadata |

### Bitbucket (7)
| Tool | Description |
|------|-------------|
| `mcp_bitbucket_list_prs` | List pull requests |
| `mcp_bitbucket_get_pr` | Get PR details |
| `mcp_bitbucket_pr_diff` | Get PR code diff |
| `mcp_bitbucket_pr_comment` | Comment on a PR |
| `mcp_bitbucket_approve_pr` | Approve a PR |
| `mcp_bitbucket_merge_pr` | Merge a PR |
| `mcp_bitbucket_list_repos` | List repositories |

### Confluence (12)
| Tool | Description |
|------|-------------|
| `mcp_confluence_search` | Search pages and content |
| `mcp_confluence_get_page` | Get page by ID or title |
| `mcp_confluence_get_page_versions` | List all versions of a page (number, author, when, message) |
| `mcp_confluence_get_page_version` | Get body.storage of a specific historical version (recover reverted content) |
| `mcp_confluence_get_child_pages` | List direct child pages |
| `mcp_confluence_get_page_ancestors` | Get the breadcrumb chain (id/title) |
| `mcp_confluence_get_attachments` | List page attachments |
| `mcp_confluence_get_page_labels` | List page labels |
| `mcp_confluence_create_page` | Create a new page |
| `mcp_confluence_update_page` | Update an existing page |
| `mcp_confluence_add_comment` | Add a page comment |
| `mcp_confluence_list_spaces` | List spaces |

### Bamboo (7)
| Tool | Description |
|------|-------------|
| `mcp_bamboo_list_plans` | List build plans |
| `mcp_bamboo_list_builds` | List builds for a plan |
| `mcp_bamboo_build_status` | Get build status |
| `mcp_bamboo_get_build` | Get build details |
| `mcp_bamboo_trigger_build` | Trigger a new build |
| `mcp_bamboo_summarize_failures` | Summarize build failures |
| `mcp_bamboo_get_build_log` | Get build log output |

## Safety

- **Dry-run by default**: All write operations (create, update, comment, merge, trigger) require `execute=true` parameter AND `WORKGRAPH_MODE=EXECUTE` in `.env`. Without both, they return what *would* happen.
- **Allowlists**: Restrict access to specific projects/repos/spaces/plans via comma-separated env vars.
- **Audit log**: Every tool call is logged to `audit.log.jsonl` with automatic credential redaction.
- **Mock mode**: Set `MOCK_MODE=true` for sample data without real API calls.

## Cursor / Claude Code Configuration

Add to your MCP settings (e.g. `~/.cursor/mcp.json` or Claude Code config):

```json
{
  "mcpServers": {
    "atlassian": {
      "command": "python",
      "args": ["/Users/elafnawaf/PycharmProjects/atlassian-mcp/server.py"]
    }
  }
}
```

## Project Structure

```
atlassian-mcp/
  server.py          # MCP server entry point (28 tool registrations)
  tools.py           # Tool handler implementations
  clients.py         # httpx clients for Jira/Bitbucket/Confluence/Bamboo
  config.py          # Environment loading, logging, allowlists
  audit.py           # JSONL audit logging with redaction
  requirements.txt   # Python dependencies
  .env.template      # Configuration template
  .env               # Your credentials (gitignored)
```
