"""
Atlassian MCP Server — standalone, 28 tools over stdio/HTTP.

Run:
  python server.py                    # stdio (default, for Cursor/Claude Code)
  MCP_TRANSPORT=streamable-http python server.py  # HTTP

Covers: Jira (8), Bitbucket (7), Confluence (6), Bamboo (7)
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
)

_mcp_host = os.getenv("MCP_HOST", "127.0.0.1")
_mcp_port = int(os.getenv("MCP_PORT", "8000"))
_mcp_transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()

mcp = FastMCP(
    "Atlassian",
    instructions="Atlassian automation: Jira, Bitbucket, Confluence, Bamboo — 45 tools for complete SDLC management.",
    host=_mcp_host,
    port=_mcp_port,
    json_response=True,
)


# ============================================================================
# Jira Tools (8)
# ============================================================================

@mcp.tool()
def mcp_jira_search_issues(jql: str, max_results: int = 50) -> dict:
    """Search Jira issues using JQL. Returns matching issues with details like summary, status, assignee."""
    return jira_search_issues(jql, max_results)


@mcp.tool()
def mcp_jira_get_issue(issue_key: str) -> dict:
    """Get detailed information about a specific Jira issue including description, comments, and history."""
    return jira_get_issue(issue_key)


@mcp.tool()
def mcp_jira_create_issue(
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: str | None = None,
    assignee: str | None = None,
    labels: list[str] | None = None,
    execute: bool = False,
) -> dict:
    """Create a new Jira issue. Set execute=true to actually create (dry-run by default)."""
    return jira_create_issue(project_key, summary, description, issue_type, priority, assignee, labels, execute)


@mcp.tool()
def mcp_jira_update_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    execute: bool = False,
) -> dict:
    """Update an existing Jira issue. Set execute=true to actually update (dry-run by default)."""
    return jira_update_issue(issue_key, summary, description, assignee, priority, status, execute)


@mcp.tool()
def mcp_jira_add_comment(issue_key: str, comment: str, execute: bool = False) -> dict:
    """Add a comment to a Jira issue. Set execute=true to actually comment (dry-run by default)."""
    return jira_add_comment(issue_key, comment, execute)


@mcp.tool()
def mcp_jira_create_subtasks(parent_issue_key: str, subtasks: list[dict], execute: bool = False) -> dict:
    """
    Create multiple subtasks under a parent Jira issue. Set execute=true to actually create.

    Each subtask: {"summary": "...", "description": "..."}
    """
    return jira_create_subtasks(parent_issue_key, subtasks, execute)


@mcp.tool()
def mcp_jira_transition_issue(issue_key: str, transition_name: str, execute: bool = False) -> dict:
    """
    Transition a Jira issue to a new status. Set execute=true to actually transition.

    Common transitions: 'In Progress', 'Done', 'To Do', 'Blocked', 'In Review'
    """
    return jira_transition_issue(issue_key, transition_name, execute)


@mcp.tool()
def mcp_jira_get_project_info(project_key: str) -> dict:
    """Get information about a Jira project including available issue types, statuses, and metadata."""
    return jira_get_project_info(project_key)


# ============================================================================
# Jira Agile Tools (17)
# ============================================================================

@mcp.tool()
def mcp_jira_list_boards(name: str | None = None, project_key: str | None = None,
                         board_type: str | None = None, max_results: int = 50, start_at: int = 0) -> dict:
    """
    List all Jira boards. Optionally filter by name, project key, or type.

    Board types: scrum, kanban
    """
    return jira_list_boards(name, project_key, board_type, max_results, start_at)


@mcp.tool()
def mcp_jira_get_board(board_id: int) -> dict:
    """Get a single Jira board by ID."""
    return jira_get_board(board_id)


@mcp.tool()
def mcp_jira_get_board_config(board_id: int) -> dict:
    """Get the configuration of a Jira board including columns, estimation type, and ranking field."""
    return jira_get_board_config(board_id)


@mcp.tool()
def mcp_jira_get_board_issues(board_id: int, jql: str | None = None,
                              max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues from a Jira board. Includes agile fields (sprint, epic, flagged). Optionally filter with JQL."""
    return jira_get_board_issues(board_id, jql, max_results, start_at)


@mcp.tool()
def mcp_jira_get_board_epics(board_id: int, done: bool = False,
                             max_results: int = 50, start_at: int = 0) -> dict:
    """Get all epics from a board. Set done=true to include completed epics."""
    return jira_get_board_epics(board_id, done, max_results, start_at)


