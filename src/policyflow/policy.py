from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Evidence
from .utils import sha256_text, stable_id


TOKEN_RE = re.compile(r"[a-zA-Z]+|\d+(?:\.\d+)?|[\u4e00-\u9fff]")


def semantic_tokens(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", text.casefold())
    atoms = TOKEN_RE.findall(normalized)
    chinese = "".join(atom for atom in atoms if "\u4e00" <= atom <= "\u9fff")
    bigrams = {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}
    return set(atoms) | bigrams


@dataclass(frozen=True)
class PolicyClause:
    clause_id: str
    title: str
    text: str
    keywords: tuple[str, ...]


class PolicyCorpus:
    def __init__(self, source: str | Path):
        self.source = Path(source)
        raw = self.source.read_text(encoding="utf-8")
        payload = json.loads(raw)
        self.policy_id = payload["policy_id"]
        self.version = payload["version"]
        self.title = payload["title"]
        self.source_hash = sha256_text(raw)
        self.clauses = [
            PolicyClause(
                clause_id=item["clause_id"],
                title=item["title"],
                text=item["text"],
                keywords=tuple(item.get("keywords", [])),
            )
            for item in payload["clauses"]
        ]

    def retrieve(self, query: str, limit: int = 4) -> list[Evidence]:
        query_tokens = semantic_tokens(query)
        scored: list[tuple[float, PolicyClause]] = []
        for clause in self.clauses:
            clause_tokens = semantic_tokens(
                " ".join((clause.clause_id, clause.title, clause.text, *clause.keywords))
            )
            overlap = len(query_tokens & clause_tokens)
            denom = math.sqrt(max(1, len(query_tokens)) * max(1, len(clause_tokens)))
            score = overlap / denom
            phrase_bonus = sum(0.08 for keyword in clause.keywords if keyword in query)
            scored.append((min(1.0, score + phrase_bonus), clause))
        scored.sort(key=lambda item: (-item[0], item[1].clause_id))
        evidence: list[Evidence] = []
        for score, clause in scored[:limit]:
            evidence.append(
                Evidence(
                    evidence_id=stable_id(
                        "ev", self.policy_id, self.version, clause.clause_id, self.source_hash
                    ),
                    policy_id=self.policy_id,
                    policy_version=self.version,
                    clause_id=clause.clause_id,
                    title=clause.title,
                    quote=clause.text,
                    score=round(max(score, 0.01), 4),
                    source_hash=self.source_hash,
                )
            )
        return evidence

    def retrieve_evidence_bundle(self, request_text: str) -> list[Evidence]:
        queries = (
            f"{request_text} 必要信息 成本中心",
            f"{request_text} 发票 有效凭证",
            f"{request_text} 住宿 每晚 超标 例外",
            "正式提交 工具调用前 财务审批",
            "幂等键 状态查询 补偿回滚 审计轨迹",
            "最小权限 执行代理 独立验证",
        )
        best: dict[str, Evidence] = {}
        for query in queries:
            for item in self.retrieve(query, limit=2):
                current = best.get(item.clause_id)
                if current is None or item.score > current.score:
                    best[item.clause_id] = item
        # Safety rules are always part of the evidence budget for a write-capable plan.
        for clause in self.clauses:
            if clause.clause_id not in best:
                item = next(
                    evidence
                    for evidence in self.retrieve(clause.title + " " + clause.text, limit=6)
                    if evidence.clause_id == clause.clause_id
                )
                best[clause.clause_id] = item
        return [best[key] for key in sorted(best)]

