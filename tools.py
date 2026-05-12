"""Atlassian tool handlers: Jira, Bitbucket, Confluence, Bamboo.

Standalone — reads credentials from .env via config.py, no database needed.
"""
import json
import os
from typing import Any

from config import (
    get_logger,
    MOCK_MODE,
    is_execute_allowed,
    ALLOWLIST_JIRA_PROJECT_KEYS,
    ALLOWLIST_BITBUCKET_REPOS,
    ALLOWLIST_CONFLUENCE_SPACE_KEYS,
    ALLOWLIST_BAMBOO_PLANS,
    BITBUCKET_WORKSPACE,
)
from clients import (
    jira_client, jira_agile_client, jira_dashboards_client,
    bitbucket_client, confluence_client, confluence_experimental_client, bamboo_client,
    is_bitbucket_server,
)
from audit import audit_log

logger = get_logger("tools")


# ── Allowlist guards ─────────────────────────────────────────────────────────

def _allow_project(project_key: str) -> None:
    if not ALLOWLIST_JIRA_PROJECT_KEYS:
        return
    key = (project_key.split("-")[0] or project_key).upper()
    if key not in [k.upper() for k in ALLOWLIST_JIRA_PROJECT_KEYS]:
        raise ValueError(f"Project {project_key} is not in allowlist (ALLOWLIST_JIRA_PROJECT_KEYS).")


def _allow_repo(repo_slug: str) -> None:
    if not ALLOWLIST_BITBUCKET_REPOS:
        return
    if repo_slug.lower() not in [r.lower() for r in ALLOWLIST_BITBUCKET_REPOS]:
        raise ValueError(f"Repo {repo_slug} is not in allowlist (ALLOWLIST_BITBUCKET_REPOS).")


def _allow_space(space_key: str) -> None:
    if not ALLOWLIST_CONFLUENCE_SPACE_KEYS:
        return
    if space_key.upper() not in [k.upper() for k in ALLOWLIST_CONFLUENCE_SPACE_KEYS]:
        raise ValueError(f"Space {space_key} is not in allowlist (ALLOWLIST_CONFLUENCE_SPACE_KEYS).")


def _allow_plan(plan_key: str) -> None:
    if not ALLOWLIST_BAMBOO_PLANS:
        return
    if plan_key.upper() not in [k.upper() for k in ALLOWLIST_BAMBOO_PLANS]:
        raise ValueError(f"Plan {plan_key} is not in allowlist (ALLOWLIST_BAMBOO_PLANS).")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_bitbucket_project_key(repo_slug: str) -> str:
    """Get the project key for a Bitbucket Server/DC repo."""
    if not is_bitbucket_server():
        return BITBUCKET_WORKSPACE

    client = bitbucket_client()
    if not client:
        raise ValueError("Bitbucket not configured.")
    with client as c:
        r = c.get("/repos", params={"name": repo_slug})
        r.raise_for_status()
        for repo in r.json().get("values", []):
            if repo.get("slug") == repo_slug:
                return repo.get("project", {}).get("key", "")
        raise ValueError(f"Repository '{repo_slug}' not found in Bitbucket Server")


# ============================================================================
# Jira Tools
# ============================================================================

def jira_search_issues(jql: str, max_results: int = 50) -> dict:
    """Search Jira issues using JQL."""
    if MOCK_MODE:
        return {"issues": [{"key": "DEMO-1", "fields": {"summary": "Sample issue", "status": {"name": "Open"}}}], "total": 1}
    client = jira_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.get("/search", params={"jql": jql, "maxResults": max_results})
        r.raise_for_status()
        data = r.json()
    issues = data.get("issues", [])
    if ALLOWLIST_JIRA_PROJECT_KEYS:
        allowed = {k.upper() for k in ALLOWLIST_JIRA_PROJECT_KEYS}
        issues = [i for i in issues if (i.get("key") or "").split("-")[0].upper() in allowed]
        data["issues"] = issues
        data["total"] = len(issues)
    audit_log("jira_search_issues", {"jql": jql, "maxResults": max_results}, "success")
    return data


def jira_get_issue(issue_key: str) -> dict:
    """Get detailed information about a specific Jira issue."""
    _allow_project(issue_key)
    if MOCK_MODE:
        return {"key": issue_key, "fields": {"summary": "Sample issue", "status": {"name": "Open"}, "description": "Mock description"}}
    client = jira_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.get(f"/issue/{issue_key}")
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_issue", {"issue_key": issue_key}, "success")
    return data


def jira_create_issue(
    project_key: str, summary: str, description: str = "",
    issue_type: str = "Task", priority: str | None = None,
    assignee: str | None = None, labels: list[str] | None = None,
    execute: bool = True,
) -> dict:
    """Create a new Jira issue."""
    _allow_project(project_key)
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN. Set EXECUTE and execute: true to create."}
    if not execute:
        audit_log("jira_create_issue", {"project": project_key, "summary": summary}, "success")
        return {"dryRun": True, "wouldCreate": {"project": project_key, "summary": summary, "issueType": issue_type}}
    if MOCK_MODE:
        return {"key": f"{project_key}-999", "created": True}

    client = jira_client()
    if not client:
        raise ValueError("Jira not configured.")
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]}
    if priority:
        fields["priority"] = {"name": priority}
    if assignee:
        fields["assignee"] = {"accountId": assignee}
    if labels:
        fields["labels"] = labels

    with client as c:
        r = c.post("/issue", json={"fields": fields})
        r.raise_for_status()
        data = r.json()
    audit_log("jira_create_issue", {"project": project_key, "summary": summary}, "success")
    return {"key": data.get("key"), "created": True}


def jira_update_issue(
    issue_key: str, summary: str | None = None, description: str | None = None,
    assignee: str | None = None, priority: str | None = None, status: str | None = None,
    execute: bool = True,
) -> dict:
    """Update an existing Jira issue."""
    _allow_project(issue_key)
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log("jira_update_issue", {"issue_key": issue_key}, "success")
        return {"dryRun": True, "wouldUpdate": issue_key}
    if MOCK_MODE:
        return {"key": issue_key, "updated": True}

    client = jira_client()
    if not client:
        raise ValueError("Jira not configured.")
    fields: dict[str, Any] = {}
    if summary:
        fields["summary"] = summary
    if description:
        fields["description"] = {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]}
    if assignee:
        fields["assignee"] = {"accountId": assignee}
    if priority:
        fields["priority"] = {"name": priority}

    with client as c:
        if fields:
            r = c.put(f"/issue/{issue_key}", json={"fields": fields})
            r.raise_for_status()
        if status:
            # Find matching transition
            tr = c.get(f"/issue/{issue_key}/transitions")
            tr.raise_for_status()
            transitions = tr.json().get("transitions", [])
            match = next((t for t in transitions if t["name"].lower() == status.lower()), None)
            if match:
                c.post(f"/issue/{issue_key}/transitions", json={"transition": {"id": match["id"]}}).raise_for_status()
            else:
                return {"key": issue_key, "updated": True, "warning": f"Transition '{status}' not found"}

    audit_log("jira_update_issue", {"issue_key": issue_key}, "success")
    return {"key": issue_key, "updated": True}


def jira_add_comment(issue_key: str, comment: str, execute: bool = True) -> dict:
    """Add a comment to a Jira issue."""
    _allow_project(issue_key)
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("jira_add_comment", {"issueKey": issue_key}, "success")
        return {"dryRun": True}
    if MOCK_MODE:
        return {"created": True}

    client = jira_client()
    if not client:
        raise ValueError("Jira not configured.")
    payload = {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}]}}
    with client as c:
        c.post(f"/issue/{issue_key}/comment", json=payload).raise_for_status()
    audit_log("jira_add_comment", {"issueKey": issue_key}, "success")
    return {"created": True}


