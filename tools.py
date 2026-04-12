"""Atlassian tool handlers: Jira, Bitbucket, Confluence, Bamboo.

Standalone — reads credentials from .env via config.py, no database needed.
"""
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
    jira_client, jira_agile_client, bitbucket_client, confluence_client, bamboo_client,
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
    execute: bool = False,
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
    execute: bool = False,
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


def jira_add_comment(issue_key: str, comment: str, execute: bool = False) -> dict:
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


def jira_create_subtasks(parent_issue_key: str, subtasks: list[dict], execute: bool = False) -> dict:
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


def jira_transition_issue(issue_key: str, transition_name: str, execute: bool = False) -> dict:
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
                       execute: bool = False) -> dict:
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
                       goal: str | None = None, execute: bool = False) -> dict:
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


def jira_move_issues_to_sprint(sprint_id: int, issue_keys: list[str], execute: bool = False) -> dict:
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


def jira_move_issues_to_backlog(issue_keys: list[str], execute: bool = False) -> dict:
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


def jira_move_issues_to_epic(epic_id_or_key: str, issue_keys: list[str], execute: bool = False) -> dict:
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
                     rank_after_issue: str | None = None, execute: bool = False) -> dict:
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


def bitbucket_pr_comment(repo_slug: str, pr_id: int, text: str, execute: bool = False) -> dict:
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


def bitbucket_approve_pr(repo_slug: str, pr_id: int, execute: bool = False) -> dict:
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


def bitbucket_merge_pr(repo_slug: str, pr_id: int, message: str | None = None, execute: bool = False) -> dict:
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


def confluence_create_page(space_key: str, title: str, content: str, parent_id: str | None = None, execute: bool = False) -> dict:
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


def confluence_update_page(page_id: str, title: str, content: str, version: int, execute: bool = False) -> dict:
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


def confluence_add_comment(page_id: str, comment: str, execute: bool = False) -> dict:
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


def bamboo_trigger_build(plan_key: str, variables: dict | None = None, execute: bool = False) -> dict:
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
