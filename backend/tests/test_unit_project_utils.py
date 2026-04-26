"""
Unit tests for backend/utils/project_utils.py.

These tests validate SQL execution order and boundary behavior without requiring
an actual database.
"""

from uuid import uuid4
from unittest.mock import AsyncMock
import asyncio

import pytest

from utils.project_utils import delete_project_data


def test_delete_project_data_executes_expected_sql_and_pid(monkeypatch):
	"""Deletion should run cleanup first, then issue all expected SQL statements."""
	fake_db = AsyncMock()
	project_id = uuid4()

	cleanup_mock = AsyncMock()
	monkeypatch.setattr("utils.project_utils.cleanup_project_s3", cleanup_mock)

	asyncio.run(delete_project_data(fake_db, project_id))

	cleanup_mock.assert_awaited_once_with(fake_db, project_id)

	executed_sql = [str(args[0]) for args, _kwargs in fake_db.execute.await_args_list]

	assert len(executed_sql) == 12
	assert "UPDATE commits SET parent_commit_id = NULL" in executed_sql[0]
	assert "UPDATE branches SET head_commit_id = NULL, parent_branch_id = NULL" in executed_sql[1]
	assert "UPDATE blender_objects SET parent_object_id = NULL" in executed_sql[2]
	assert "DELETE FROM blender_objects" in executed_sql[3]
	assert "DELETE FROM object_locks" in executed_sql[4]
	assert "DELETE FROM merge_conflicts" in executed_sql[5]
	assert "DELETE FROM commits" in executed_sql[6]
	assert "DELETE FROM branches" in executed_sql[7]
	assert "DELETE FROM project_metadata" in executed_sql[8]
	assert "DELETE FROM project_invitations" in executed_sql[9]
	assert "DELETE FROM project_members" in executed_sql[10]
	assert "DELETE FROM projects" in executed_sql[11]

	expected_pid = str(project_id)
	for call_obj in fake_db.execute.await_args_list:
		args = call_obj.args
		kwargs = call_obj.kwargs

		if len(args) >= 2:
			assert args[1] == {"pid": expected_pid}
		elif "params" in kwargs:
			assert kwargs["params"] == {"pid": expected_pid}
		else:
			assert False, f"Missing pid bind params for SQL call: {args[0]}"


def test_delete_project_data_propagates_cleanup_failure(monkeypatch):
	"""If S3 cleanup fails, SQL deletes should not run and the error should bubble up."""
	fake_db = AsyncMock()
	project_id = uuid4()

	cleanup_mock = AsyncMock(side_effect=RuntimeError("s3 is unavailable"))
	monkeypatch.setattr("utils.project_utils.cleanup_project_s3", cleanup_mock)

	with pytest.raises(RuntimeError, match="s3 is unavailable"):
		asyncio.run(delete_project_data(fake_db, project_id))

	cleanup_mock.assert_awaited_once_with(fake_db, project_id)
	fake_db.execute.assert_not_called()


def test_delete_project_data_does_not_commit_or_rollback(monkeypatch):
	"""Helper should leave transaction control to callers."""
	fake_db = AsyncMock()
	project_id = uuid4()

	cleanup_mock = AsyncMock()
	monkeypatch.setattr("utils.project_utils.cleanup_project_s3", cleanup_mock)

	asyncio.run(delete_project_data(fake_db, project_id))

	fake_db.commit.assert_not_called()
	fake_db.rollback.assert_not_called()
