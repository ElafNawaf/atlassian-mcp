"""
Atlassian MCP Server — standalone, 110 tools over stdio/HTTP.

Run:
  python server.py                    # stdio (default, for Cursor/Claude Code)
  MCP_TRANSPORT=streamable-http python server.py  # HTTP

Covers: Jira typed (86) + Bitbucket (7) + Confluence (6) + Bamboo (7) + 4 raw passthroughs
"""
import os

from config import setup_logging, get_logger

setup_logging()
logger = get_logger("mcp_server")

from mcp.server.fastmcp import FastMCP
from tools import (
    # Jira
    jira_search_issues,
    jira_get_issue,
    jira_create_issue,
    jira_update_issue,
    jira_add_comment,
    jira_create_subtasks,
    jira_transition_issue,
    jira_get_project_info,
    # Jira Agile
    jira_list_boards,
    jira_get_board,
    jira_get_board_config,
    jira_get_board_issues,
    jira_get_board_epics,
    jira_get_board_backlog,
    jira_get_board_sprints,
    jira_get_sprint,
    jira_create_sprint,
    jira_update_sprint,
    jira_get_sprint_issues,
    jira_move_issues_to_sprint,
    jira_move_issues_to_backlog,
    jira_get_epic,
    jira_get_epic_issues,
    jira_move_issues_to_epic,
    jira_rank_issues,
    # Jira Extended
    jira_get_attachment,
    jira_delete_attachment,
    jira_get_attachment_meta,
    jira_get_issue_worklogs,
    jira_add_issue_worklog,
    jira_update_issue_worklog,
    jira_delete_issue_worklog,
    jira_get_issue_watchers,
    jira_add_issue_watcher,
    jira_remove_issue_watcher,
    jira_get_issue_link_types,
    jira_create_issue_link,
    jira_get_issue_link,
    jira_delete_issue_link,
    jira_get_issue_remote_links,
    jira_create_issue_remote_link,
    jira_delete_issue_remote_link,
    jira_get_project_versions,
    jira_get_version,
    jira_create_version,
    jira_update_version,
    jira_delete_version,
    jira_get_project_components,
    jira_get_component,
    jira_create_component,
    jira_update_component,
    jira_delete_component,
    jira_assign_issue,
    jira_list_transitions,
    jira_get_createmeta,
    jira_bulk_create_issues,
    jira_archive_issue,
    jira_restore_issue,
    jira_get_filter,
    jira_get_favourite_filters,
    jira_create_filter,
    jira_update_filter,
    jira_delete_filter,
    # Jira Dashboards
    jira_list_dashboards,
    jira_get_dashboard,
    jira_list_dashboard_item_properties,
    jira_get_dashboard_item_property,
    jira_set_dashboard_item_property,
    jira_delete_dashboard_item_property,
    # Jira Dashboards plugin (create/edit dashboards & gadgets)
    jira_create_dashboard,
    jira_update_dashboard,
    jira_delete_dashboard,
    jira_list_available_gadgets,
    jira_list_dashboard_gadgets,
    jira_add_dashboard_gadget,
    jira_move_dashboard_gadget,
    jira_remove_dashboard_gadget,
    jira_set_dashboard_gadget_prefs,
    # Jira lookup helpers (for dashboard/gadget configuration)
    jira_get_myself,
    jira_search_users,
    jira_list_groups,
    jira_list_projects,
    jira_list_statuses,
    jira_list_priorities,
    jira_list_issue_types,
    jira_list_fields,
    # Bitbucket
    bitbucket_list_prs,
    bitbucket_get_pr,
    bitbucket_pr_diff,
    bitbucket_pr_comment,
    bitbucket_approve_pr,
    bitbucket_merge_pr,
    bitbucket_list_repos,
    # Confluence
    confluence_search,
    confluence_get_page,
    confluence_create_page,
    confluence_update_page,
    confluence_add_comment,
    confluence_list_spaces,
    # Bamboo
    bamboo_list_plans,
    bamboo_list_builds,
    bamboo_build_status,
    bamboo_get_build,
    bamboo_trigger_build,
    bamboo_summarize_failures,
    bamboo_get_build_log,
    # Raw passthroughs
    jira_raw,
    bitbucket_raw,
    confluence_raw,
    bamboo_raw,
)
from typing import Any
import functools
import httpx

_mcp_host = os.getenv("MCP_HOST", "127.0.0.1")
_mcp_port = int(os.getenv("MCP_PORT", "8000"))
_mcp_transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()

mcp = FastMCP(
    "Atlassian",
    instructions="Atlassian automation: Jira, Bitbucket, Confluence, Bamboo — 110 tools (typed + raw passthroughs) for complete SDLC management, including dashboard creation and gadget management.",
    host=_mcp_host,
    port=_mcp_port,
    json_response=True,
)