def jira_create_subtasks(parent_issue_key: str, subtasks: list[dict], execute: bool = True) -> dict:
    """Create multiple subtasks under a parent Jira issue."""
    _allow_project(parent_issue_key)
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log("jira_create_subtasks", {"parentKey": parent_issue_key}, "success")
        return {"dryRun": True, "wouldCreate": len(subtasks)}
    if MOCK_MODE:
        return {"created": len(subtasks), "keys": [f"{parent_issue_key}-{i+1}" for i in range(len(subtasks))]}

    client = jira_client()
    if not client:
        raise ValueError("Jira not configured.")
    proj = parent_issue_key.split("-")[0]
    keys = []
    with client as c:
        for st in subtasks:
            body: dict[str, Any] = {
                "fields": {
                    "project": {"key": proj},
                    "parent": {"key": parent_issue_key},
                    "summary": st.get("summary", ""),
                    "issuetype": {"name": "Sub-task"},
                }
            }
            if st.get("description"):
                body["fields"]["description"] = {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": st["description"]}]}]}
            r = c.post("/issue", json=body)
            r.raise_for_status()
            keys.append(r.json()["key"])
    audit_log("jira_create_subtasks", {"parentKey": parent_issue_key}, "success")
    return {"created": len(keys), "keys": keys}


def jira_transition_issue(issue_key: str, transition_name: str, execute: bool = True) -> dict:
    """Transition a Jira issue to a new status."""
    _allow_project(issue_key)
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("jira_transition_issue", {"issueKey": issue_key}, "success")
        return {"dryRun": True}
    if MOCK_MODE:
        return {"done": True}

    client = jira_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        tr = c.get(f"/issue/{issue_key}/transitions")
        tr.raise_for_status()
        transitions = tr.json().get("transitions", [])
        match = next((t for t in transitions if t["name"].lower() == transition_name.lower()), None)
        if not match:
            available = [t["name"] for t in transitions]
            raise ValueError(f"Transition '{transition_name}' not found. Available: {available}")
        c.post(f"/issue/{issue_key}/transitions", json={"transition": {"id": match["id"]}}).raise_for_status()
    audit_log("jira_transition_issue", {"issueKey": issue_key}, "success")
    return {"done": True}


def jira_get_project_info(project_key: str) -> dict:
    """Get information about a Jira project."""
    _allow_project(project_key)
    if MOCK_MODE:
        return {"key": project_key, "name": "Demo Project", "issueTypes": [{"name": "Task"}, {"name": "Bug"}]}
    client = jira_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.get(f"/project/{project_key}")
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_project_info", {"project_key": project_key}, "success")
    return data


# ============================================================================
# Jira Agile Tools (Board, Sprint, Epic, Backlog)
# ============================================================================

def jira_list_boards(name: str | None = None, project_key: str | None = None,
                     board_type: str | None = None, max_results: int = 50, start_at: int = 0) -> dict:
    """List all Jira boards. Optionally filter by name, project, or type (scrum/kanban)."""
    if MOCK_MODE:
        return {"values": [{"id": 1, "name": "Sample Board", "type": "scrum"}], "maxResults": 1, "total": 1}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    params: dict[str, Any] = {"maxResults": max_results, "startAt": start_at}
    if name:
        params["name"] = name
    if project_key:
        if ALLOWLIST_JIRA_PROJECT_KEYS:
            _allow_project(project_key)
        params["projectKeyOrId"] = project_key
    if board_type:
        params["type"] = board_type
    with client as c:
        r = c.get("/board", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_list_boards", params, "success")
    return data


def jira_get_board(board_id: int) -> dict:
    """Get a single Jira board by ID."""
    if MOCK_MODE:
        return {"id": board_id, "name": "Sample Board", "type": "scrum"}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.get(f"/board/{board_id}")
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_board", {"board_id": board_id}, "success")
    return data


def jira_get_board_config(board_id: int) -> dict:
    """Get the configuration of a Jira board (columns, estimation, ranking)."""
    if MOCK_MODE:
        return {"id": board_id, "name": "Sample Board", "columnConfig": {"columns": []}}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.get(f"/board/{board_id}/configuration")
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_board_config", {"board_id": board_id}, "success")
    return data


def jira_get_board_issues(board_id: int, jql: str | None = None,
                          max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues from a Jira board. Optionally filter with JQL."""
    if MOCK_MODE:
        return {"issues": [{"key": "DEMO-1", "fields": {"summary": "Sample"}}], "total": 1}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    params: dict[str, Any] = {"maxResults": max_results, "startAt": start_at}
    if jql:
        params["jql"] = jql
    with client as c:
        r = c.get(f"/board/{board_id}/issue", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_board_issues", {"board_id": board_id}, "success")
    return data


def jira_get_board_epics(board_id: int, done: bool = False,
                         max_results: int = 50, start_at: int = 0) -> dict:
    """Get all epics from a board."""
    if MOCK_MODE:
        return {"values": [{"id": 1, "name": "Sample Epic", "done": False}], "maxResults": 1}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    params: dict[str, Any] = {"maxResults": max_results, "startAt": start_at, "done": str(done).lower()}
    with client as c:
        r = c.get(f"/board/{board_id}/epic", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_board_epics", {"board_id": board_id}, "success")
    return data


def jira_get_board_backlog(board_id: int, jql: str | None = None,
                           max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues from a board's backlog."""
    if MOCK_MODE:
        return {"issues": [{"key": "DEMO-2", "fields": {"summary": "Backlog item"}}], "total": 1}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    params: dict[str, Any] = {"maxResults": max_results, "startAt": start_at}
    if jql:
        params["jql"] = jql
    with client as c:
        r = c.get(f"/board/{board_id}/backlog", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_board_backlog", {"board_id": board_id}, "success")
    return data


def jira_get_board_sprints(board_id: int, state: str | None = None,
                           max_results: int = 50, start_at: int = 0) -> dict:
    """Get all sprints from a board. Optionally filter by state (future, active, closed)."""
    if MOCK_MODE:
        return {"values": [{"id": 1, "name": "Sprint 1", "state": "active"}], "maxResults": 1}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    params: dict[str, Any] = {"maxResults": max_results, "startAt": start_at}
    if state:
        params["state"] = state
    with client as c:
        r = c.get(f"/board/{board_id}/sprint", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_board_sprints", {"board_id": board_id, "state": state}, "success")
    return data


def jira_get_sprint(sprint_id: int) -> dict:
    """Get a single sprint by ID."""
    if MOCK_MODE:
        return {"id": sprint_id, "name": "Sprint 1", "state": "active", "goal": "Ship features"}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.get(f"/sprint/{sprint_id}")
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_sprint", {"sprint_id": sprint_id}, "success")
    return data


def jira_create_sprint(board_id: int, name: str, start_date: str | None = None,
                       end_date: str | None = None, goal: str | None = None,
                       execute: bool = True) -> dict:
    """Create a future sprint on a board."""
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log("jira_create_sprint", {"board_id": board_id, "name": name}, "success")
        return {"dryRun": True, "wouldCreate": {"name": name, "originBoardId": board_id}}
    if MOCK_MODE:
        return {"id": 999, "name": name, "state": "future", "created": True}

    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    payload: dict[str, Any] = {"name": name, "originBoardId": board_id}
    if start_date:
        payload["startDate"] = start_date
    if end_date:
        payload["endDate"] = end_date
    if goal:
        payload["goal"] = goal
    with client as c:
        r = c.post("/sprint", json=payload)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_create_sprint", {"board_id": board_id, "name": name}, "success")
    return data


def jira_update_sprint(sprint_id: int, name: str | None = None, state: str | None = None,
                       start_date: str | None = None, end_date: str | None = None,
                       goal: str | None = None, execute: bool = True) -> dict:
    """Update a sprint (name, state, dates, goal). Use state='active' to start, 'closed' to complete."""
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log("jira_update_sprint", {"sprint_id": sprint_id}, "success")
        return {"dryRun": True, "wouldUpdate": sprint_id}
    if MOCK_MODE:
        return {"id": sprint_id, "updated": True}

    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    payload: dict[str, Any] = {}
    if name:
        payload["name"] = name
    if state:
        payload["state"] = state
    if start_date:
        payload["startDate"] = start_date
    if end_date:
        payload["endDate"] = end_date
    if goal is not None:
        payload["goal"] = goal
    with client as c:
        r = c.post(f"/sprint/{sprint_id}", json=payload)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_update_sprint", {"sprint_id": sprint_id}, "success")
    return data


def jira_get_sprint_issues(sprint_id: int, jql: str | None = None,
                           max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues in a sprint."""
    if MOCK_MODE:
        return {"issues": [{"key": "DEMO-1", "fields": {"summary": "Sprint item"}}], "total": 1}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    params: dict[str, Any] = {"maxResults": max_results, "startAt": start_at}
    if jql:
        params["jql"] = jql
    with client as c:
        r = c.get(f"/sprint/{sprint_id}/issue", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_sprint_issues", {"sprint_id": sprint_id}, "success")
    return data


def jira_move_issues_to_sprint(sprint_id: int, issue_keys: list[str], execute: bool = True) -> dict:
    """Move issues to a sprint. Maximum 50 issues per operation."""
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log("jira_move_issues_to_sprint", {"sprint_id": sprint_id, "count": len(issue_keys)}, "success")
        return {"dryRun": True, "wouldMove": issue_keys}
    if MOCK_MODE:
        return {"moved": len(issue_keys)}

    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.post(f"/sprint/{sprint_id}/issue", json={"issues": issue_keys})
        r.raise_for_status()
    audit_log("jira_move_issues_to_sprint", {"sprint_id": sprint_id, "count": len(issue_keys)}, "success")
    return {"moved": len(issue_keys)}


def jira_move_issues_to_backlog(issue_keys: list[str], execute: bool = True) -> dict:
    """Move issues to the backlog (removes them from any sprint). Maximum 50 issues."""
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log("jira_move_issues_to_backlog", {"count": len(issue_keys)}, "success")
        return {"dryRun": True, "wouldMove": issue_keys}
    if MOCK_MODE:
        return {"moved": len(issue_keys)}

    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.post("/backlog/issue", json={"issues": issue_keys})
        r.raise_for_status()
    audit_log("jira_move_issues_to_backlog", {"count": len(issue_keys)}, "success")
    return {"moved": len(issue_keys)}


def jira_get_epic(epic_id_or_key: str) -> dict:
    """Get an epic by ID or issue key."""
    if MOCK_MODE:
        return {"id": 1, "key": epic_id_or_key, "name": "Sample Epic", "done": False}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.get(f"/epic/{epic_id_or_key}")
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_epic", {"epic_id_or_key": epic_id_or_key}, "success")
    return data


def jira_get_epic_issues(epic_id_or_key: str, jql: str | None = None,
                         max_results: int = 50, start_at: int = 0) -> dict:
    """Get all issues belonging to an epic."""
    if MOCK_MODE:
        return {"issues": [{"key": "DEMO-3", "fields": {"summary": "Epic child"}}], "total": 1}
    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    params: dict[str, Any] = {"maxResults": max_results, "startAt": start_at}
    if jql:
        params["jql"] = jql
    with client as c:
        r = c.get(f"/epic/{epic_id_or_key}/issue", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("jira_get_epic_issues", {"epic_id_or_key": epic_id_or_key}, "success")
    return data


def jira_move_issues_to_epic(epic_id_or_key: str, issue_keys: list[str], execute: bool = True) -> dict:
    """Move issues to an epic. Maximum 50 issues per operation."""
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log("jira_move_issues_to_epic", {"epic": epic_id_or_key, "count": len(issue_keys)}, "success")
        return {"dryRun": True, "wouldMove": issue_keys}
    if MOCK_MODE:
        return {"moved": len(issue_keys)}

    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    with client as c:
        r = c.post(f"/epic/{epic_id_or_key}/issue", json={"issues": issue_keys})
        r.raise_for_status()
    audit_log("jira_move_issues_to_epic", {"epic": epic_id_or_key, "count": len(issue_keys)}, "success")
    return {"moved": len(issue_keys)}


def jira_rank_issues(issue_keys: list[str], rank_before_issue: str | None = None,
                     rank_after_issue: str | None = None, execute: bool = True) -> dict:
    """Rank (reorder) issues. Specify either rank_before_issue or rank_after_issue."""
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log("jira_rank_issues", {"count": len(issue_keys)}, "success")
        return {"dryRun": True, "wouldRank": issue_keys}
    if MOCK_MODE:
        return {"ranked": len(issue_keys)}

    client = jira_agile_client()
    if not client:
        raise ValueError("Jira not configured.")
    payload: dict[str, Any] = {"issues": issue_keys}
    if rank_before_issue:
        payload["rankBeforeIssue"] = rank_before_issue
    if rank_after_issue:
        payload["rankAfterIssue"] = rank_after_issue
    with client as c:
        r = c.put("/issue/rank", json=payload)
        r.raise_for_status()
    audit_log("jira_rank_issues", {"count": len(issue_keys)}, "success")
    return {"ranked": len(issue_keys)}


# ============================================================================
# Jira Extended Tools (attachments, worklogs, watchers, links, versions,
# components, archive, filters, bulk)
# ============================================================================

def _adf(text: str) -> dict:
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _require_jira() -> Any:
    c = jira_client()
    if not c:
        raise ValueError("Jira not configured.")
    return c


def _require_jira_agile() -> Any:
    c = jira_agile_client()
    if not c:
        raise ValueError("Jira not configured.")
    return c


def _dry(name: str, params: dict, execute: bool) -> dict | None:
    if execute and not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
    if not execute:
        audit_log(name, params, "success")
        return {"dryRun": True, **params}
    return None


# ── Attachments ──────────────────────────────────────────────────────────────

def jira_get_attachment(attachment_id: str) -> dict:
    """Get attachment metadata by ID."""
    if MOCK_MODE:
        return {"id": attachment_id}
    with _require_jira() as c:
        r = c.get(f"/attachment/{attachment_id}")
        r.raise_for_status()
        return r.json()


def jira_delete_attachment(attachment_id: str, execute: bool = True) -> dict:
    """Delete an attachment by ID."""
    d = _dry("jira_delete_attachment", {"attachmentId": attachment_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira() as c:
        c.delete(f"/attachment/{attachment_id}").raise_for_status()
    audit_log("jira_delete_attachment", {"attachmentId": attachment_id}, "success")
    return {"deleted": True}


def jira_get_attachment_meta() -> dict:
    """Get Jira attachment capabilities (enabled, max upload size)."""
    if MOCK_MODE:
        return {"enabled": True}
    with _require_jira() as c:
        r = c.get("/attachment/meta")
        r.raise_for_status()
        return r.json()


# ── Worklogs ─────────────────────────────────────────────────────────────────

def jira_get_issue_worklogs(issue_key: str) -> dict:
    """Get all worklogs for an issue."""
    _allow_project(issue_key)
    if MOCK_MODE:
        return {"worklogs": []}
    with _require_jira() as c:
        r = c.get(f"/issue/{issue_key}/worklog")
        r.raise_for_status()
        return r.json()


def jira_add_issue_worklog(
    issue_key: str, time_spent: str, comment: str = "", started: str | None = None,
    execute: bool = True,
) -> dict:
    """Add a worklog entry (time_spent like '3h 20m', started ISO-8601)."""
    _allow_project(issue_key)
    d = _dry("jira_add_issue_worklog", {"issueKey": issue_key, "timeSpent": time_spent}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"created": True}
    payload: dict[str, Any] = {"timeSpent": time_spent}
    if comment:
        payload["comment"] = _adf(comment)
    if started:
        payload["started"] = started
    with _require_jira() as c:
        r = c.post(f"/issue/{issue_key}/worklog", json=payload)
        r.raise_for_status()
    audit_log("jira_add_issue_worklog", {"issueKey": issue_key}, "success")
    return {"created": True}


def jira_update_issue_worklog(
    issue_key: str, worklog_id: str, time_spent: str | None = None,
    comment: str | None = None, execute: bool = True,
) -> dict:
    """Update a worklog entry."""
    _allow_project(issue_key)
    d = _dry("jira_update_issue_worklog", {"issueKey": issue_key, "worklogId": worklog_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"updated": True}
    payload: dict[str, Any] = {}
    if time_spent:
        payload["timeSpent"] = time_spent
    if comment:
        payload["comment"] = _adf(comment)
    with _require_jira() as c:
        c.put(f"/issue/{issue_key}/worklog/{worklog_id}", json=payload).raise_for_status()
    audit_log("jira_update_issue_worklog", {"issueKey": issue_key, "worklogId": worklog_id}, "success")
    return {"updated": True}


def jira_delete_issue_worklog(issue_key: str, worklog_id: str, execute: bool = True) -> dict:
    """Delete a worklog entry."""
    _allow_project(issue_key)
    d = _dry("jira_delete_issue_worklog", {"issueKey": issue_key, "worklogId": worklog_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira() as c:
        c.delete(f"/issue/{issue_key}/worklog/{worklog_id}").raise_for_status()
    audit_log("jira_delete_issue_worklog", {"issueKey": issue_key, "worklogId": worklog_id}, "success")
    return {"deleted": True}


# ── Watchers ─────────────────────────────────────────────────────────────────

def jira_get_issue_watchers(issue_key: str) -> dict:
    """Get watchers for an issue."""
    _allow_project(issue_key)
    if MOCK_MODE:
        return {"watchers": []}
    with _require_jira() as c:
        r = c.get(f"/issue/{issue_key}/watchers")
        r.raise_for_status()
        return r.json()


def jira_add_issue_watcher(issue_key: str, username: str, execute: bool = True) -> dict:
    """Add a watcher to an issue (username or accountId depending on Jira flavor)."""
    _allow_project(issue_key)
    d = _dry("jira_add_issue_watcher", {"issueKey": issue_key, "username": username}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"added": True}
    with _require_jira() as c:
        c.post(f"/issue/{issue_key}/watchers", json=username).raise_for_status()
    audit_log("jira_add_issue_watcher", {"issueKey": issue_key}, "success")
    return {"added": True}


def jira_remove_issue_watcher(issue_key: str, username: str, execute: bool = True) -> dict:
    """Remove a watcher from an issue."""
    _allow_project(issue_key)
    d = _dry("jira_remove_issue_watcher", {"issueKey": issue_key, "username": username}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"removed": True}
    with _require_jira() as c:
        c.delete(f"/issue/{issue_key}/watchers", params={"username": username}).raise_for_status()
    audit_log("jira_remove_issue_watcher", {"issueKey": issue_key}, "success")
    return {"removed": True}


# ── Issue Links ──────────────────────────────────────────────────────────────

def jira_get_issue_link_types() -> dict:
    """List available issue link types."""
    if MOCK_MODE:
        return {"issueLinkTypes": []}
    with _require_jira() as c:
        r = c.get("/issueLinkType")
        r.raise_for_status()
        return r.json()


def jira_create_issue_link(
    link_type: str, inward_issue: str, outward_issue: str,
    comment: str | None = None, execute: bool = True,
) -> dict:
    """Link two issues (e.g. 'Blocks', 'Relates')."""
    _allow_project(inward_issue)
    _allow_project(outward_issue)
    d = _dry("jira_create_issue_link", {"linkType": link_type, "inward": inward_issue, "outward": outward_issue}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"created": True}
    payload: dict[str, Any] = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_issue},
        "outwardIssue": {"key": outward_issue},
    }
    if comment:
        payload["comment"] = {"body": _adf(comment)}
    with _require_jira() as c:
        c.post("/issueLink", json=payload).raise_for_status()
    audit_log("jira_create_issue_link", {"inward": inward_issue, "outward": outward_issue}, "success")
    return {"created": True}


def jira_get_issue_link(link_id: str) -> dict:
    """Get an issue link by ID."""
    if MOCK_MODE:
        return {"id": link_id}
    with _require_jira() as c:
        r = c.get(f"/issueLink/{link_id}")
        r.raise_for_status()
        return r.json()


def jira_delete_issue_link(link_id: str, execute: bool = True) -> dict:
    """Delete an issue link by ID."""
    d = _dry("jira_delete_issue_link", {"linkId": link_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira() as c:
        c.delete(f"/issueLink/{link_id}").raise_for_status()
    audit_log("jira_delete_issue_link", {"linkId": link_id}, "success")
    return {"deleted": True}


# ── Remote Links ─────────────────────────────────────────────────────────────

def jira_get_issue_remote_links(issue_key: str) -> dict:
    """Get all remote links on an issue."""
    _allow_project(issue_key)
    if MOCK_MODE:
        return {"remoteLinks": []}
    with _require_jira() as c:
        r = c.get(f"/issue/{issue_key}/remotelink")
        r.raise_for_status()
        return {"remoteLinks": r.json()}


def jira_create_issue_remote_link(
    issue_key: str, url: str, title: str, summary: str | None = None,
    global_id: str | None = None, execute: bool = True,
) -> dict:
    """Create or update a remote link on an issue."""
    _allow_project(issue_key)
    d = _dry("jira_create_issue_remote_link", {"issueKey": issue_key, "url": url}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"created": True}
    payload: dict[str, Any] = {"object": {"url": url, "title": title}}
    if summary:
        payload["object"]["summary"] = summary
    if global_id:
        payload["globalId"] = global_id
    with _require_jira() as c:
        r = c.post(f"/issue/{issue_key}/remotelink", json=payload)
        r.raise_for_status()
    audit_log("jira_create_issue_remote_link", {"issueKey": issue_key}, "success")
    return r.json() if r.content else {"created": True}


def jira_delete_issue_remote_link(issue_key: str, link_id: str, execute: bool = True) -> dict:
    """Delete a remote link from an issue."""
    _allow_project(issue_key)
    d = _dry("jira_delete_issue_remote_link", {"issueKey": issue_key, "linkId": link_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira() as c:
        c.delete(f"/issue/{issue_key}/remotelink/{link_id}").raise_for_status()
    audit_log("jira_delete_issue_remote_link", {"issueKey": issue_key, "linkId": link_id}, "success")
    return {"deleted": True}


# ── Versions ─────────────────────────────────────────────────────────────────

def jira_get_project_versions(project_key: str) -> dict:
    """Get all versions for a project."""
    _allow_project(project_key)
    if MOCK_MODE:
        return {"versions": []}
    with _require_jira() as c:
        r = c.get(f"/project/{project_key}/versions")
        r.raise_for_status()
        return {"versions": r.json()}


def jira_get_version(version_id: str) -> dict:
    """Get a version by ID."""
    if MOCK_MODE:
        return {"id": version_id}
    with _require_jira() as c:
        r = c.get(f"/version/{version_id}")
        r.raise_for_status()
        return r.json()


def jira_create_version(
    project_key: str, name: str, description: str = "",
    release_date: str | None = None, released: bool = False, execute: bool = True,
) -> dict:
    """Create a version in a project."""
    _allow_project(project_key)
    d = _dry("jira_create_version", {"project": project_key, "name": name}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"created": True, "name": name}
    payload: dict[str, Any] = {"name": name, "project": project_key, "released": released}
    if description:
        payload["description"] = description
    if release_date:
        payload["releaseDate"] = release_date
    with _require_jira() as c:
        r = c.post("/version", json=payload)
        r.raise_for_status()
    audit_log("jira_create_version", {"project": project_key, "name": name}, "success")
    return r.json()


def jira_update_version(
    version_id: str, name: str | None = None, description: str | None = None,
    release_date: str | None = None, released: bool | None = None, execute: bool = True,
) -> dict:
    """Update a version."""
    d = _dry("jira_update_version", {"versionId": version_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"updated": True}
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if release_date is not None:
        payload["releaseDate"] = release_date
    if released is not None:
        payload["released"] = released
    with _require_jira() as c:
        r = c.put(f"/version/{version_id}", json=payload)
        r.raise_for_status()
    audit_log("jira_update_version", {"versionId": version_id}, "success")
    return r.json()


def jira_delete_version(version_id: str, execute: bool = True) -> dict:
    """Delete a version."""
    d = _dry("jira_delete_version", {"versionId": version_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira() as c:
        c.delete(f"/version/{version_id}").raise_for_status()
    audit_log("jira_delete_version", {"versionId": version_id}, "success")
    return {"deleted": True}


# ── Components ───────────────────────────────────────────────────────────────

def jira_get_project_components(project_key: str) -> dict:
    """Get all components for a project."""
    _allow_project(project_key)
    if MOCK_MODE:
        return {"components": []}
    with _require_jira() as c:
        r = c.get(f"/project/{project_key}/components")
        r.raise_for_status()
        return {"components": r.json()}


def jira_get_component(component_id: str) -> dict:
    """Get a component by ID."""
    if MOCK_MODE:
        return {"id": component_id}
    with _require_jira() as c:
        r = c.get(f"/component/{component_id}")
        r.raise_for_status()
        return r.json()


def jira_create_component(
    project_key: str, name: str, description: str = "",
    lead: str | None = None, execute: bool = True,
) -> dict:
    """Create a component in a project."""
    _allow_project(project_key)
    d = _dry("jira_create_component", {"project": project_key, "name": name}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"created": True, "name": name}
    payload: dict[str, Any] = {"name": name, "project": project_key}
    if description:
        payload["description"] = description
    if lead:
        payload["leadUserName"] = lead
    with _require_jira() as c:
        r = c.post("/component", json=payload)
        r.raise_for_status()
    audit_log("jira_create_component", {"project": project_key, "name": name}, "success")
    return r.json()


def jira_update_component(
    component_id: str, name: str | None = None, description: str | None = None,
    lead: str | None = None, execute: bool = True,
) -> dict:
    """Update a component."""
    d = _dry("jira_update_component", {"componentId": component_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"updated": True}
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if lead is not None:
        payload["leadUserName"] = lead
    with _require_jira() as c:
        r = c.put(f"/component/{component_id}", json=payload)
        r.raise_for_status()
    audit_log("jira_update_component", {"componentId": component_id}, "success")
    return r.json()


def jira_delete_component(component_id: str, execute: bool = True) -> dict:
    """Delete a component."""
    d = _dry("jira_delete_component", {"componentId": component_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira() as c:
        c.delete(f"/component/{component_id}").raise_for_status()
    audit_log("jira_delete_component", {"componentId": component_id}, "success")
    return {"deleted": True}


# ── Assign, Transitions list, Issue-type metadata, Archive ───────────────────

def jira_assign_issue(issue_key: str, assignee: str | None, execute: bool = True) -> dict:
    """Assign an issue (null/'-1' to unassign, '-1' for default assignee)."""
    _allow_project(issue_key)
    d = _dry("jira_assign_issue", {"issueKey": issue_key, "assignee": assignee}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"assigned": True}
    with _require_jira() as c:
        c.put(f"/issue/{issue_key}/assignee", json={"name": assignee}).raise_for_status()
    audit_log("jira_assign_issue", {"issueKey": issue_key}, "success")
    return {"assigned": True}


def jira_list_transitions(issue_key: str) -> dict:
    """List available workflow transitions for an issue."""
    _allow_project(issue_key)
    if MOCK_MODE:
        return {"transitions": []}
    with _require_jira() as c:
        r = c.get(f"/issue/{issue_key}/transitions")
        r.raise_for_status()
        return r.json()


def jira_get_createmeta(project_key: str | None = None, issue_type_names: str | None = None) -> dict:
    """Get metadata for creating issues (projects, issue types, required fields)."""
    params: dict[str, Any] = {"expand": "projects.issuetypes.fields"}
    if project_key:
        _allow_project(project_key)
        params["projectKeys"] = project_key
    if issue_type_names:
        params["issuetypeNames"] = issue_type_names
    if MOCK_MODE:
        return {"projects": []}
    with _require_jira() as c:
        r = c.get("/issue/createmeta", params=params)
        r.raise_for_status()
        return r.json()


def jira_bulk_create_issues(issues: list[dict], execute: bool = True) -> dict:
    """Create multiple issues in one request. Each entry: {fields: {...}}."""
    d = _dry("jira_bulk_create_issues", {"count": len(issues)}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"created": len(issues)}
    with _require_jira() as c:
        r = c.post("/issue/bulk", json={"issueUpdates": issues})
        r.raise_for_status()
    audit_log("jira_bulk_create_issues", {"count": len(issues)}, "success")
    return r.json()


def jira_archive_issue(issue_key: str, execute: bool = True) -> dict:
    """Archive a single issue."""
    _allow_project(issue_key)
    d = _dry("jira_archive_issue", {"issueKey": issue_key}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"archived": True}
    with _require_jira() as c:
        c.put(f"/issue/{issue_key}/archive").raise_for_status()
    audit_log("jira_archive_issue", {"issueKey": issue_key}, "success")
    return {"archived": True}


def jira_restore_issue(issue_key: str, execute: bool = True) -> dict:
    """Restore an archived issue."""
    _allow_project(issue_key)
    d = _dry("jira_restore_issue", {"issueKey": issue_key}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"restored": True}
    with _require_jira() as c:
        c.put(f"/issue/{issue_key}/restore").raise_for_status()
    audit_log("jira_restore_issue", {"issueKey": issue_key}, "success")
    return {"restored": True}


# ── Filters ──────────────────────────────────────────────────────────────────

def jira_get_filter(filter_id: str) -> dict:
    """Get a Jira filter by ID."""
    if MOCK_MODE:
        return {"id": filter_id}
    with _require_jira() as c:
        r = c.get(f"/filter/{filter_id}")
        r.raise_for_status()
        return r.json()


def jira_get_favourite_filters() -> dict:
    """Get the current user's favourite filters."""
    if MOCK_MODE:
        return {"filters": []}
    with _require_jira() as c:
        r = c.get("/filter/favourite")
        r.raise_for_status()
        return {"filters": r.json()}


def jira_create_filter(
    name: str, jql: str, description: str = "", favourite: bool = False, execute: bool = True,
) -> dict:
    """Create a saved JQL filter."""
    d = _dry("jira_create_filter", {"name": name}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"created": True, "name": name}
    payload: dict[str, Any] = {"name": name, "jql": jql, "favourite": favourite}
    if description:
        payload["description"] = description
    with _require_jira() as c:
        r = c.post("/filter", json=payload)
        r.raise_for_status()
    audit_log("jira_create_filter", {"name": name}, "success")
    return r.json()


def jira_update_filter(
    filter_id: str, name: str | None = None, jql: str | None = None,
    description: str | None = None, execute: bool = True,
) -> dict:
    """Update a saved filter."""
    d = _dry("jira_update_filter", {"filterId": filter_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"updated": True}
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if jql is not None:
        payload["jql"] = jql
    if description is not None:
        payload["description"] = description
    with _require_jira() as c:
        r = c.put(f"/filter/{filter_id}", json=payload)
        r.raise_for_status()
    audit_log("jira_update_filter", {"filterId": filter_id}, "success")
    return r.json()


def jira_delete_filter(filter_id: str, execute: bool = True) -> dict:
    """Delete a saved filter."""
    d = _dry("jira_delete_filter", {"filterId": filter_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira() as c:
        c.delete(f"/filter/{filter_id}").raise_for_status()
    audit_log("jira_delete_filter", {"filterId": filter_id}, "success")
    return {"deleted": True}


# ============================================================================
# Bitbucket Tools
# ============================================================================

def bitbucket_list_prs(repo_slug: str, state: str = "OPEN", limit: int = 50) -> dict:
    """List pull requests in a Bitbucket repository."""
    _allow_repo(repo_slug)
    if MOCK_MODE:
        return {"values": [{"id": 1, "title": "Sample PR", "state": "OPEN", "author": {"display_name": "Dev"}}], "size": 1}
    client = bitbucket_client()
    if not client:
        raise ValueError("Bitbucket not configured.")

    if is_bitbucket_server():
        project_key = _get_bitbucket_project_key(repo_slug)
        endpoint = f"/projects/{project_key}/repos/{repo_slug}/pull-requests"
        params = {"state": state.upper(), "limit": limit}
    else:
        endpoint = f"/{repo_slug}/pullrequests"
        params = {"state": state, "pagelen": limit}

    with client as c:
        r = c.get(endpoint, params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("bitbucket_list_prs", {"repoSlug": repo_slug, "state": state}, "success")
    return data


def bitbucket_get_pr(repo_slug: str, pr_id: int) -> dict:
    """Get detailed information about a specific pull request."""
    _allow_repo(repo_slug)
    if MOCK_MODE:
        return {"id": pr_id, "title": "Sample PR", "state": "OPEN", "description": "Mock PR"}
    client = bitbucket_client()
    if not client:
        raise ValueError("Bitbucket not configured.")

    if is_bitbucket_server():
        project_key = _get_bitbucket_project_key(repo_slug)
        endpoint = f"/projects/{project_key}/repos/{repo_slug}/pull-requests/{pr_id}"
    else:
        endpoint = f"/{repo_slug}/pullrequests/{pr_id}"

    with client as c:
        r = c.get(endpoint)
        r.raise_for_status()
        data = r.json()
    audit_log("bitbucket_get_pr", {"repoSlug": repo_slug, "prId": pr_id}, "success")
    return data


def bitbucket_pr_diff(repo_slug: str, pr_id: int) -> dict:
    """Get the code diff for a pull request."""
    _allow_repo(repo_slug)
    if MOCK_MODE:
        return {"diff": "mock diff", "files": []}
    client = bitbucket_client()
    if not client:
        raise ValueError("Bitbucket not configured.")

    if is_bitbucket_server():
        project_key = _get_bitbucket_project_key(repo_slug)
        endpoint = f"/projects/{project_key}/repos/{repo_slug}/pull-requests/{pr_id}/diff"
    else:
        endpoint = f"/{repo_slug}/pullrequests/{pr_id}/diff"

    with client as c:
        r = c.get(endpoint)
        r.raise_for_status()
        data = r.text if r.headers.get("content-type", "").startswith("text") else r.json()
    audit_log("bitbucket_pr_diff", {"repoSlug": repo_slug, "prId": pr_id}, "success")
    return {"diff": data} if isinstance(data, str) else data


def bitbucket_pr_comment(repo_slug: str, pr_id: int, text: str, execute: bool = True) -> dict:
    """Add a comment to a pull request."""
    _allow_repo(repo_slug)
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("bitbucket_pr_comment", {"repoSlug": repo_slug, "prId": pr_id}, "success")
        return {"dryRun": True}
    if MOCK_MODE:
        return {"created": True}

    client = bitbucket_client()
    if not client:
        raise ValueError("Bitbucket not configured.")

    if is_bitbucket_server():
        project_key = _get_bitbucket_project_key(repo_slug)
        endpoint = f"/projects/{project_key}/repos/{repo_slug}/pull-requests/{pr_id}/comments"
        payload = {"text": text}
    else:
        endpoint = f"/{repo_slug}/pullrequests/{pr_id}/comments"
        payload = {"content": {"raw": text}}

    with client as c:
        c.post(endpoint, json=payload).raise_for_status()
    audit_log("bitbucket_pr_comment", {"repoSlug": repo_slug, "prId": pr_id}, "success")
    return {"created": True}


def bitbucket_approve_pr(repo_slug: str, pr_id: int, execute: bool = True) -> dict:
    """Approve a pull request."""
    _allow_repo(repo_slug)
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("bitbucket_approve_pr", {"repoSlug": repo_slug, "prId": pr_id}, "success")
        return {"dryRun": True}
    if MOCK_MODE:
        return {"approved": True}

    client = bitbucket_client()
    if not client:
        raise ValueError("Bitbucket not configured.")

    if is_bitbucket_server():
        project_key = _get_bitbucket_project_key(repo_slug)
        endpoint = f"/projects/{project_key}/repos/{repo_slug}/pull-requests/{pr_id}/approve"
    else:
        endpoint = f"/{repo_slug}/pullrequests/{pr_id}/approve"

    with client as c:
        c.post(endpoint).raise_for_status()
    audit_log("bitbucket_approve_pr", {"repoSlug": repo_slug, "prId": pr_id}, "success")
    return {"approved": True}


def bitbucket_merge_pr(repo_slug: str, pr_id: int, message: str | None = None, execute: bool = True) -> dict:
    """Merge a pull request."""
    _allow_repo(repo_slug)
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("bitbucket_merge_pr", {"repoSlug": repo_slug, "prId": pr_id}, "success")
        return {"dryRun": True}
    if MOCK_MODE:
        return {"merged": True}

    client = bitbucket_client()
    if not client:
        raise ValueError("Bitbucket not configured.")

    if is_bitbucket_server():
        project_key = _get_bitbucket_project_key(repo_slug)
        endpoint = f"/projects/{project_key}/repos/{repo_slug}/pull-requests/{pr_id}/merge"
    else:
        endpoint = f"/{repo_slug}/pullrequests/{pr_id}/merge"

    payload = {}
    if message:
        payload["message"] = message

    with client as c:
        c.post(endpoint, json=payload if payload else None).raise_for_status()
    audit_log("bitbucket_merge_pr", {"repoSlug": repo_slug, "prId": pr_id}, "success")
    return {"merged": True}


def bitbucket_list_repos(limit: int = 50) -> dict:
    """List all repositories in the workspace/project."""
    if MOCK_MODE:
        return {"values": [{"slug": "demo-repo", "name": "Demo Repo"}], "size": 1}
    client = bitbucket_client()
    if not client:
        raise ValueError("Bitbucket not configured.")

    if is_bitbucket_server():
        endpoint = "/repos"
    else:
        endpoint = ""  # base URL already includes workspace

    with client as c:
        r = c.get(endpoint, params={"pagelen": limit} if not is_bitbucket_server() else {"limit": limit})
        r.raise_for_status()
        data = r.json()
    audit_log("bitbucket_list_repos", {"limit": limit}, "success")
    return data


# ============================================================================
# Confluence Tools
# ============================================================================

def confluence_search(query: str, space_key: str | None = None, content_type: str = "page", limit: int = 50) -> dict:
    """Search Confluence pages and content."""
    if space_key:
        _allow_space(space_key)
    if MOCK_MODE:
        return {"results": [{"content": {"id": "1", "title": "Sample", "type": "page"}}], "size": 1}
    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")

    cql = query
    if space_key:
        cql = f'space = "{space_key}" AND ({query})'

    with client as c:
        r = c.get("/content/search", params={"cql": cql, "limit": limit})
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    if ALLOWLIST_CONFLUENCE_SPACE_KEYS:
        allowed = {k.upper() for k in ALLOWLIST_CONFLUENCE_SPACE_KEYS}
        results = [r for r in results if not (r.get("space") or {}).get("key") or (r["space"]["key"] or "").upper() in allowed]
        data["results"] = results
    audit_log("confluence_search", {"query": query, "limit": limit}, "success")
    return data


def confluence_get_page(page_id: str | None = None, space_key: str | None = None, title: str | None = None) -> dict:
    """Get a specific Confluence page by ID or title."""
    if space_key:
        _allow_space(space_key)
    if MOCK_MODE:
        return {"id": page_id or "1", "title": title or "Sample Page", "body": {"storage": {"value": "<p>Mock content</p>"}}}
    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")

    with client as c:
        if page_id:
            r = c.get(f"/content/{page_id}", params={"expand": "body.storage,version,space"})
        elif space_key and title:
            r = c.get("/content", params={"spaceKey": space_key, "title": title, "expand": "body.storage,version,space"})
        else:
            raise ValueError("Provide either page_id or (space_key + title)")
        r.raise_for_status()
        data = r.json()

    if "results" in data:
        data = data["results"][0] if data["results"] else {}
    audit_log("confluence_get_page", {"page_id": page_id, "space_key": space_key, "title": title}, "success")
    return data


def confluence_create_page(space_key: str, title: str, content: str, parent_id: str | None = None, execute: bool = True) -> dict:
    """Create a new Confluence page."""
    _allow_space(space_key)
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("confluence_create_page", {"spaceKey": space_key, "title": title}, "success")
        return {"dryRun": True, "wouldCreate": {"spaceKey": space_key, "title": title}}
    if MOCK_MODE:
        return {"id": "123", "title": title, "created": True}

    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    payload: dict[str, Any] = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {"storage": {"value": content, "representation": "storage"}},
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]

    with client as c:
        r = c.post("/content", json=payload)
        r.raise_for_status()
        data = r.json()
    audit_log("confluence_create_page", {"spaceKey": space_key, "title": title}, "success")
    return {"id": data["id"], "title": data["title"], "created": True}


def confluence_update_page(page_id: str, title: str, content: str, version: int, execute: bool = True) -> dict:
    """Update an existing Confluence page."""
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("confluence_update_page", {"pageId": page_id}, "success")
        return {"dryRun": True}
    if MOCK_MODE:
        return {"updated": True}

    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    with client as c:
        page = c.get(f"/content/{page_id}").json()
        space_key = (page.get("space") or {}).get("key")
        if space_key:
            _allow_space(space_key)
        payload = {
            "id": page_id,
            "type": "page",
            "title": title or page.get("title"),
            "version": {"number": version + 1},
            "body": {"storage": {"value": content, "representation": "storage"}},
        }
        c.put(f"/content/{page_id}", json=payload).raise_for_status()
    audit_log("confluence_update_page", {"pageId": page_id}, "success")
    return {"updated": True}


def confluence_add_comment(page_id: str, comment: str, execute: bool = True) -> dict:
    """Add a comment to a Confluence page."""
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("confluence_add_comment", {"pageId": page_id}, "success")
        return {"dryRun": True}
    if MOCK_MODE:
        return {"created": True}

    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    payload = {
        "type": "comment",
        "container": {"id": page_id, "type": "page"},
        "body": {"storage": {"value": comment, "representation": "storage"}},
    }
    with client as c:
        c.post("/content", json=payload).raise_for_status()
    audit_log("confluence_add_comment", {"pageId": page_id}, "success")
    return {"created": True}


def confluence_list_spaces(limit: int = 50) -> dict:
    """List all accessible Confluence spaces."""
    if MOCK_MODE:
        return {"results": [{"key": "DEMO", "name": "Demo Space"}], "size": 1}
    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    with client as c:
        r = c.get("/space", params={"limit": limit})
        r.raise_for_status()
        data = r.json()
    audit_log("confluence_list_spaces", {"limit": limit}, "success")
    return data


def confluence_get_page_versions(page_id: str, limit: int = 25) -> dict:
    """List all versions of a Confluence page with version number, author, timestamp, and message."""
    if MOCK_MODE:
        return {"results": [
            {"number": 3, "when": "2026-01-03T00:00:00Z", "by": {"displayName": "Mock User"}, "message": ""},
            {"number": 2, "when": "2026-01-02T00:00:00Z", "by": {"displayName": "Mock User"}, "message": "revert"},
            {"number": 1, "when": "2026-01-01T00:00:00Z", "by": {"displayName": "Mock User"}, "message": ""},
        ], "size": 3, "limit": limit}
    client = confluence_experimental_client()
    if not client:
        raise ValueError("Confluence not configured.")
    with client as c:
        r = c.get(f"/content/{page_id}/version", params={"limit": limit})
        r.raise_for_status()
        data = r.json()
    audit_log("confluence_get_page_versions", {"page_id": page_id, "limit": limit}, "success")
    return data


def confluence_get_page_version(page_id: str, version_number: int) -> dict:
    """Get the full body.storage content of a specific historical version of a Confluence page (for recovering reverted content)."""
    if MOCK_MODE:
        return {"number": version_number, "when": "2026-01-01T00:00:00Z", "by": {"displayName": "Mock User"},
                "content": {"id": page_id, "title": "Sample Page",
                            "body": {"storage": {"value": f"<p>Mock content at version {version_number}</p>", "representation": "storage"}}}}
    client = confluence_experimental_client()
    if not client:
        raise ValueError("Confluence not configured.")
    with client as c:
        r = c.get(f"/content/{page_id}/version/{version_number}", params={"expand": "content.body.storage"})
        r.raise_for_status()
        data = r.json()
    space_key = ((data.get("content") or {}).get("space") or {}).get("key")
    if space_key:
        _allow_space(space_key)
    audit_log("confluence_get_page_version", {"page_id": page_id, "version_number": version_number}, "success")
    return data


def confluence_get_child_pages(page_id: str, limit: int = 50) -> dict:
    """List the direct child pages of a Confluence page (with version and space info)."""
    if MOCK_MODE:
        return {"results": [{"id": "200", "title": "Child Page", "type": "page", "version": {"number": 1}}], "size": 1, "limit": limit}
    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    with client as c:
        r = c.get(f"/content/{page_id}/child/page", params={"expand": "version,space", "limit": limit})
        r.raise_for_status()
        data = r.json()
    audit_log("confluence_get_child_pages", {"page_id": page_id, "limit": limit}, "success")
    return data


def confluence_get_page_ancestors(page_id: str) -> dict:
    """Get the ancestor (breadcrumb) chain of a Confluence page, simplified to id and title."""
    if MOCK_MODE:
        return {"page_id": page_id, "ancestors": [{"id": "1", "title": "Home"}, {"id": "2", "title": "Section"}]}
    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    with client as c:
        r = c.get(f"/content/{page_id}", params={"expand": "ancestors"})
        r.raise_for_status()
        data = r.json()
    ancestors = [{"id": a.get("id"), "title": a.get("title")} for a in data.get("ancestors", [])]
    audit_log("confluence_get_page_ancestors", {"page_id": page_id}, "success")
    return {"page_id": page_id, "ancestors": ancestors}


def confluence_get_attachments(page_id: str, limit: int = 25) -> dict:
    """List attachments on a Confluence page (id, title, mediaType, download link)."""
    if MOCK_MODE:
        return {"results": [{"id": "att1", "title": "diagram.png", "metadata": {"mediaType": "image/png"},
                             "_links": {"download": "/download/attachments/1/diagram.png"}}], "size": 1, "limit": limit}
    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    with client as c:
        r = c.get(f"/content/{page_id}/child/attachment", params={"limit": limit})
        r.raise_for_status()
        data = r.json()
    audit_log("confluence_get_attachments", {"page_id": page_id, "limit": limit}, "success")
    return data


def confluence_get_page_labels(page_id: str) -> dict:
    """List the labels attached to a Confluence page."""
    if MOCK_MODE:
        return {"results": [{"name": "technical-debt", "prefix": "global", "id": "1"}], "size": 1}
    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    with client as c:
        r = c.get(f"/content/{page_id}/label")
        r.raise_for_status()
        data = r.json()
    audit_log("confluence_get_page_labels", {"page_id": page_id}, "success")
    return data


# ── Confluence file-based tools (for payloads too large for MCP tool args) ────

_MAX_CONTENT_FILE_BYTES = 5 * 1024 * 1024  # 5 MB safety cap


def _read_local_file(path: str) -> tuple[str | None, dict | None]:
    """Read a UTF-8 text file with validation. Returns (content, None) or (None, error_dict)."""
    if not isinstance(path, str) or not path:
        return None, {"error": True, "type": "file_error", "message": "No file path provided."}
    if not os.path.isfile(path):
        return None, {"error": True, "type": "file_error", "message": f"File not found: {path}"}
    try:
        size = os.path.getsize(path)
    except OSError as e:
        return None, {"error": True, "type": "file_error", "message": f"Cannot stat {path}: {e}"}
    if size == 0:
        return None, {"error": True, "type": "file_error", "message": f"File is empty: {path}"}
    if size > _MAX_CONTENT_FILE_BYTES:
        return None, {"error": True, "type": "file_error",
                      "message": f"File exceeds 5 MB cap ({size} bytes): {path}"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), None
    except (OSError, UnicodeDecodeError) as e:
        return None, {"error": True, "type": "file_error", "message": f"Cannot read {path}: {e}"}


def confluence_update_page_from_file(page_id: str, title: str, version: int, content_file: str,
                                     execute: bool = False, message: str | None = None) -> dict:
    """Update a Confluence page using storage-format XML read from a local file.

    Use this when the page body is large (>10KB) — passing it inline as a tool argument
    risks truncation at the MCP transport boundary. `version` is the target version number
    (the page's current version + 1, since Confluence requires a strict increment).
    Dry-run by default; set execute=true (and WORKGRAPH_MODE=EXECUTE) to publish.
    """
    content, err = _read_local_file(content_file)
    if err:
        return err
    if not content.strip():
        return {"error": True, "type": "file_error", "message": f"File has no usable content: {content_file}"}

    path = f"/content/{page_id}"
    if not execute:
        audit_log("confluence_update_page_from_file", {"page_id": page_id, "chars": len(content)}, "success")
        return {
            "dryRun": True, "method": "PUT", "path": path, "pageId": page_id,
            "version": version, "title": title, "contentChars": len(content),
            "preview": {"head": content[:200], "tail": content[-200:] if len(content) > 200 else ""},
        }
    if not is_execute_allowed():
        return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN. Set EXECUTE and execute=true to publish."}
    if MOCK_MODE:
        return {"updated": True}

    client = confluence_client()
    if not client:
        raise ValueError("Confluence not configured.")
    payload = {
        "version": {"number": version, "message": message or ""},
        "title": title,
        "type": "page",
        "body": {"storage": {"value": content, "representation": "storage"}},
    }
    with client as c:
        c.put(path, json=payload).raise_for_status()
    audit_log("confluence_update_page_from_file", {"page_id": page_id, "chars": len(content)}, "success")
    return {"updated": True}


def confluence_raw_from_file(method: str, path: str, body_file: str,
                             params: dict | None = None, execute: bool = False) -> dict:
    """Call any Confluence REST endpoint with a JSON request body read from a local file.

    Use this when the request body is large (>10KB) and would be truncated as an inline
    tool argument. The file must contain valid JSON (validated before sending). path is
    relative to /rest/api. Write methods are dry-run by default; set execute=true (and
    WORKGRAPH_MODE=EXECUTE) to send.
    """
    raw, err = _read_local_file(body_file)
    if err:
        return err
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": True, "type": "json_error", "message": f"Body file is not valid JSON: {e}"}

    method_u = (method or "").upper()
    if not execute:
        audit_log("confluence_raw_from_file", {"method": method_u, "path": path, "chars": len(raw)}, "success")
        return {
            "dryRun": True, "method": method_u, "path": path, "params": params,
            "contentChars": len(raw),
            "bodyTopLevelKeys": list(body.keys()) if isinstance(body, dict) else None,
        }
    return _raw("confluence_raw_from_file", confluence_client, method, path, params, body, execute=True)


def confluence_get_page_to_file(page_id: str, output_file: str,
                                expand: str = "body.storage,version,space") -> dict:
    """Fetch a Confluence page and write its storage-format body to a local file.

    Use this for backup-before-update workflows, or when the page body is too large to
    return inline as a tool result. Returns page metadata (id, title, version, chars
    written) WITHOUT the body itself.
    """
    if MOCK_MODE:
        body_val = "<p>Mock content</p>"
        meta = {"id": page_id, "title": "Sample Page", "version": 1}
    else:
        client = confluence_client()
        if not client:
            raise ValueError("Confluence not configured.")
        with client as c:
            r = c.get(f"/content/{page_id}", params={"expand": expand})
            r.raise_for_status()
            data = r.json()
        space_key = (data.get("space") or {}).get("key")
        if space_key:
            _allow_space(space_key)
        body_val = (((data.get("body") or {}).get("storage") or {}).get("value"))
        if body_val is None:
            return {"error": True, "type": "response_error",
                    "message": "Page response did not contain body.storage.value — check the expand parameter."}
        meta = {"id": data.get("id", page_id), "title": data.get("title"),
                "version": (data.get("version") or {}).get("number")}

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(body_val)
    except OSError as e:
        return {"error": True, "type": "file_error", "message": f"Cannot write {output_file}: {e}"}
    audit_log("confluence_get_page_to_file",
              {"page_id": page_id, "output_file": output_file, "chars": len(body_val)}, "success")
    return {**meta, "outputFile": output_file, "contentChars": len(body_val)}


# ============================================================================
# Bamboo Tools
# ============================================================================

def bamboo_list_plans(max_results: int = 50) -> dict:
    """List all build plans in Bamboo."""
    if MOCK_MODE:
        return {"plans": {"plan": [{"key": "PROJ-BUILD", "name": "Sample Plan"}]}, "size": 1}
    client = bamboo_client()
    if not client:
        raise ValueError("Bamboo not configured.")
    with client as c:
        r = c.get("/plan", params={"max-results": max_results})
        r.raise_for_status()
        data = r.json()
    audit_log("bamboo_list_plans", {"max_results": max_results}, "success")
    return data


def bamboo_list_builds(plan_key: str, max_results: int = 50, include_all_states: bool = True) -> dict:
    """List builds for a specific build plan."""
    _allow_plan(plan_key)
    if MOCK_MODE:
        return {"builds": {"build": [{"buildNumber": 1, "state": "Successful", "buildResultKey": f"{plan_key}-1"}]}, "size": 1}
    client = bamboo_client()
    if not client:
        raise ValueError("Bamboo not configured.")
    params: dict[str, Any] = {"max-results": max_results}
    if include_all_states:
        params["includeAllStates"] = "true"
    with client as c:
        r = c.get(f"/result/{plan_key}", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("bamboo_list_builds", {"planKey": plan_key}, "success")
    return data


def bamboo_build_status(plan_key: str, build_number: int | None = None) -> dict:
    """Get status and details of a specific build or the latest build."""
    _allow_plan(plan_key)
    if MOCK_MODE:
        return {"planKey": plan_key, "state": "Successful", "successRate": 0.95}
    client = bamboo_client()
    if not client:
        raise ValueError("Bamboo not configured.")
    with client as c:
        if build_number:
            r = c.get(f"/result/{plan_key}-{build_number}")
        else:
            r = c.get(f"/result/{plan_key}/latest")
        r.raise_for_status()
        data = r.json()
        state = data.get("state", "Unknown")
        bn = data.get("buildNumber", 0)
        success_rate = 0.0
        try:
            hist = c.get(f"/result/{plan_key}", params={"max-results": 10})
            hist.raise_for_status()
            builds = (hist.json().get("results") or {}).get("result") or []
            success_rate = sum(1 for b in builds if b.get("state") == "Successful") / len(builds) if builds else (1.0 if state == "Successful" else 0.0)
        except Exception:
            success_rate = 1.0 if state == "Successful" else 0.0
    audit_log("bamboo_build_status", {"planKey": plan_key}, "success")
    return {"planKey": plan_key, "state": state, "buildNumber": bn, "successRate": success_rate}


def bamboo_get_build(build_key: str) -> dict:
    """Get detailed information about a specific build."""
    plan_key = "-".join(build_key.split("-")[:2])
    _allow_plan(plan_key)
    if MOCK_MODE:
        return {"buildResultKey": build_key, "state": "Successful", "stages": []}
    client = bamboo_client()
    if not client:
        raise ValueError("Bamboo not configured.")
    with client as c:
        r = c.get(f"/result/{build_key}", params={"expand": "stages.stage.results"})
        r.raise_for_status()
        data = r.json()
    audit_log("bamboo_get_build", {"build_key": build_key}, "success")
    return data


def bamboo_trigger_build(plan_key: str, variables: dict | None = None, execute: bool = True) -> dict:
    """Trigger a new build for a build plan."""
    _allow_plan(plan_key)
    if execute and not is_execute_allowed():
        return {"dryRun": True}
    if not execute:
        audit_log("bamboo_trigger_build", {"planKey": plan_key}, "success")
        return {"dryRun": True}
    if MOCK_MODE:
        return {"buildResultKey": f"{plan_key}-999", "triggered": True}

    client = bamboo_client()
    if not client:
        raise ValueError("Bamboo not configured.")
    params = {}
    if variables:
        for k, v in variables.items():
            params[f"bamboo.variable.{k}"] = v
    with client as c:
        r = c.post(f"/queue/{plan_key}", params=params)
        r.raise_for_status()
        data = r.json()
    audit_log("bamboo_trigger_build", {"planKey": plan_key}, "success")
    return data


def bamboo_summarize_failures(plan_key: str, limit: int = 10) -> dict:
    """Get a summary of recent build failures."""
    _allow_plan(plan_key)
    if MOCK_MODE:
        return {"planKey": plan_key, "failedJobs": [], "summary": "No failures (mock)."}
    client = bamboo_client()
    if not client:
        raise ValueError("Bamboo not configured.")
    with client as c:
        r = c.get(f"/result/{plan_key}/latest")
        r.raise_for_status()
        build = r.json()
        build_result_key = build.get("buildResultKey") or f"{plan_key}-0"
        r2 = c.get(f"/result/{build_result_key}/job", params={"expand": "jobs"})
        r2.raise_for_status()
        jobs = r2.json()
    job_list = (jobs.get("jobs") or {}).get("job") or []
    failed = [j for j in job_list if j.get("state") == "Failed"]
    audit_log("bamboo_summarize_failures", {"planKey": plan_key}, "success")
    return {"planKey": plan_key, "buildResultKey": build_result_key, "failedJobs": failed, "summary": f"{len(failed)} failed job(s)."}


def bamboo_get_build_log(build_key: str) -> dict:
    """Get the build log output for a specific build."""
    plan_key = "-".join(build_key.split("-")[:2])
    _allow_plan(plan_key)
    if MOCK_MODE:
        return {"buildKey": build_key, "log": "Mock build log output"}
    client = bamboo_client()
    if not client:
        raise ValueError("Bamboo not configured.")
    with client as c:
        r = c.get(f"/result/{build_key}/log")
        r.raise_for_status()
        log_text = r.text
    audit_log("bamboo_get_build_log", {"build_key": build_key}, "success")
    return {"buildKey": build_key, "log": log_text}


# ── Dashboards ───────────────────────────────────────────────────────────────

def jira_list_dashboards(filter: str | None = None, max_results: int = 20, start_at: int = 0) -> dict:
    """List Jira dashboards. filter='favourite' returns favourites only."""
    if MOCK_MODE:
        return {"dashboards": [], "total": 0}
    params: dict[str, Any] = {"maxResults": max_results, "startAt": start_at}
    if filter:
        params["filter"] = filter
    with _require_jira() as c:
        r = c.get("/dashboard", params=params)
        r.raise_for_status()
        return r.json()


def jira_get_dashboard(dashboard_id: str) -> dict:
    """Get a single Jira dashboard by ID."""
    if MOCK_MODE:
        return {"id": dashboard_id}
    with _require_jira() as c:
        r = c.get(f"/dashboard/{dashboard_id}")
        r.raise_for_status()
        return r.json()


def jira_list_dashboard_item_properties(dashboard_id: str, item_id: str) -> dict:
    """List all property keys for a dashboard item (gadget)."""
    if MOCK_MODE:
        return {"keys": []}
    with _require_jira() as c:
        r = c.get(f"/dashboard/{dashboard_id}/items/{item_id}/properties")
        r.raise_for_status()
        return r.json()


def jira_get_dashboard_item_property(dashboard_id: str, item_id: str, property_key: str) -> dict:
    """Get a single property value for a dashboard item."""
    if MOCK_MODE:
        return {"key": property_key}
    with _require_jira() as c:
        r = c.get(f"/dashboard/{dashboard_id}/items/{item_id}/properties/{property_key}")
        r.raise_for_status()
        return r.json()


def jira_set_dashboard_item_property(
    dashboard_id: str, item_id: str, property_key: str, value: Any, execute: bool = True,
) -> dict:
    """Set a property on a dashboard item. value can be any JSON-serializable type."""
    d = _dry("jira_set_dashboard_item_property",
             {"dashboardId": dashboard_id, "itemId": item_id, "propertyKey": property_key}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"set": True}
    with _require_jira() as c:
        c.put(f"/dashboard/{dashboard_id}/items/{item_id}/properties/{property_key}", json=value).raise_for_status()
    audit_log("jira_set_dashboard_item_property",
              {"dashboardId": dashboard_id, "itemId": item_id, "propertyKey": property_key}, "success")
    return {"set": True}


def jira_delete_dashboard_item_property(
    dashboard_id: str, item_id: str, property_key: str, execute: bool = True,
) -> dict:
    """Delete a property from a dashboard item."""
    d = _dry("jira_delete_dashboard_item_property",
             {"dashboardId": dashboard_id, "itemId": item_id, "propertyKey": property_key}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira() as c:
        c.delete(f"/dashboard/{dashboard_id}/items/{item_id}/properties/{property_key}").raise_for_status()
    audit_log("jira_delete_dashboard_item_property",
              {"dashboardId": dashboard_id, "itemId": item_id, "propertyKey": property_key}, "success")
    return {"deleted": True}


# ── Dashboards plugin API (internal /rest/dashboards/1.0/) ──────────────────
# These let you actually CREATE/MODIFY dashboards and add gadgets — the public
# /rest/api/2/dashboard endpoints only support read.

def _require_jira_dashboards() -> Any:
    c = jira_dashboards_client()
    if not c:
        raise ValueError("Jira not configured.")
    return c


def jira_create_dashboard(
    name: str, description: str = "",
    layout: str = "AA",
    share_permissions: list[dict] | None = None,
    edit_permissions: list[dict] | None = None,
    execute: bool = True,
) -> dict:
    """Create a new Jira dashboard.

    layout: column code — 'A' (1 col), 'AA' (2 equal), 'AB' (2: 60/40),
            'AAA' (3 equal), 'ABA' (3: 25/50/25), 'AABC' (4 cols).
    share_permissions / edit_permissions: list of dicts like
            [{'type': 'global'}], [{'type': 'authenticated'}],
            [{'type': 'user', 'param': 'username'}],
            [{'type': 'project', 'param': 'projectId'}].
    Defaults to private (only the creator can see/edit).
    """
    d = _dry("jira_create_dashboard", {"name": name}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"id": "9999", "name": name, "created": True}
    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "layout": layout,
        "sharePermissions": share_permissions or [],
        "editPermissions": edit_permissions or [],
    }
    with _require_jira_dashboards() as c:
        r = c.post("/", json=payload)
        r.raise_for_status()
    audit_log("jira_create_dashboard", {"name": name}, "success")
    return r.json()


def jira_update_dashboard(
    dashboard_id: str, name: str | None = None, description: str | None = None,
    layout: str | None = None,
    share_permissions: list[dict] | None = None,
    edit_permissions: list[dict] | None = None,
    execute: bool = True,
) -> dict:
    """Update a dashboard's name/description/layout/permissions."""
    d = _dry("jira_update_dashboard", {"dashboardId": dashboard_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"id": dashboard_id, "updated": True}
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if layout is not None:
        payload["layout"] = layout
    if share_permissions is not None:
        payload["sharePermissions"] = share_permissions
    if edit_permissions is not None:
        payload["editPermissions"] = edit_permissions
    with _require_jira_dashboards() as c:
        r = c.put(f"/{dashboard_id}", json=payload)
        r.raise_for_status()
    audit_log("jira_update_dashboard", {"dashboardId": dashboard_id}, "success")
    return r.json() if r.content else {"updated": True}


def jira_delete_dashboard(dashboard_id: str, execute: bool = True) -> dict:
    """Delete a Jira dashboard by ID."""
    d = _dry("jira_delete_dashboard", {"dashboardId": dashboard_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"deleted": True}
    with _require_jira_dashboards() as c:
        c.delete(f"/{dashboard_id}").raise_for_status()
    audit_log("jira_delete_dashboard", {"dashboardId": dashboard_id}, "success")
    return {"deleted": True}


def jira_list_available_gadgets() -> dict:
    """List all gadgets available to add to a dashboard.

    Each entry has a 'uri' (gadget XML spec) and a 'title'. Pass the uri
    to jira_add_dashboard_gadget. Common gadget URIs include:
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:filter-results-gadget/gadgets/filter-results-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:pie-chart-gadget/gadgets/pie-chart-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:two-dimensional-stats-gadget/gadgets/two-dimensional-stats-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:created-vs-resolved-chart-gadget/gadgets/created-vs-resolved-chart-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:assigned-to-me-gadget/gadgets/assigned-to-me-gadget.xml
      - rest/gadgets/1.0/g/com.atlassian.jira.gadgets:sprint-burndown-gadget/gadgets/sprint-burndown-gadget.xml
    """
    if MOCK_MODE:
        return {"gadgets": []}
    with _require_jira_dashboards() as c:
        r = c.get("/gadgets")
        r.raise_for_status()
        return r.json()


def jira_add_dashboard_gadget(
    dashboard_id: str, uri: str, color: str = "blue",
    column: int | None = None, row: int | None = None, execute: bool = True,
) -> dict:
    """Add a gadget (chart) to a dashboard. uri comes from jira_list_available_gadgets."""
    d = _dry("jira_add_dashboard_gadget", {"dashboardId": dashboard_id, "uri": uri}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"id": "g-1", "added": True}
    payload: dict[str, Any] = {"uri": uri, "color": color}
    if column is not None:
        payload["column"] = column
    if row is not None:
        payload["row"] = row
    with _require_jira_dashboards() as c:
        r = c.post(f"/{dashboard_id}/gadget", json=payload)
        r.raise_for_status()
    audit_log("jira_add_dashboard_gadget", {"dashboardId": dashboard_id, "uri": uri}, "success")
    return r.json()


def jira_list_dashboard_gadgets(dashboard_id: str) -> dict:
    """List gadgets currently on a dashboard."""
    if MOCK_MODE:
        return {"gadgets": []}
    with _require_jira_dashboards() as c:
        r = c.get(f"/{dashboard_id}/gadget")
        r.raise_for_status()
        return r.json()


def jira_move_dashboard_gadget(
    dashboard_id: str, gadget_id: str,
    column: int | None = None, row: int | None = None, color: str | None = None,
    execute: bool = True,
) -> dict:
    """Move a gadget to a new column/row on a dashboard, or change its color."""
    d = _dry("jira_move_dashboard_gadget",
             {"dashboardId": dashboard_id, "gadgetId": gadget_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"moved": True}
    payload: dict[str, Any] = {}
    if column is not None:
        payload["column"] = column
    if row is not None:
        payload["row"] = row
    if color is not None:
        payload["color"] = color
    with _require_jira_dashboards() as c:
        r = c.put(f"/{dashboard_id}/gadget/{gadget_id}", json=payload)
        r.raise_for_status()
    audit_log("jira_move_dashboard_gadget",
              {"dashboardId": dashboard_id, "gadgetId": gadget_id}, "success")
    return r.json() if r.content else {"moved": True}


def jira_remove_dashboard_gadget(dashboard_id: str, gadget_id: str, execute: bool = True) -> dict:
    """Remove a gadget from a dashboard."""
    d = _dry("jira_remove_dashboard_gadget",
             {"dashboardId": dashboard_id, "gadgetId": gadget_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"removed": True}
    with _require_jira_dashboards() as c:
        c.delete(f"/{dashboard_id}/gadget/{gadget_id}").raise_for_status()
    audit_log("jira_remove_dashboard_gadget",
              {"dashboardId": dashboard_id, "gadgetId": gadget_id}, "success")
    return {"removed": True}


def jira_get_myself() -> dict:
    """Get the currently authenticated user (key/name/accountId for share/edit perms)."""
    if MOCK_MODE:
        return {"name": "mock"}
    with _require_jira() as c:
        r = c.get("/myself")
        r.raise_for_status()
        return r.json()


def jira_search_users(query: str, max_results: int = 20) -> dict:
    """Search Jira users by username/email/display name. Useful for share/edit perms and assignee."""
    if MOCK_MODE:
        return {"users": []}
    with _require_jira() as c:
        r = c.get("/user/search", params={"username": query, "maxResults": max_results})
        r.raise_for_status()
        return {"users": r.json()}


def jira_list_groups(query: str = "", max_results: int = 50) -> dict:
    """List Jira groups (group picker). Useful for group-scoped dashboard share permissions."""
    if MOCK_MODE:
        return {"groups": {"items": []}}
    with _require_jira() as c:
        r = c.get("/groups/picker", params={"query": query, "maxResults": max_results})
        r.raise_for_status()
        return r.json()


def jira_list_projects() -> dict:
    """List all Jira projects visible to the current user."""
    if MOCK_MODE:
        return {"projects": []}
    with _require_jira() as c:
        r = c.get("/project")
        r.raise_for_status()
        return {"projects": r.json()}


def jira_list_statuses() -> dict:
    """List all global issue statuses (id, name, category) — useful for chart configuration."""
    if MOCK_MODE:
        return {"statuses": []}
    with _require_jira() as c:
        r = c.get("/status")
        r.raise_for_status()
        return {"statuses": r.json()}


def jira_list_priorities() -> dict:
    """List all issue priorities — useful for priority breakdown gadgets."""
    if MOCK_MODE:
        return {"priorities": []}
    with _require_jira() as c:
        r = c.get("/priority")
        r.raise_for_status()
        return {"priorities": r.json()}


def jira_list_issue_types() -> dict:
    """List all issue types — useful for issue-type breakdown gadgets."""
    if MOCK_MODE:
        return {"issueTypes": []}
    with _require_jira() as c:
        r = c.get("/issuetype")
        r.raise_for_status()
        return {"issueTypes": r.json()}


def jira_list_fields() -> dict:
    """List all Jira fields (system + custom). Returns id, name, custom flag — needed to set 'statType' on stats gadgets and pick custom fields."""
    if MOCK_MODE:
        return {"fields": []}
    with _require_jira() as c:
        r = c.get("/field")
        r.raise_for_status()
        return {"fields": r.json()}


def jira_set_dashboard_gadget_prefs(
    dashboard_id: str, gadget_id: str, prefs: dict, execute: bool = True,
) -> dict:
    """Configure a gadget's preferences (e.g. JQL filter, project, chart type).

    prefs is a flat dict like {'filterId': '10001', 'numberToShow': '10'}.
    Each gadget XML defines its own pref keys; inspect via the UI's
    'Edit' panel or the gadget XML at the URI.
    """
    d = _dry("jira_set_dashboard_gadget_prefs",
             {"dashboardId": dashboard_id, "gadgetId": gadget_id}, execute)
    if d is not None:
        return d
    if MOCK_MODE:
        return {"set": True}
    payload = {"prefs": [{"key": k, "value": str(v)} for k, v in prefs.items()]}
    with _require_jira_dashboards() as c:
        r = c.put(f"/{dashboard_id}/gadget/{gadget_id}/prefs", json=payload)
        r.raise_for_status()
    audit_log("jira_set_dashboard_gadget_prefs",
              {"dashboardId": dashboard_id, "gadgetId": gadget_id}, "success")
    return r.json() if r.content else {"set": True}


# ============================================================================
# Raw passthrough tools — full API coverage for advanced/niche endpoints
# ============================================================================

_WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def _raw_call(client: Any, method: str, path: str, params: dict | None, body: Any) -> dict:
    method = method.upper()
    if not path.startswith("/"):
        path = "/" + path
    with client as c:
        r = c.request(method, path, params=params, json=body if body is not None else None)
        r.raise_for_status()
        if not r.content:
            return {"status": r.status_code}
        try:
            return r.json() if isinstance(r.json(), dict) else {"data": r.json()}
        except Exception:
            return {"status": r.status_code, "text": r.text}


def _raw(name: str, client_factory, method: str, path: str,
         params: dict | None, body: Any, execute: bool) -> dict:
    method = method.upper()
    is_write = method in _WRITE_METHODS
    if is_write:
        if execute and not is_execute_allowed():
            return {"dryRun": True, "message": "WORKGRAPH_MODE is DRY_RUN."}
        if not execute:
            audit_log(name, {"method": method, "path": path}, "success")
            return {"dryRun": True, "method": method, "path": path, "params": params, "body": body}
    if MOCK_MODE:
        return {"mock": True, "method": method, "path": path}
    client = client_factory()
    if not client:
        raise ValueError(f"{name} client not configured.")
    result = _raw_call(client, method, path, params, body)
    if is_write:
        audit_log(name, {"method": method, "path": path}, "success")
    return result


def jira_raw(method: str, path: str, params: dict | None = None,
             body: Any = None, agile: bool = False, execute: bool = True) -> dict:
    """Call any Jira REST endpoint. path is relative to /rest/api/{version} (or /rest/agile/1.0 if agile=true)."""
    factory = jira_agile_client if agile else jira_client
    return _raw("jira_raw", factory, method, path, params, body, execute)


def bitbucket_raw(method: str, path: str, params: dict | None = None,
                  body: Any = None, execute: bool = True) -> dict:
    """Call any Bitbucket REST endpoint. path is relative to the Bitbucket API base."""
    return _raw("bitbucket_raw", bitbucket_client, method, path, params, body, execute)


def confluence_raw(method: str, path: str, params: dict | None = None,
                   body: Any = None, execute: bool = True) -> dict:
    """Call any Confluence REST endpoint. path is relative to /rest/api."""
    return _raw("confluence_raw", confluence_client, method, path, params, body, execute)


def bamboo_raw(method: str, path: str, params: dict | None = None,
               body: Any = None, execute: bool = True) -> dict:
    """Call any Bamboo REST endpoint. path is relative to /rest/api/latest."""
    return _raw("bamboo_raw", bamboo_client, method, path, params, body, execute)
