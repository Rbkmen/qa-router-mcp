import json
import stat

import pytest

from qa_router_mcp.policy import PolicyError
from qa_router_mcp.store import ProposalStore


def test_pending_approve_and_reject_lifecycle(tmp_path):
    store = ProposalStore(tmp_path)

    first = store.add("Use concise case titles")
    second = store.add("Separate assumptions")

    assert [item.id for item in store.list_pending()] == [first.id, second.id]
    assert store.get_pending(first.id).text == "Use concise case titles"
    approved = store.approve(first.id)
    assert approved.status == "approved"
    assert store.reject(second.id) is True
    assert store.list_pending() == []
    saved = json.loads((tmp_path / "proposals.json").read_text())
    assert saved["approved"][0]["text"] == "Use concise case titles"


def test_forbidden_text_is_never_written(tmp_path):
    store = ProposalStore(tmp_path)

    with pytest.raises(PolicyError):
        store.add("Remember ABC-123")

    assert not (tmp_path / "proposals.json").exists()


def test_proposal_file_is_owner_only(tmp_path):
    data_dir = tmp_path / "private"
    store = ProposalStore(data_dir)

    store.add("Use concise case titles")

    directory_mode = stat.S_IMODE(data_dir.stat().st_mode)
    file_mode = stat.S_IMODE((data_dir / "proposals.json").stat().st_mode)
    assert directory_mode == 0o700
    assert file_mode == 0o600