def safe_tool():
    """Wrap @safe_tool() so exceptions become structured errors the LLM can read."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                body = ""
                try:
                    body = e.response.text[:2000]
                except Exception:
                    pass
                logger.warning("%s HTTP %s: %s", fn.__name__, e.response.status_code, body[:200])
                return {
                    "error": True,
                    "type": "http_error",
                    "status": e.response.status_code,
                    "url": str(e.request.url) if e.request else None,
                    "message": f"{e.response.status_code} {e.response.reason_phrase}",
                    "response": body,
                }
            except httpx.RequestError as e:
                logger.warning("%s network error: %s", fn.__name__, e)
                return {"error": True, "type": "network_error", "message": str(e)}
            except ValueError as e:
                logger.info("%s validation: %s", fn.__name__, e)
                return {"error": True, "type": "validation_error", "message": str(e)}
            except Exception as e:
                logger.exception("%s failed", fn.__name__)
                return {"error": True, "type": type(e).__name__, "message": str(e)}
        return mcp.tool()(wrapper)
    return deco


# ============================================================================
# Jira Tools (8)
# ============================================================================

@safe_tool()
def mcp_jira_search_issues(jql: str, max_results: int = 50) -> dict:
    """Search Jira issues using JQL. Returns matching issues with details like summary, status, assignee."""
    return jira_search_issues(jql, max_results)


@safe_tool()
def mcp_jira_get_issue(issue_key: str) -> dict:
    """Get detailed information about a specific Jira issue including description, comments, and history."""
    return jira_get_issue(issue_key)


@safe_tool()
def mcp_jira_create_issue(
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: str | None = None,
    assignee: str | None = None,
    labels: list[str] | None = None,
    execute: bool = True,
) -> dict:
    """Create a new Jira issue. Set execute=true to actually create (dry-run by default)."""
    return jira_create_issue(project_key, summary, description, issue_type, priority, assignee, labels, execute)


@safe_tool()
def mcp_jira_update_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    execute: bool = True,
) -> dict:
    """Update an existing Jira issue. Set execute=true to actually update (dry-run by default)."""
    return jira_update_issue(issue_key, summary, description, assignee, priority, status, execute)


@safe_tool()
def mcp_jira_add_comment(issue_key: str, comment: str, execute: bool = True) -> dict:
    """Add a comment to a Jira issue. Set execute=true to actually comment (dry-run by default)."""
    return jira_add_comment(issue_key, comment, execute)


@safe_tool()
def mcp_jira_create_subtasks(parent_issue_key: str, subtasks: list[dict], execute: bool = True) -> dict:
    """
    Create multiple subtasks under a parent Jira issue. Set execute=true to actually create.

    Each subtask: {"summary": "...", "description": "..."}
    """
    return jira_create_subtasks(parent_issue_key, subtasks, execute)


@safe_tool()
def mcp_jira_transition_issue(issue_key: str, transition_name: str, execute: bool = True) -> dict:
    """
    Transition a Jira issue to a new status. Set execute=true to actually transition.

    Common transitions: 'In Progress', 'Done', 'To Do', 'Blocked', 'In Review'
    """
    return jira_transition_issue(issue_key, transition_name, execute)


@safe_tool()
def mcp_jira_get_project_info(project_key: str) -> dict:
    """Get information about a Jira project including available issue types, statuses, and metadata."""
    return jira_get_project_info(project_key)


# ============================================================================
# Jira Agile Tools (17)
# ============================================================================

@safe_tool()
def mcp_jira_list_boards(name: str | None = None, project_key: str | None = None,
                         board_type: str | None = None, max_results: int = 50, start_at: int = 0) -> dict:
    """
    List all Jira boards. Optionally filter by name, project key, or type.

    Board types: scrum, kanban
    """
    return jira_list_boards(name, project_key, board_type, max_results, start_at)


@safe_tool()
def mcp_jira_get_board(board_id: int) -> dict:
    """Get a single Jira board by ID."""
    return jira_get_board(board_id)


@safe_tool()
def mcp_jira_get_board_config(board_id: int) -> dict:
    """Get the configuration of a Jira board including columns, estimation type, and ranking field."""
    return jira_get_board_config(board_id)


@safe_tool()
def mcp_jira_get_board_issues(board_id: int, jql: str | None = None,
                              max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues from a Jira board. Includes agile fields (sprint, epic, flagged). Optionally filter with JQL."""
    return jira_get_board_issues(board_id, jql, max_results, start_at)


@safe_tool()
def mcp_jira_get_board_epics(board_id: int, done: bool = False,
                             max_results: int = 50, start_at: int = 0) -> dict:
    """Get all epics from a board. Set done=true to include completed epics."""
    return jira_get_board_epics(board_id, done, max_results, start_at)