@mcp.tool()
def mcp_jira_get_board_backlog(board_id: int, jql: str | None = None,
                               max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues from a board's backlog."""
    return jira_get_board_backlog(board_id, jql, max_results, start_at)


@mcp.tool()
def mcp_jira_get_board_sprints(board_id: int, state: str | None = None,
                               max_results: int = 50, start_at: int = 0) -> dict:
    """
    Get all sprints from a board.

    States: future, active, closed (comma-separated for multiple, e.g. 'active,closed')
    """
    return jira_get_board_sprints(board_id, state, max_results, start_at)


@mcp.tool()
def mcp_jira_get_sprint(sprint_id: int) -> dict:
    """Get a single sprint by ID including name, state, dates, and goal."""
    return jira_get_sprint(sprint_id)


@mcp.tool()
def mcp_jira_create_sprint(board_id: int, name: str, start_date: str | None = None,
                           end_date: str | None = None, goal: str | None = None,
                           execute: bool = False) -> dict:
    """
    Create a future sprint on a board. Set execute=true to actually create.

    Dates in ISO 8601 format (e.g. '2024-01-15T09:00:00.000Z').
    """
    return jira_create_sprint(board_id, name, start_date, end_date, goal, execute)


@mcp.tool()
def mcp_jira_update_sprint(sprint_id: int, name: str | None = None, state: str | None = None,
                           start_date: str | None = None, end_date: str | None = None,
                           goal: str | None = None, execute: bool = False) -> dict:
    """
    Update a sprint. Set execute=true to actually update.

    Set state='active' to start a sprint (requires start/end dates).
    Set state='closed' to complete an active sprint.
    """
    return jira_update_sprint(sprint_id, name, state, start_date, end_date, goal, execute)


@mcp.tool()
def mcp_jira_get_sprint_issues(sprint_id: int, jql: str | None = None,
                               max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues in a sprint. Ordered by rank by default."""
    return jira_get_sprint_issues(sprint_id, jql, max_results, start_at)


@mcp.tool()
def mcp_jira_move_issues_to_sprint(sprint_id: int, issue_keys: list[str], execute: bool = False) -> dict:
    """Move issues to a sprint. Maximum 50 issues. Set execute=true to actually move."""
    return jira_move_issues_to_sprint(sprint_id, issue_keys, execute)


@mcp.tool()
def mcp_jira_move_issues_to_backlog(issue_keys: list[str], execute: bool = False) -> dict:
    """Move issues to the backlog (removes from any sprint). Maximum 50 issues. Set execute=true to actually move."""
    return jira_move_issues_to_backlog(issue_keys, execute)


@mcp.tool()
def mcp_jira_get_epic(epic_id_or_key: str) -> dict:
    """Get an epic by ID or issue key."""
    return jira_get_epic(epic_id_or_key)


@mcp.tool()
def mcp_jira_get_epic_issues(epic_id_or_key: str, jql: str | None = None,
                             max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues belonging to an epic. Ordered by rank by default."""
    return jira_get_epic_issues(epic_id_or_key, jql, max_results, start_at)


@mcp.tool()
def mcp_jira_move_issues_to_epic(epic_id_or_key: str, issue_keys: list[str], execute: bool = False) -> dict:
    """Move issues to an epic. Maximum 50 issues. Set execute=true to actually move."""
    return jira_move_issues_to_epic(epic_id_or_key, issue_keys, execute)


@mcp.tool()
def mcp_jira_rank_issues(issue_keys: list[str], rank_before_issue: str | None = None,
                         rank_after_issue: str | None = None, execute: bool = False) -> dict:
    """
    Rank (reorder) issues on a board. Maximum 50 issues. Set execute=true to actually rank.

    Specify either rank_before_issue or rank_after_issue to position the issues.
    """
    return jira_rank_issues(issue_keys, rank_before_issue, rank_after_issue, execute)


# ============================================================================
# Bitbucket Tools (7)
# ============================================================================

@mcp.tool()
def mcp_bitbucket_list_prs(repo_slug: str, state: str = "OPEN", limit: int = 50) -> dict:
    """
    List pull requests in a Bitbucket repository.

    States: OPEN, MERGED, DECLINED, SUPERSEDED
    """
    return bitbucket_list_prs(repo_slug, state, limit)


@mcp.tool()
def mcp_bitbucket_get_pr(repo_slug: str, pr_id: int) -> dict:
    """Get detailed information about a specific pull request."""
    return bitbucket_get_pr(repo_slug, pr_id)


@mcp.tool()
def mcp_bitbucket_pr_diff(repo_slug: str, pr_id: int) -> dict:
    """Get the code diff for a pull request."""
    return bitbucket_pr_diff(repo_slug, pr_id)


@mcp.tool()
def mcp_bitbucket_pr_comment(repo_slug: str, pr_id: int, text: str, execute: bool = False) -> dict:
    """Add a comment to a pull request. Set execute=true to actually comment."""
    return bitbucket_pr_comment(repo_slug, pr_id, text, execute)


@mcp.tool()
def mcp_bitbucket_approve_pr(repo_slug: str, pr_id: int, execute: bool = False) -> dict:
    """Approve a pull request. Set execute=true to actually approve."""
    return bitbucket_approve_pr(repo_slug, pr_id, execute)


@mcp.tool()
def mcp_bitbucket_merge_pr(repo_slug: str, pr_id: int, message: str | None = None, execute: bool = False) -> dict:
    """Merge a pull request. Set execute=true to actually merge."""
    return bitbucket_merge_pr(repo_slug, pr_id, message, execute)


@mcp.tool()
def mcp_bitbucket_list_repos(limit: int = 50) -> dict:
    """List all repositories in the workspace/project."""
    return bitbucket_list_repos(limit)


# ============================================================================
# Confluence Tools (6)
# ============================================================================

@mcp.tool()
def mcp_confluence_search(query: str, space_key: str | None = None, content_type: str = "page", limit: int = 50) -> dict:
    """
    Search for Confluence pages and content.

    Content types: page, blogpost, attachment
    """
    return confluence_search(query, space_key, content_type, limit)


@mcp.tool()
def mcp_confluence_get_page(page_id: str | None = None, space_key: str | None = None, title: str | None = None) -> dict:
    """
    Get a Confluence page by ID or title.

    Provide either page_id OR (space_key + title).
    """
    return confluence_get_page(page_id, space_key, title)


@mcp.tool()
def mcp_confluence_create_page(space_key: str, title: str, content: str, parent_id: str | None = None, execute: bool = False) -> dict:
    """Create a new Confluence page. Set execute=true to actually create."""
    return confluence_create_page(space_key, title, content, parent_id, execute)


@mcp.tool()
def mcp_confluence_update_page(page_id: str, title: str, content: str, version: int, execute: bool = False) -> dict:
    """Update an existing Confluence page. Requires current version number. Set execute=true to actually update."""
    return confluence_update_page(page_id, title, content, version, execute)


@mcp.tool()
def mcp_confluence_add_comment(page_id: str, comment: str, execute: bool = False) -> dict:
    """Add a comment to a Confluence page. Set execute=true to actually comment."""
    return confluence_add_comment(page_id, comment, execute)


@mcp.tool()
def mcp_confluence_list_spaces(limit: int = 50) -> dict:
    """List all accessible Confluence spaces."""
    return confluence_list_spaces(limit)


# ============================================================================
# Bamboo Tools (7)
# ============================================================================

@mcp.tool()
def mcp_bamboo_list_plans(max_results: int = 50) -> dict:
    """List all build plans in Bamboo."""
    return bamboo_list_plans(max_results)


@mcp.tool()
def mcp_bamboo_list_builds(plan_key: str, max_results: int = 50, include_all_states: bool = True) -> dict:
    """
    List builds for a specific build plan.

    Set include_all_states=False to show only successful builds.
    """
    return bamboo_list_builds(plan_key, max_results, include_all_states)


@mcp.tool()
def mcp_bamboo_build_status(plan_key: str, build_number: int | None = None) -> dict:
    """
    Get status of a specific build or the latest build for a plan.

    If build_number is not provided, returns the latest build.
    """
    return bamboo_build_status(plan_key, build_number)


@mcp.tool()
def mcp_bamboo_get_build(build_key: str) -> dict:
    """
    Get detailed information about a specific build.

    Build key format: PROJ-BUILD-123
    """
    return bamboo_get_build(build_key)


@mcp.tool()
def mcp_bamboo_trigger_build(plan_key: str, variables: dict | None = None, execute: bool = False) -> dict:
    """Trigger a new build. Set execute=true to actually trigger."""
    return bamboo_trigger_build(plan_key, variables, execute)


@mcp.tool()
def mcp_bamboo_summarize_failures(plan_key: str, limit: int = 10) -> dict:
    """Get a summary of recent build failures with failure reasons and patterns."""
    return bamboo_summarize_failures(plan_key, limit)


@mcp.tool()
def mcp_bamboo_get_build_log(build_key: str) -> dict:
    """
    Get the build log output for a specific build.

    Build key format: PROJ-BUILD-123
    """
    return bamboo_get_build_log(build_key)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Atlassian MCP Server starting (%s)", _mcp_transport)
    logger.info("=" * 70)
    logger.info("45 tools: Jira(8) + Jira Agile(17) + Bitbucket(7) + Confluence(6) + Bamboo(7)")
    logger.info("=" * 70)

    if _mcp_transport == "streamable-http":
        logger.info("HTTP endpoint: http://%s:%s/mcp", _mcp_host, _mcp_port)
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
