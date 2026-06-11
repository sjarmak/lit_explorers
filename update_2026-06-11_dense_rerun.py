#!/usr/bin/env python3
"""Fold the 2026-06-11 dense-lane rerun finds into the explorer data blobs.

Papers surfaced by hybrid search after the INDUS dense lane was restored
(both source lit reviews were built in the lexical-only window). See
scix_experiments/results/litreview_rerun_2026-06-11.md.
"""

import json
import re

PROVENANCE = "Surfaced by the 2026-06-11 dense-lane rerun (missed in the lexical-only window)."


def arxiv_from_bibcode(bib):
    m = re.match(r"20\d{2}arXiv(\d{4})(\d{5,6})[A-Z]?$", bib)
    if not m:
        return None
    return f"{m.group(1)}.{m.group(2)}"


MEMORY_ADDS = [
    ("2025arXiv250206975P", "Position: Episodic Memory is the Missing Piece for Long-Term LLM Agents", "Pink, Mathis", 2025, 2, "architectures", "Position paper directly on the review's thesis."),
    ("2024arXiv240704363A", "AriGraph: Learning Knowledge Graph World Models with Episodic Memory for LLM Agents", "Anokhin, Petr", 2024, 12, "architectures", "KG world model + episodic memory architecture."),
    ("2025arXiv250308026T", "In Prospect and Retrospect: Reflective Memory Management for Long-term Personalized Dialogue", "Tan, Zhen", 2025, 2, "reflection-experience", "Reflective memory management for long-term personalization."),
    ("2025arXiv250303704D", "A Practical Memory Injection Attack against LLM Agents", "Dong, Shen", 2025, 0, "security-governance", "Concrete memory-injection attack."),
    ("2025arXiv250213172W", "Unveiling Privacy Risks in LLM Agent Memory", "Wang, Bo", 2025, 3, "security-governance", "Privacy leakage from agent memory stores."),
    ("2025arXiv250111739D", "Episodic memory in AI agents poses risks that should be studied and mitigated", "DeChant, Chad", 2025, 0, "security-governance", "Risk framing for episodic agent memory."),
    ("2021arXiv210707567X", "Beyond Goldfish Memory: Long-Term Open-Domain Conversation", "Xu, Jing", 2021, 67, "benchmarks-catalog", "Foundational long-term dialogue benchmark (pre-wave)."),
    ("2022arXiv221008750B", "Keep Me Updated! Memory Management in Long-term Conversations", "Bae, Sanghwan", 2022, 9, "benchmarks-catalog", "Early memory-management benchmark for long conversations."),
    ("2016Sci...352..305S", "A pathway for forgetting", "Stern, Peter", 2016, 0, "forgetting", "Neuroscience anchor: active forgetting pathway."),
    ("2019Sci...365R1260S", "A brain pathway for active forgetting", "Stern, Peter", 2019, 0, "forgetting", "Neuroscience anchor: active forgetting."),
    ("2020Sci...370S1428S", "Memory consolidation in the neocortex", "Stern, Peter", 2020, 0, "forgetting", "Neuroscience anchor: consolidation."),
    ("2020arXiv200207111U", "Targeted Forgetting and False Memory Formation in Continual Learners through Adversarial Backdoor Attacks", "Umer, Muhammad", 2020, 4, "forgetting", "Adversarial false-memory formation in continual learning."),
]

ORCH_ADDS = [
    ("2026arXiv260407494M", "Triage: Routing Software Engineering Tasks to Cost-Effective LLM Tiers via Code Quality Signals", "Madeyski, Lech", 2026, 0, "production", "Cost-tier routing for SWE tasks — closest single paper to the Gas City tiering problem."),
    ("2024arXiv241010347D", "A Unified Approach to Routing and Cascading for LLMs", "Dekoninck, Jasper", 2024, 2, "production", "Unifies routing + cascading formally."),
    ("2025arXiv250410681S", "EMAFusion: A Self-Optimizing System for Seamless LLM Selection and Integration", "Shah, Soham", 2025, 0, "production", "Self-optimizing LLM selection."),
    ("2024arXiv240702348K", "Agreement-Based Cascading for Efficient Inference", "Kolawole, Steven", 2024, 2, "production", "Cascade via inter-model agreement."),
    ("2024arXiv240600060W", "Cascade-Aware Training of Language Models", "Wang, Congchao", 2024, 4, "production", "Trains models with the cascade in mind."),
    ("2025arXiv250219335R", "I Know What I Don't Know: Improving Model Cascades Through Confidence Tuning", "Rabanser, Stephan", 2025, 0, "production", "Confidence tuning for cascade deferral."),
    ("2022arXiv220511747K", "BabyBear: Cheap inference triage for expensive language models", "Khalili, Leila", 2022, 5, "production", "Early inference-triage pattern."),
]


def update(path, adds):
    html_text = open(path).read()
    m = re.search(r'(<script id="data" type="application/json">)(.*?)(</script>)', html_text, re.S)
    d = json.loads(m.group(2))
    existing = {p["bibcode"] for p in d["papers"]}
    sections = {s["key"]: s for s in d["sections"]}
    # mirror branch naming from an existing paper in the same section
    n_added = 0
    for bib, title, author, year, cites, sect_key, note in adds:
        if bib in existing:
            continue
        sect = sections[sect_key]
        branch = None
        for p in d["papers"]:
            if p["bibcode"] in set(sect["papers"]) and p.get("branches"):
                branch = p["branches"][0]
                break
        paper = {
            "bibcode": bib,
            "title": title,
            "first_author": author,
            "year": year,
            "citation_count": cites,
            "branches": [branch or sect_key],
            "notes": f"{note} {PROVENANCE}",
            "arxiv": arxiv_from_bibcode(bib),
        }
        d["papers"].append(paper)
        if bib not in sect["papers"]:
            sect["papers"].append(bib)
        n_added += 1
    blob = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    open(path, "w").write(html_text[: m.start(2)] + blob + html_text[m.end(2):])
    print(f"{path.split('/')[-1]}: +{n_added} papers (now {len(d['papers'])})")


update("/home/ds/projects/lit_explorers/agentic_memory_explorer.html", MEMORY_ADDS)
update("/home/ds/projects/lit_explorers/multiagent_orchestration_explorer.html", ORCH_ADDS)