@safe_tool()
def mcp_jira_get_board_backlog(board_id: int, jql: str | None = None,
                               max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues from a board's backlog."""
    return jira_get_board_backlog(board_id, jql, max_results, start_at)


@safe_tool()
def mcp_jira_get_board_sprints(board_id: int, state: str | None = None,
                               max_results: int = 50, start_at: int = 0) -> dict:
    """
    Get all sprints from a board.

    States: future, active, closed (comma-separated for multiple, e.g. 'active,closed')
    """
    return jira_get_board_sprints(board_id, state, max_results, start_at)


@safe_tool()
def mcp_jira_get_sprint(sprint_id: int) -> dict:
    """Get a single sprint by ID including name, state, dates, and goal."""
    return jira_get_sprint(sprint_id)


@safe_tool()
def mcp_jira_create_sprint(board_id: int, name: str, start_date: str | None = None,
                           end_date: str | None = None, goal: str | None = None,
                           execute: bool = True) -> dict:
    """
    Create a future sprint on a board. Set execute=true to actually create.

    Dates in ISO 8601 format (e.g. '2024-01-15T09:00:00.000Z').
    """
    return jira_create_sprint(board_id, name, start_date, end_date, goal, execute)


@safe_tool()
def mcp_jira_update_sprint(sprint_id: int, name: str | None = None, state: str | None = None,
                           start_date: str | None = None, end_date: str | None = None,
                           goal: str | None = None, execute: bool = True) -> dict:
    """
    Update a sprint. Set execute=true to actually update.

    Set state='active' to start a sprint (requires start/end dates).
    Set state='closed' to complete an active sprint.
    """
    return jira_update_sprint(sprint_id, name, state, start_date, end_date, goal, execute)


@safe_tool()
def mcp_jira_get_sprint_issues(sprint_id: int, jql: str | None = None,
                               max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues in a sprint. Ordered by rank by default."""
    return jira_get_sprint_issues(sprint_id, jql, max_results, start_at)


@safe_tool()
def mcp_jira_move_issues_to_sprint(sprint_id: int, issue_keys: list[str], execute: bool = True) -> dict:
    """Move issues to a sprint. Maximum 50 issues. Set execute=true to actually move."""
    return jira_move_issues_to_sprint(sprint_id, issue_keys, execute)


@safe_tool()
def mcp_jira_move_issues_to_backlog(issue_keys: list[str], execute: bool = True) -> dict:
    """Move issues to the backlog (removes from any sprint). Maximum 50 issues. Set execute=true to actually move."""
    return jira_move_issues_to_backlog(issue_keys, execute)


@safe_tool()
def mcp_jira_get_epic(epic_id_or_key: str) -> dict:
    """Get an epic by ID or issue key."""
    return jira_get_epic(epic_id_or_key)


@safe_tool()
def mcp_jira_get_epic_issues(epic_id_or_key: str, jql: str | None = None,
                             max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues belonging to an epic. Ordered by rank by default."""
    return jira_get_epic_issues(epic_id_or_key, jql, max_results, start_at)


@safe_tool()
def mcp_jira_move_issues_to_epic(epic_id_or_key: str, issue_keys: list[str], execute: bool = True) -> dict:
    """Move issues to an epic. Maximum 50 issues. Set execute=true to actually move."""
    return jira_move_issues_to_epic(epic_id_or_key, issue_keys, execute)


@safe_tool()
def mcp_jira_rank_issues(issue_keys: list[str], rank_before_issue: str | None = None,
                         rank_after_issue: str | None = None, execute: bool = True) -> dict:
    """
    Rank (reorder) issues on a board. Maximum 50 issues. Set execute=true to actually rank.

    Specify either rank_before_issue or rank_after_issue to position the issues.
    """
    return jira_rank_issues(issue_keys, rank_before_issue, rank_after_issue, execute)


# ============================================================================
# Jira Extended Tools (attachments, worklogs, watchers, links, versions,
# components, archive, filters, bulk)
# ============================================================================

# ── Attachments ─────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_get_attachment(attachment_id: str) -> dict:
    """Get Jira attachment metadata by ID."""
    return jira_get_attachment(attachment_id)


@safe_tool()
def mcp_jira_delete_attachment(attachment_id: str, execute: bool = True) -> dict:
    """Delete a Jira attachment by ID. Dry-run by default."""
    return jira_delete_attachment(attachment_id, execute)


@safe_tool()
def mcp_jira_get_attachment_meta() -> dict:
    """Get Jira attachment capabilities (enabled, max upload size)."""
    return jira_get_attachment_meta()


# ── Worklogs ────────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_get_issue_worklogs(issue_key: str) -> dict:
    """List all worklogs for a Jira issue."""
    return jira_get_issue_worklogs(issue_key)


@safe_tool()
def mcp_jira_add_issue_worklog(
    issue_key: str, time_spent: str, comment: str = "",
    started: str | None = None, execute: bool = True,
) -> dict:
    """Add a worklog entry to an issue. time_spent like '3h 20m'. Dry-run by default."""
    return jira_add_issue_worklog(issue_key, time_spent, comment, started, execute)


@safe_tool()
def mcp_jira_update_issue_worklog(
    issue_key: str, worklog_id: str, time_spent: str | None = None,
    comment: str | None = None, execute: bool = True,
) -> dict:
    """Update a worklog entry. Dry-run by default."""
    return jira_update_issue_worklog(issue_key, worklog_id, time_spent, comment, execute)


@safe_tool()
def mcp_jira_delete_issue_worklog(issue_key: str, worklog_id: str, execute: bool = True) -> dict:
    """Delete a worklog entry. Dry-run by default."""
    return jira_delete_issue_worklog(issue_key, worklog_id, execute)


# ── Watchers ────────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_get_issue_watchers(issue_key: str) -> dict:
    """Get watchers for a Jira issue."""
    return jira_get_issue_watchers(issue_key)


@safe_tool()
def mcp_jira_add_issue_watcher(issue_key: str, username: str, execute: bool = True) -> dict:
    """Add a watcher to a Jira issue. Dry-run by default."""
    return jira_add_issue_watcher(issue_key, username, execute)


@safe_tool()
def mcp_jira_remove_issue_watcher(issue_key: str, username: str, execute: bool = True) -> dict:
    """Remove a watcher from a Jira issue. Dry-run by default."""
    return jira_remove_issue_watcher(issue_key, username, execute)


# ── Issue Links ─────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_get_issue_link_types() -> dict:
    """List all available Jira issue link types (Blocks, Relates, etc.)."""
    return jira_get_issue_link_types()


@safe_tool()
def mcp_jira_create_issue_link(
    link_type: str, inward_issue: str, outward_issue: str,
    comment: str | None = None, execute: bool = True,
) -> dict:
    """Link two Jira issues (e.g. 'Blocks', 'Relates'). Dry-run by default."""
    return jira_create_issue_link(link_type, inward_issue, outward_issue, comment, execute)


@safe_tool()
def mcp_jira_get_issue_link(link_id: str) -> dict:
    """Get a Jira issue link by ID."""
    return jira_get_issue_link(link_id)


@safe_tool()
def mcp_jira_delete_issue_link(link_id: str, execute: bool = True) -> dict:
    """Delete a Jira issue link by ID. Dry-run by default."""
    return jira_delete_issue_link(link_id, execute)


# ── Remote Links ────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_get_issue_remote_links(issue_key: str) -> dict:
    """List remote (web) links on a Jira issue."""
    return jira_get_issue_remote_links(issue_key)


@safe_tool()
def mcp_jira_create_issue_remote_link(
    issue_key: str, url: str, title: str, summary: str | None = None,
    global_id: str | None = None, execute: bool = True,
) -> dict:
    """Create or update a remote link on a Jira issue. Dry-run by default."""
    return jira_create_issue_remote_link(issue_key, url, title, summary, global_id, execute)


@safe_tool()
def mcp_jira_delete_issue_remote_link(issue_key: str, link_id: str, execute: bool = True) -> dict:
    """Delete a remote link from a Jira issue. Dry-run by default."""
    return jira_delete_issue_remote_link(issue_key, link_id, execute)


# ── Versions ────────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_get_project_versions(project_key: str) -> dict:
    """Get all versions (releases) for a Jira project."""
    return jira_get_project_versions(project_key)


@safe_tool()
def mcp_jira_get_version(version_id: str) -> dict:
    """Get a Jira version by ID."""
    return jira_get_version(version_id)


@safe_tool()
def mcp_jira_create_version(
    project_key: str, name: str, description: str = "",
    release_date: str | None = None, released: bool = False, execute: bool = True,
) -> dict:
    """Create a Jira version (release). release_date as YYYY-MM-DD. Dry-run by default."""
    return jira_create_version(project_key, name, description, release_date, released, execute)


@safe_tool()
def mcp_jira_update_version(
    version_id: str, name: str | None = None, description: str | None = None,
    release_date: str | None = None, released: bool | None = None, execute: bool = True,
) -> dict:
    """Update a Jira version. Dry-run by default."""
    return jira_update_version(version_id, name, description, release_date, released, execute)


@safe_tool()
def mcp_jira_delete_version(version_id: str, execute: bool = True) -> dict:
    """Delete a Jira version. Dry-run by default."""
    return jira_delete_version(version_id, execute)


# ── Components ──────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_get_project_components(project_key: str) -> dict:
    """Get all components for a Jira project."""
    return jira_get_project_components(project_key)


@safe_tool()
def mcp_jira_get_component(component_id: str) -> dict:
    """Get a Jira component by ID."""
    return jira_get_component(component_id)


@safe_tool()
def mcp_jira_create_component(
    project_key: str, name: str, description: str = "",
    lead: str | None = None, execute: bool = True,
) -> dict:
    """Create a Jira component. Dry-run by default."""
    return jira_create_component(project_key, name, description, lead, execute)


@safe_tool()
def mcp_jira_update_component(
    component_id: str, name: str | None = None, description: str | None = None,
    lead: str | None = None, execute: bool = True,
) -> dict:
    """Update a Jira component. Dry-run by default."""
    return jira_update_component(component_id, name, description, lead, execute)


@safe_tool()
def mcp_jira_delete_component(component_id: str, execute: bool = True) -> dict:
    """Delete a Jira component. Dry-run by default."""
    return jira_delete_component(component_id, execute)


# ── Assign / Transitions / Metadata / Bulk / Archive ────────────────────────

@safe_tool()
def mcp_jira_assign_issue(issue_key: str, assignee: str | None, execute: bool = True) -> dict:
    """Assign a Jira issue. Pass null to unassign, '-1' for default assignee. Dry-run by default."""
    return jira_assign_issue(issue_key, assignee, execute)


@safe_tool()
def mcp_jira_list_transitions(issue_key: str) -> dict:
    """List the workflow transitions available for a Jira issue."""
    return jira_list_transitions(issue_key)


@safe_tool()
def mcp_jira_get_createmeta(project_key: str | None = None, issue_type_names: str | None = None) -> dict:
    """Get metadata for creating Jira issues (fields/issue types per project)."""
    return jira_get_createmeta(project_key, issue_type_names)


@safe_tool()
def mcp_jira_bulk_create_issues(issues: list[dict], execute: bool = True) -> dict:
    """Create many Jira issues in one call. Each item: {fields: {...}}. Dry-run by default."""
    return jira_bulk_create_issues(issues, execute)


@safe_tool()
def mcp_jira_archive_issue(issue_key: str, execute: bool = True) -> dict:
    """Archive a Jira issue. Dry-run by default."""
    return jira_archive_issue(issue_key, execute)


@safe_tool()
def mcp_jira_restore_issue(issue_key: str, execute: bool = True) -> dict:
    """Restore an archived Jira issue. Dry-run by default."""
    return jira_restore_issue(issue_key, execute)


# ── Filters ─────────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_get_filter(filter_id: str) -> dict:
    """Get a Jira saved JQL filter by ID."""
    return jira_get_filter(filter_id)


@safe_tool()
def mcp_jira_get_favourite_filters() -> dict:
    """Get the current user's favourite Jira filters."""
    return jira_get_favourite_filters()


@safe_tool()
def mcp_jira_create_filter(
    name: str, jql: str, description: str = "", favourite: bool = False, execute: bool = True,
) -> dict:
    """Create a Jira saved JQL filter. Dry-run by default."""
    return jira_create_filter(name, jql, description, favourite, execute)


@safe_tool()
def mcp_jira_update_filter(
    filter_id: str, name: str | None = None, jql: str | None = None,
    description: str | None = None, execute: bool = True,
) -> dict:
    """Update a Jira saved filter. Dry-run by default."""
    return jira_update_filter(filter_id, name, jql, description, execute)


@safe_tool()
def mcp_jira_delete_filter(filter_id: str, execute: bool = True) -> dict:
    """Delete a Jira saved filter. Dry-run by default."""
    return jira_delete_filter(filter_id, execute)


# ── Dashboards ──────────────────────────────────────────────────────────────

@safe_tool()
def mcp_jira_list_dashboards(filter: str | None = None, max_results: int = 20, start_at: int = 0) -> dict:
    """List Jira dashboards. filter='favourite' returns the user's favourites only."""
    return jira_list_dashboards(filter, max_results, start_at)


@safe_tool()
def mcp_jira_get_dashboard(dashboard_id: str) -> dict:
    """Get a single Jira dashboard by ID."""
    return jira_get_dashboard(dashboard_id)


@safe_tool()
def mcp_jira_list_dashboard_item_properties(dashboard_id: str, item_id: str) -> dict:
    """List all property keys for a dashboard item (gadget)."""
    return jira_list_dashboard_item_properties(dashboard_id, item_id)


@safe_tool()
def mcp_jira_get_dashboard_item_property(dashboard_id: str, item_id: str, property_key: str) -> dict:
    """Get a single property value for a dashboard item (gadget)."""
    return jira_get_dashboard_item_property(dashboard_id, item_id, property_key)


@safe_tool()
def mcp_jira_set_dashboard_item_property(
    dashboard_id: str, item_id: str, property_key: str, value: Any, execute: bool = True,
) -> dict:
    """Set a property on a dashboard item (gadget). value can be any JSON value."""
    return jira_set_dashboard_item_property(dashboard_id, item_id, property_key, value, execute)


@safe_tool()
def mcp_jira_delete_dashboard_item_property(
    dashboard_id: str, item_id: str, property_key: str, execute: bool = True,
) -> dict:
    """Delete a property from a dashboard item (gadget)."""
    return jira_delete_dashboard_item_property(dashboard_id, item_id, property_key, execute)


# ── Dashboards plugin (create/edit dashboards & gadgets) ────────────────────

@safe_tool()
def mcp_jira_create_dashboard(
    name: str, description: str = "", layout: str = "AA",
    share_permissions: list[dict] | None = None,
    edit_permissions: list[dict] | None = None,
    execute: bool = True,
) -> dict:
    """
    Create a new Jira dashboard via the internal Dashboards plugin.

    layout: 'A' (1 col), 'AA' (2 equal), 'AB' (2: 60/40), 'AAA' (3 equal),
            'ABA' (3: 25/50/25), 'AABC' (4 cols).
    share/edit_permissions: list of {type, [param]} dicts. Examples:
      [{'type': 'global'}]                     -> public
      [{'type': 'authenticated'}]              -> any logged-in user
      [{'type': 'user', 'param': 'username'}]  -> single user
      [{'type': 'group', 'param': 'group'}]    -> a group
      [{'type': 'project', 'param': '10000'}]  -> a project
    Defaults to private (creator only).
    """
    return jira_create_dashboard(name, description, layout, share_permissions, edit_permissions, execute)


@safe_tool()
def mcp_jira_update_dashboard(
    dashboard_id: str, name: str | None = None, description: str | None = None,
    layout: str | None = None,
    share_permissions: list[dict] | None = None,
    edit_permissions: list[dict] | None = None,
    execute: bool = True,
) -> dict:
    """Update an existing dashboard's name, description, layout, or sharing."""
    return jira_update_dashboard(dashboard_id, name, description, layout, share_permissions, edit_permissions, execute)


@safe_tool()
def mcp_jira_delete_dashboard(dashboard_id: str, execute: bool = True) -> dict:
    """Delete a Jira dashboard by ID."""
    return jira_delete_dashboard(dashboard_id, execute)


@safe_tool()
def mcp_jira_list_available_gadgets() -> dict:
    """List all gadgets available to add to a dashboard (returns each gadget's URI + title)."""
    return jira_list_available_gadgets()


@safe_tool()
def mcp_jira_list_dashboard_gadgets(dashboard_id: str) -> dict:
    """List the gadgets currently on a dashboard (with their IDs, columns, rows)."""
    return jira_list_dashboard_gadgets(dashboard_id)


@safe_tool()
def mcp_jira_add_dashboard_gadget(
    dashboard_id: str, uri: str, color: str = "blue",
    column: int | None = None, row: int | None = None, execute: bool = True,
) -> dict:
    """
    Add a gadget (chart) to a dashboard. Get uri from mcp_jira_list_available_gadgets.

    Common gadget URIs:
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:filter-results-gadget/gadgets/filter-results-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:pie-chart-gadget/gadgets/pie-chart-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:two-dimensional-stats-gadget/gadgets/two-dimensional-stats-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:created-vs-resolved-chart-gadget/gadgets/created-vs-resolved-chart-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:assigned-to-me-gadget/gadgets/assigned-to-me-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:sprint-burndown-gadget/gadgets/sprint-burndown-gadget.xml
    color: 'blue' | 'red' | 'yellow' | 'green' | 'transparent' | 'cyan' | 'gray'.
    """
    return jira_add_dashboard_gadget(dashboard_id, uri, color, column, row, execute)


@safe_tool()
def mcp_jira_move_dashboard_gadget(
    dashboard_id: str, gadget_id: str,
    column: int | None = None, row: int | None = None, color: str | None = None,
    execute: bool = True,
) -> dict:
    """Move a gadget to a different column/row on a dashboard, or recolor it."""
    return jira_move_dashboard_gadget(dashboard_id, gadget_id, column, row, color, execute)


@safe_tool()
def mcp_jira_remove_dashboard_gadget(dashboard_id: str, gadget_id: str, execute: bool = True) -> dict:
    """Remove a gadget from a dashboard."""
    return jira_remove_dashboard_gadget(dashboard_id, gadget_id, execute)


@safe_tool()
def mcp_jira_set_dashboard_gadget_prefs(
    dashboard_id: str, gadget_id: str, prefs: dict, execute: bool = True,
) -> dict:
    """
    Configure a gadget's preferences. Pass a flat dict of pref keys/values.

    Example pref sets per common gadget:
      filter-results-gadget: {'filterId': '10001', 'num': '10', 'columnNames': 'issuetype,key,summary,priority,status'}
      pie-chart-gadget: {'filterId': '10001', 'statType': 'priority'}
      two-dimensional-stats-gadget: {'filterId': '10001', 'xstattype': 'priority', 'ystattype': 'status', 'numberToShow': '5'}
      created-vs-resolved-chart-gadget: {'projectOrFilterId': 'filter-10001', 'periodName': 'daily', 'daysprevious': '30', 'cumulative': 'true'}
      assigned-to-me-gadget: {'num': '10'}
    """
    return jira_set_dashboard_gadget_prefs(dashboard_id, gadget_id, prefs, execute)


# ── Lookup helpers (populate gadget configs) ────────────────────────────────

@safe_tool()
def mcp_jira_get_myself() -> dict:
    """Get the currently authenticated Jira user (key, name, email)."""
    return jira_get_myself()


@safe_tool()
def mcp_jira_search_users(query: str, max_results: int = 20) -> dict:
    """Search Jira users by username/email/display name."""
    return jira_search_users(query, max_results)


@safe_tool()
def mcp_jira_list_groups(query: str = "", max_results: int = 50) -> dict:
    """List Jira groups (group picker) for share/edit permissions."""
    return jira_list_groups(query, max_results)


@safe_tool()
def mcp_jira_list_projects() -> dict:
    """List all Jira projects visible to the current user."""
    return jira_list_projects()


@safe_tool()
def mcp_jira_list_statuses() -> dict:
    """List all global issue statuses (id, name, category)."""
    return jira_list_statuses()


@safe_tool()
def mcp_jira_list_priorities() -> dict:
    """List all issue priorities."""
    return jira_list_priorities()


@safe_tool()
def mcp_jira_list_issue_types() -> dict:
    """List all issue types."""
    return jira_list_issue_types()


@safe_tool()
def mcp_jira_list_fields() -> dict:
    """List all Jira fields (system + custom). Returns id, name, custom flag."""
    return jira_list_fields()


# ============================================================================
# Bitbucket Tools (7)
# ============================================================================

@safe_tool()
def mcp_bitbucket_list_prs(repo_slug: str, state: str = "OPEN", limit: int = 50) -> dict:
    """
    List pull requests in a Bitbucket repository.

    States: OPEN, MERGED, DECLINED, SUPERSEDED
    """
    return bitbucket_list_prs(repo_slug, state, limit)


@safe_tool()
def mcp_bitbucket_get_pr(repo_slug: str, pr_id: int) -> dict:
    """Get detailed information about a specific pull request."""
    return bitbucket_get_pr(repo_slug, pr_id)


@safe_tool()
def mcp_bitbucket_pr_diff(repo_slug: str, pr_id: int) -> dict:
    """Get the code diff for a pull request."""
    return bitbucket_pr_diff(repo_slug, pr_id)


@safe_tool()
def mcp_bitbucket_pr_comment(repo_slug: str, pr_id: int, text: str, execute: bool = True) -> dict:
    """Add a comment to a pull request. Set execute=true to actually comment."""
    return bitbucket_pr_comment(repo_slug, pr_id, text, execute)


@safe_tool()
def mcp_bitbucket_approve_pr(repo_slug: str, pr_id: int, execute: bool = True) -> dict:
    """Approve a pull request. Set execute=true to actually approve."""
    return bitbucket_approve_pr(repo_slug, pr_id, execute)


@safe_tool()
def mcp_bitbucket_merge_pr(repo_slug: str, pr_id: int, message: str | None = None, execute: bool = True) -> dict:
    """Merge a pull request. Set execute=true to actually merge."""
    return bitbucket_merge_pr(repo_slug, pr_id, message, execute)


@safe_tool()
def mcp_bitbucket_list_repos(limit: int = 50) -> dict:
    """List all repositories in the workspace/project."""
    return bitbucket_list_repos(limit)


# ============================================================================
# Confluence Tools (6)
# ============================================================================

@safe_tool()
def mcp_confluence_search(query: str, space_key: str | None = None, content_type: str = "page", limit: int = 50) -> dict:
    """
    Search for Confluence pages and content.

    Content types: page, blogpost, attachment
    """
    return confluence_search(query, space_key, content_type, limit)


@safe_tool()
def mcp_confluence_get_page(page_id: str | None = None, space_key: str | None = None, title: str | None = None) -> dict:
    """
    Get a Confluence page by ID or title.

    Provide either page_id OR (space_key + title).
    """
    return confluence_get_page(page_id, space_key, title)


@safe_tool()
def mcp_confluence_create_page(space_key: str, title: str, content: str, parent_id: str | None = None, execute: bool = True) -> dict:
    """Create a new Confluence page. Set execute=true to actually create."""
    return confluence_create_page(space_key, title, content, parent_id, execute)


@safe_tool()
def mcp_confluence_update_page(page_id: str, title: str, content: str, version: int, execute: bool = True) -> dict:
    """Update an existing Confluence page. Requires current version number. Set execute=true to actually update."""
    return confluence_update_page(page_id, title, content, version, execute)


@safe_tool()
def mcp_confluence_add_comment(page_id: str, comment: str, execute: bool = True) -> dict:
    """Add a comment to a Confluence page. Set execute=true to actually comment."""
    return confluence_add_comment(page_id, comment, execute)


@safe_tool()
def mcp_confluence_list_spaces(limit: int = 50) -> dict:
    """List all accessible Confluence spaces."""
    return confluence_list_spaces(limit)


# ============================================================================
# Bamboo Tools (7)
# ============================================================================

@safe_tool()
def mcp_bamboo_list_plans(max_results: int = 50) -> dict:
    """List all build plans in Bamboo."""
    return bamboo_list_plans(max_results)


@safe_tool()
def mcp_bamboo_list_builds(plan_key: str, max_results: int = 50, include_all_states: bool = True) -> dict:
    """
    List builds for a specific build plan.

    Set include_all_states=False to show only successful builds.
    """
    return bamboo_list_builds(plan_key, max_results, include_all_states)


@safe_tool()
def mcp_bamboo_build_status(plan_key: str, build_number: int | None = None) -> dict:
    """
    Get status of a specific build or the latest build for a plan.

    If build_number is not provided, returns the latest build.
    """
    return bamboo_build_status(plan_key, build_number)


@safe_tool()
def mcp_bamboo_get_build(build_key: str) -> dict:
    """
    Get detailed information about a specific build.

    Build key format: PROJ-BUILD-123
    """
    return bamboo_get_build(build_key)


@safe_tool()
def mcp_bamboo_trigger_build(plan_key: str, variables: dict | None = None, execute: bool = True) -> dict:
    """Trigger a new build. Set execute=true to actually trigger."""
    return bamboo_trigger_build(plan_key, variables, execute)


@safe_tool()
def mcp_bamboo_summarize_failures(plan_key: str, limit: int = 10) -> dict:
    """Get a summary of recent build failures with failure reasons and patterns."""
    return bamboo_summarize_failures(plan_key, limit)


@safe_tool()
def mcp_bamboo_get_build_log(build_key: str) -> dict:
    """
    Get the build log output for a specific build.

    Build key format: PROJ-BUILD-123
    """
    return bamboo_get_build_log(build_key)


# ============================================================================
# Main
# ============================================================================

# ============================================================================
# Raw passthrough tools — full API coverage for any endpoint
# ============================================================================

@safe_tool()
def mcp_jira_raw(
    method: str, path: str, params: dict | None = None,
    body: Any = None, agile: bool = False, execute: bool = True,
) -> dict:
    """
    Call ANY Jira REST endpoint not covered by a typed tool.

    method: GET/POST/PUT/DELETE/PATCH.
    path: relative to /rest/api/{version} by default, or /rest/agile/1.0 if agile=true.
    Write methods (POST/PUT/DELETE/PATCH) are dry-run unless execute=true.
    Example: method='GET', path='/user/search', params={'username': 'alice'}
    """
    return jira_raw(method, path, params, body, agile, execute)


@safe_tool()
def mcp_bitbucket_raw(
    method: str, path: str, params: dict | None = None,
    body: Any = None, execute: bool = True,
) -> dict:
    """Call ANY Bitbucket REST endpoint. Write methods dry-run unless execute=true."""
    return bitbucket_raw(method, path, params, body, execute)


@safe_tool()
def mcp_confluence_raw(
    method: str, path: str, params: dict | None = None,
    body: Any = None, execute: bool = True,
) -> dict:
    """Call ANY Confluence REST endpoint (path relative to /rest/api). Write methods dry-run unless execute=true."""
    return confluence_raw(method, path, params, body, execute)


@safe_tool()
def mcp_bamboo_raw(
    method: str, path: str, params: dict | None = None,
    body: Any = None, execute: bool = True,
) -> dict:
    """Call ANY Bamboo REST endpoint (path relative to /rest/api/latest). Write methods dry-run unless execute=true."""
    return bamboo_raw(method, path, params, body, execute)


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Atlassian MCP Server starting (%s)", _mcp_transport)
    logger.info("=" * 70)
    logger.info("110 tools: Jira(86) + Bitbucket(7) + Confluence(6) + Bamboo(7) + raw(4)")
    logger.info("=" * 70)

    if _mcp_transport == "streamable-http":
        logger.info("HTTP endpoint: http://%s:%s/mcp", _mcp_host, _mcp_port)
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
