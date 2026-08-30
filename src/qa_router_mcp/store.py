import json
import os
import secrets
from pathlib import Path

from qa_router_mcp.contracts import LearningProposal, ProposalStatus
from qa_router_mcp.policy import validate_learning_text


class ProposalStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "proposals.json"

    def _load(self) -> dict[str, list[dict[str, str]]]:
        if not self.path.exists():
            return {"pending": [], "approved": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, list[dict[str, str]]]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    def add(self, text: str) -> LearningProposal:
        proposal = LearningProposal(
            id=f"lp_{secrets.token_hex(8)}",
            text=validate_learning_text(text),
        )
        data = self._load()
        data["pending"].append(proposal.model_dump(mode="json"))
        self._save(data)
        return proposal

    def list_pending(self) -> list[LearningProposal]:
        return [LearningProposal.model_validate(item) for item in self._load()["pending"]]

    def get_pending(self, proposal_id: str) -> LearningProposal:
        match = next(
            (item for item in self._load()["pending"] if item["id"] == proposal_id),
            None,
        )
        if match is None:
            raise KeyError("proposal_not_found")
        return LearningProposal.model_validate(match)

    def approve(self, proposal_id: str) -> LearningProposal:
        data = self._load()
        match = next((item for item in data["pending"] if item["id"] == proposal_id), None)
        if match is None:
            raise KeyError("proposal_not_found")
        data["pending"] = [item for item in data["pending"] if item["id"] != proposal_id]
        approved = LearningProposal.model_validate(match).model_copy(
            update={"status": ProposalStatus.APPROVED}
        )
        data["approved"].append(approved.model_dump(mode="json"))
        self._save(data)
        return approved

    def reject(self, proposal_id: str) -> bool:
        data = self._load()
        remaining = [item for item in data["pending"] if item["id"] != proposal_id]
        found = len(remaining) != len(data["pending"])
        if found:
            data["pending"] = remaining
            self._save(data)
        return found
