#!/usr/bin/env python3
"""Build memory_design_explorer.html — a practitioner/industry companion to
agentic_memory_explorer.html (which covers the academic arXiv/ADS literature).

This explorer collects high-signal recent sources on agentic memory — product
launches, engineering write-ups, community field reports, newsletters, and the
design-relevant slice of recent research — and organizes them CATEGORICALLY by
memory *design consideration* for agents (retrieval, consolidation,
representation, temporality, forgetting, substrate, multi-agent, context,
evaluation, interop), not by product or vendor.

Sources were surfaced via the code-intel-digest local mirror (hourly-refreshed
Postgres) using the code-intel-copilot MCP. Each source carries a distillation
(key points), connections + takeaway, and related sources.

Run:  python3 build_memory_design_explorer.py
"""
import re
import json
import pathlib

HERE = pathlib.Path(__file__).parent
SHELL = HERE / "agentic_memory_explorer.html"
OUT = HERE / "memory_design_explorer.html"

# ---------------------------------------------------------------------------
# Categories — memory design considerations for agents (the "themes")
# ---------------------------------------------------------------------------
BRANCH_LABELS = {
    "retrieval": "Retrieval & Ranking",
    "consolidation": "Consolidation & Distillation",
    "representation": "Knowledge Representation",
    "temporal": "Temporality & Updating",
    "forgetting": "Forgetting & Lifecycle",
    "substrate": "Storage Substrate",
    "multiagent": "Multi-Agent & Shared Memory",
    "context": "Working Memory & Context",
    "evaluation": "Evaluation & Cost",
    "interop": "Interop, Schema & Governance",
    "foundations": "Foundations & Landscape",
}

# Per-category framing panels: consideration (subtopic), questions, tensions, takeaways
SECTION_META = {
    "retrieval": {
        "consideration": "How memories are surfaced into context at inference time: single- vs multi-channel retrieval, fusion across channels (e.g. Reciprocal Rank Fusion), keyword + semantic hybrids, and moving beyond raw cosine similarity toward user- and task-aware ranking.",
        "questions": [
            "One vector index, or parallel channels (recency, semantic, entity, summary, raw) fused with RRF?",
            "Is cosine similarity the right relevance signal, or does it surface the semantically-near-but-useless?",
            "When should the agent retrieve at all versus reason from what it already holds?",
        ],
        "tensions": [
            "More channels improve recall but multiply latency, cost, and the surface area for spurious matches.",
            "Embedding-only retrieval misses evidence that matters for user state/goals but isn't lexically or semantically close to the query.",
        ],
        "takeaways": [
            "The emerging production default is multi-channel parallel retrieval + RRF (Cloudflare ships exactly this).",
            "Precision of retrieval ≠ correctness of the final answer — measure them separately (see Evaluation & Cost).",
        ],
    },
    "consolidation": {
        "consideration": "Turning raw turns into durable memory: when (and whether) to run an LLM to extract/summarize, episodic traces vs consolidated abstractions, and the failure modes of letting an LLM continuously rewrite its own memory.",
        "questions": [
            "Eager (consolidate every turn) or lazy/recurrent (batch, on idle, on retrieval)?",
            "Keep raw episodic traces alongside distilled facts, or replace one with the other?",
            "What experience is even worth keeping — and how should it change behavior, not just fill storage?",
        ],
        "tensions": [
            "Eager per-turn extraction is the dominant cost driver; recurrence/batching cuts tokens but adds staleness.",
            "LLM-rewritten 'distilled truth' degrades over iterations (drift, context collapse) — distillation can make memory worse.",
        ],
        "takeaways": [
            "Two independent signals (Slack in production, 'Useful Memories Become Faulty' in research) say: validate consolidated memory and retain raw traces as ground truth.",
            "Frame the goal as memory *utility* (what changes behavior) over memory *capacity* (what fits).",
        ],
    },
    "representation": {
        "consideration": "The data structure memory lives in: flat vector RAG, entity–relationship knowledge graphs, atomic facts, event-grounded episodic records, or layered semantic/episodic/procedural stores.",
        "questions": [
            "Graph, vector, atomic facts, or events — and is the choice load-bearing or incidental?",
            "Do you model who/when/where (episodic coherence) or only what (semantic recall)?",
            "Is the atomic-fact paradigm (handcrafted prompts → compressed facts) actually the right primitive?",
        ],
        "tensions": [
            "KGs add an entity-extraction LLM step (latency, hallucinated edges, mega-hub blowup); flat RAG loses structure.",
            "Atomic facts are matchable but lossy; events/narratives are coherent but harder to index.",
        ],
        "takeaways": [
            "The field converged on entity–relationship graphs (Mem0, Zep, supermemory) — and a vocal minority argues that was a wrong turn.",
            "Cognitive-science-shaped layering (semantic + episodic + procedural) is a recurring practitioner pattern.",
        ],
    },
    "temporal": {
        "consideration": "Reasoning about time: validity intervals, bi-temporal modeling (event time vs ingestion time), contradiction/conflict resolution when facts update, and keeping a fact's timeline straight.",
        "questions": [
            "When a user's fact changes, does the system supersede, version, or silently overwrite?",
            "Do you track both when something was true and when you learned it (bi-temporal)?",
            "How are contradictions detected — formally, or left to retrieval to disambiguate?",
        ],
        "tensions": [
            "Vector stores have no native notion of supersession — the classic 'agent forgets the timeline' amnesia.",
            "Temporal graphs encode validity well but cost more to build and maintain.",
        ],
        "takeaways": [
            "Timeline/fact-update handling is the most-cited concrete weakness of vector-only memory in field reports.",
            "Bi-temporal modeling is moving from research into shipped products as a differentiator.",
        ],
    },
    "forgetting": {
        "consideration": "Lifecycle management: decay and salience, interference-based forgetting, consolidation/'sleep' phases, and the under-appreciated question of when memories *should* be forgotten (including for safety).",
        "questions": [
            "Does memory have an explicit lifecycle, or does it only grow until it rots?",
            "Is forgetting heuristic decay, or principled (interference, reconsolidation, salience)?",
            "When is forgetting a safety requirement, not just a cost optimization?",
        ],
        "tensions": [
            "Append-only stores accrue clutter, cap saturation, and stale context that pollutes retrieval.",
            "Aggressive forgetting risks dropping rare-but-critical facts; biologically-inspired schemes are largely unvalidated.",
        ],
        "takeaways": [
            "Forgetting is the least-measured part of agent memory — benchmarks barely test it (PersistBench is an early exception).",
            "Bio-inspired designs (sleep consolidation, interference, engram maturation) are proliferating, mostly as zero-citation preprints.",
        ],
    },
    "substrate": {
        "consideration": "Where bytes actually live: object storage for full transcripts (S3-style), managed session/filesystem state, self-hosted archives, and lightweight embedded stores (SQLite/FTS5) — the persistence layer beneath the semantic layer.",
        "questions": [
            "Keep full transcripts forever (cheap object storage) and derive memory, or only keep derived memory?",
            "Who owns durability across stop/resume — the runtime, or your store?",
            "Does this need a vector DB at all, or does SQLite + full-text search cover it?",
        ],
        "tensions": [
            "Full-transcript retention is cheap and audit-friendly but pushes the retrieval problem downstream.",
            "Managed session storage couples you to a runtime; embedded stores are portable but limited.",
        ],
        "takeaways": [
            "'Git + S3 as the memory layer' and self-hosted transcript archives are an active, deliberately-boring counter-movement to managed memory services.",
            "A common practitioner finding: many agents don't need a vector DB — FTS over a transcript store goes far.",
        ],
    },
    "multiagent": {
        "consideration": "Memory shared across agents and sessions: shared/team memory profiles, distributed multi-agent memory, and keeping long-running agent swarms coherent without dumping chat logs.",
        "questions": [
            "Is memory per-agent, per-user, or a shared team profile multiple agents read/write?",
            "How do you keep N long-running agents coherent without re-feeding raw history?",
            "What's the cost/accuracy curve of long-term memory across cloud+edge agents?",
        ],
        "tensions": [
            "Shared memory boosts coherence but raises write-conflict, staleness, and access-control questions.",
            "Distributed memory under network constraints trades accuracy for latency/cost in ways vendor benchmarks hide.",
        ],
        "takeaways": [
            "Shared memory profiles are now a headline feature (Cloudflare); Slack's lesson is 'structured memory + distilled truth' over accumulated logs.",
            "The mem0-vs-Graphiti distributed cost/accuracy study is the most decision-useful head-to-head for this layer.",
        ],
    },
    "context": {
        "consideration": "The working-memory boundary: what competes for the context window, context rot over long horizons, and selective/dependency-aware construction of what the model actually sees each step.",
        "questions": [
            "What are the components competing for the window, and what's each one's token budget?",
            "How do you fight context rot as histories grow — compress, retrieve, or restructure?",
            "Should context be rebuilt selectively per step rather than appended/slid?",
        ],
        "tensions": [
            "Sliding windows and prompt compression drop earlier structured info that later steps depend on.",
            "Iterative context rewriting causes brevity bias and context collapse (loses domain detail).",
        ],
        "takeaways": [
            "Long-term memory is one of ~7 consumers of the window — memory design can't be separated from context engineering.",
            "Dependency-structured / reflection-driven context management is the research response to context rot.",
        ],
    },
    "evaluation": {
        "consideration": "How we know any of this works: benchmarks beyond factual recall, separating retrieval-correctness from answer-correctness, cost/latency accounting, and production reality checks.",
        "questions": [
            "Does the benchmark test retrieval quality, or just whether the final answer was right?",
            "Are you measuring beyond surface factual recall (implicit user state, goals, values)?",
            "What does this actually cost at 100k+ users, not in a demo?",
        ],
        "tensions": [
            "A system that returns its whole belief store scores recall 1.0 and passes answer-quality evals — a unit-test/integration-test gap.",
            "Vendor-published evals optimize tokens/latency and omit system-level cost and accuracy.",
        ],
        "takeaways": [
            "Incumbent benchmarks (LoCoMo et al.) are saturating; precision-aware and beyond-factual benchmarks are the new frontier.",
            "Production field reports are blunt: 'just add a vector DB' breaks once agents run for a while (drift, repeated mistakes).",
        ],
    },
    "interop": {
        "consideration": "Portability and control: shared wire formats across memory frameworks, schema discipline, and governance/audit surfaces for what gets written and read.",
        "questions": [
            "Can you migrate memory between frameworks, or does switching mean rebuilding from scratch?",
            "Is the memory schema explicit and reviewable, or implicit and emergent?",
            "Is there a human-auditable surface over memory writes/reads?",
        ],
        "tensions": [
            "Every framework (Mem0, Letta/MemGPT, Cognee, Zep/Graphiti, MemoryOS) ships bespoke storage + vocabulary — no shared format.",
            "Governance/audit is almost entirely absent, yet memory directly shapes agent behavior.",
        ],
        "takeaways": [
            "'Memory quality = schema quality' is becoming a stated principle.",
            "A vendor-neutral wire format is being proposed precisely because migration and audit are currently impossible.",
        ],
    },
    "foundations": {
        "consideration": "Orienting maps: surveys that taxonomize the field, and the managed-service landscape (Cloudflare, Mem0, Zep, LangMem, Letta) that frames the build-vs-buy decision.",
        "questions": [
            "What's the shared vocabulary — memory forms (logs/weights/vectors) × functions (factual/experiential/working)?",
            "Build a memory layer, or adopt a managed service?",
            "Which incumbent assumptions are already being challenged?",
        ],
        "tensions": [
            "The field is fragmented: same words, different implementations and eval protocols.",
            "Managed services accelerate shipping but lock in representation, retrieval, and governance choices.",
        ],
        "takeaways": [
            "Start from a survey taxonomy before picking a store — it makes the design space legible.",
            "The managed-memory market formed fast (2025–2026); the surveys formalized the field almost in parallel.",
        ],
    },
}

# ---------------------------------------------------------------------------
# Sources. note: {b: branch, k: distillation/key points, r: connections + takeaway}
# related: list of source ids.  type: Product|Engineering|Research|Community|Newsletter|Survey
# ---------------------------------------------------------------------------
S = [
    # ---------- Foundations & Landscape ----------
    dict(id="cf-agent-memory-blog", title="Agents that remember: introducing Agent Memory",
         source="Cloudflare Blog", author="Tyson Trautmann", date="2026-04", type="Product",
         url="https://blog.cloudflare.com/introducing-agent-memory/",
         branches=["foundations", "retrieval", "multiagent"],
         notes=[
            dict(b="foundations", k="Cloudflare's managed memory service: extracts structured memories from agent conversations and serves them on demand, with shared memory profiles so teams of agents read common knowledge. Framed around getting the right info into context even as windows pass 1M tokens.",
                 r="The most complete public blueprint for the shape of service described in many internal designs (sessions → turns → consolidated docs → multi-channel search). Build-vs-buy anchor for the whole map."),
            dict(b="retrieval", k="Retrieval is five-channel parallel + Reciprocal Rank Fusion (RRF) — not a single vector lookup.",
                 r="Concrete, shipped instance of the multi-channel+fusion pattern; copy the channel decomposition. Connects directly to [precision-belief-state] on why channel fusion still needs retrieval-quality measurement."),
            dict(b="multiagent", k="Shared memory profiles let multiple agents access common knowledge.",
                 r="Productizes team/shared memory; pair with Slack's distilled-truth lesson for the coherence side."),
         ],
         related=["cf-agent-memory-infoq", "slack-context", "memory-survey-hu", "memorywire"]),

    dict(id="cf-agent-memory-infoq", title="Cloudflare Announces Agent Memory, a Managed Persistent Memory Service",
         source="InfoQ", author="Steef-Jan Wiggers", date="2026-04", type="Engineering",
         url="https://www.infoq.com/news/2026/04/cloudflare-agent-memory-beta/",
         branches=["foundations", "retrieval"],
         notes=[
            dict(b="foundations", k="Third-party writeup of Cloudflare Agent Memory (private beta). Names the competitive set explicitly: Mem0, Zep, LangMem, Letta.",
                 r="Use this to scope the managed-memory market in one line. Takeaway: the named incumbents are exactly the frameworks the wire-format work [memorywire] says can't interoperate."),
            dict(b="retrieval", k="Confirms five-channel parallel retrieval with RRF and structured-memory extraction.",
                 r="Independent confirmation of the architecture in [cf-agent-memory-blog]."),
         ],
         related=["cf-agent-memory-blog", "memorywire", "mem0-vs-graphiti"]),

    dict(id="memory-survey-hu", title="Memory in the Age of AI Agents (survey)",
         source="arXiv / ADS", author="Hu et al. (50 authors)", date="2026-03", type="Survey",
         url="https://ui.adsabs.harvard.edu/abs/2025arXiv251213564H",
         branches=["foundations"],
         notes=[
            dict(b="foundations", k="Large multi-institution survey formalizing agent memory as a core capability. Unifies a fragmented field into a taxonomy of memory forms (token-level logs vs parametric weights vs latent vectors) × functions (factual knowledge vs experiential learning vs working scratchpad).",
                 r="The canonical framing doc — read first to make the rest of the map legible. Its forms×functions grid is a good axis for any design review. Connects to every other category as the orienting vocabulary."),
         ],
         related=["llmwatch-survey", "graph-memory-survey", "memorywire"]),

    dict(id="llmwatch-survey", title="AI Agents of the Week: Memory as a First-Class Citizen",
         source="LLM Watch", author="Pascal Biese", date="2025-12", type="Newsletter",
         url="https://www.llmwatch.com/p/ai-agents-of-the-week-papers-you-afa",
         branches=["foundations", "consolidation"],
         notes=[
            dict(b="foundations", k="Newsletter roundup that flagged the agent-memory survey wave and frameworks like MemVerse (fast parametric recall + hierarchical retrieval) and WorldMM (multimodal experience consolidation).",
                 r="Good lay-of-the-land pulse on what the research community foregrounded as memory went mainstream. Lighter signal than the survey itself."),
         ],
         related=["memory-survey-hu"]),

    dict(id="twilio-conversation-memory", title="What Is Twilio Conversation Memory?",
         source="Twilio Blog", author="Sean Spediacci", date="2026-05", type="Product",
         url="https://www.twilio.com/en-us/blog/products/launches/conversation-memory",
         branches=["foundations"],
         notes=[
            dict(b="foundations", k="Productized 'memory across conversations' for Twilio's agent/CX stack.",
                 r="Data point that conversation memory is now table-stakes in vertical comms platforms, not just AI-infra vendors. Lower technical depth; useful as market evidence."),
         ],
         related=["cf-agent-memory-blog"]),

    # ---------- Retrieval & Ranking ----------
    dict(id="adamem", title="AdaMem: Adaptive User-Centric Memory for Long-Horizon Dialogue Agents",
         source="arXiv / ADS", author="Yan et al.", date="2026-03", type="Research",
         url="https://ui.adsabs.harvard.edu/abs/2026arXiv260316496Y",
         branches=["retrieval"],
         notes=[
            dict(b="retrieval", k="Argues memory systems lean too hard on semantic similarity (misses user-centric evidence) and store related experiences as isolated fragments. Proposes adaptive, user-centric retrieval.",
                 r="Direct critique of cosine-similarity-as-relevance — the case for ranking on user state/goals, not just embedding distance. Connects to AdaMem's fragmentation point and [cast-episodic]'s coherence argument."),
         ],
         related=["cast-episodic", "precision-belief-state", "cf-agent-memory-blog"]),

    dict(id="retrieve-or-think", title="To Retrieve or To Think? An Agentic Approach for Context Evolution",
         source="arXiv", author="Chen et al.", date="2026-01", type="Research",
         url="https://arxiv.org/abs/2601.08747",
         branches=["retrieval", "context"],
         notes=[
            dict(b="retrieval", k="RAG-at-every-step is a rigid brute-force strategy that wastes compute and can degrade performance. Proposes an agent that decides when to retrieve vs reason from current context.",
                 r="Reframes retrieval as a policy decision, not a reflex — the cost/quality lever most retrieval designs ignore. Bridges Retrieval and Working-Memory categories."),
         ],
         related=["arc-context", "adamem"]),

    dict(id="hins", title="HiNS: Hierarchical Negative Sampling for Memory Retrieval Embedding Models",
         source="arXiv", author="Tian et al.", date="2026-01", type="Research",
         url="https://arxiv.org/abs/2601.14857",
         branches=["retrieval"],
         notes=[
            dict(b="retrieval", k="Memory retrieval depends on the embedding model; existing training ignores the hierarchical difficulty of negatives (close distractors vs easy negatives) in human–agent interaction. HiNS trains on that hierarchy.",
                 r="The under-discussed layer beneath retrieval design: the embedding model itself decides what 'similar' means. Improving it is orthogonal to channel/fusion choices."),
         ],
         related=["adamem", "precision-belief-state"]),

    dict(id="precision-belief-state", title="Structured Belief State and the First Precision-Aware Benchmark for LLM Memory Retrieval",
         source="arXiv", author="Jeffrey Flynt", date="2026-05", type="Research",
         url="https://arxiv.org/abs/2605.11325",
         branches=["retrieval", "evaluation"],
         notes=[
            dict(b="retrieval", k="Observes that returning the entire belief store yields recall 1.0 and passes answer-quality evals — so answer-correctness can't validate a retrieval system. Introduces a precision-aware retrieval benchmark over a structured belief state.",
                 r="The cleanest statement of the retrieval-vs-answer-correctness gap (the 'unit test vs integration test' framing). A north star for evaluating any multi-channel retriever. Bridges Retrieval and Evaluation."),
         ],
         related=["cf-agent-memory-blog", "locomo-plus", "engramabench", "mem0-vs-graphiti"]),

    # ---------- Consolidation & Distillation ----------
    dict(id="slack-context", title="How Slack Manages Context in Long-running Multi-agent Systems",
         source="InfoQ", author="Sergio De Simone", date="2026-04", type="Engineering",
         url="https://www.infoq.com/news/2026/04/slack-agent-context-management/",
         branches=["consolidation", "multiagent"],
         notes=[
            dict(b="consolidation", k="Slack engineering moved away from accumulating chat logs toward structured memory, validation, and 'distilled truth' to keep long-running agents coherent and accurate.",
                 r="Production validation of the consolidation thesis — and crucially, they *validate* the distilled memory rather than trusting LLM rewrites. Read alongside [useful-memories-faulty], which explains why that validation step is necessary."),
            dict(b="multiagent", k="Targets coherence across long-running multi-agent systems specifically.",
                 r="Pairs with Cloudflare shared profiles as the two main public takes on multi-agent memory."),
         ],
         related=["useful-memories-faulty", "cf-agent-memory-blog", "recmem", "compiled-memory"]),

    dict(id="useful-memories-faulty", title="Useful Memories Become Faulty When Continuously Updated by LLMs",
         source="arXiv", author="Zhang et al.", date="2026-05", type="Research",
         url="https://arxiv.org/abs/2605.12978",
         branches=["consolidation", "temporal"],
         notes=[
            dict(b="consolidation", k="Distinguishes episodic traces (raw trajectories) from consolidated abstractions (schema-like lessons). Shows that when an LLM repeatedly rewrites a textual memory bank, the consolidated memory degrades over time.",
                 r="The strongest research caution against LLM-driven consolidation as your primary store. Direct argument to keep raw traces (see Substrate) as ground truth and treat distillation as lossy. Pairs with Slack's validation step."),
         ],
         related=["slack-context", "beyond-atomic-facts", "git-s3-memory", "recmem"]),

    dict(id="recmem", title="RecMem: Recurrence-based Memory Consolidation for Long-Running LLM Agents",
         source="arXiv", author="Dai et al.", date="2026-05", type="Research",
         url="https://arxiv.org/abs/2605.16045",
         branches=["consolidation"],
         notes=[
            dict(b="consolidation", k="Critiques 'eager' consolidation (invoke an LLM on every incoming interaction to extract memory) as a major token-cost driver. Proposes recurrence-based consolidation that batches/defers the work.",
                 r="The cost knob for consolidation. Connects to [memfly] and [simplemem] as the efficiency cluster; the tradeoff is staleness vs token spend."),
         ],
         related=["simplemem", "memfly", "useful-memories-faulty"]),

    dict(id="simplemem", title="SimpleMem: Efficient Lifelong Memory for LLM Agents",
         source="arXiv / ADS", author="Liu et al.", date="2026-01", type="Research",
         url="https://ui.adsabs.harvard.edu/abs/2026arXiv260102553L",
         branches=["consolidation"],
         notes=[
            dict(b="consolidation", k="Frames the dilemma: retain full history (redundancy) vs iterative reasoning to filter noise (token cost). Proposes an efficient middle path for lifelong memory.",
                 r="Clean statement of the consolidation cost/coverage tradeoff that recurs across the category. Sits with [recmem]/[memfly] on efficiency."),
         ],
         related=["recmem", "memfly", "evermemos"]),

    dict(id="memfly", title="MemFly: On-the-Fly Memory Optimization via Information Bottleneck",
         source="arXiv / ADS", author="Zhang et al.", date="2026-02", type="Research",
         url="https://ui.adsabs.harvard.edu/abs/2026arXiv260207885Z",
         branches=["consolidation"],
         notes=[
            dict(b="consolidation", k="Uses an information-bottleneck objective to balance compressing redundant info against keeping retrieval precise, optimizing memory on the fly.",
                 r="Gives the consolidation tradeoff a principled objective rather than a heuristic. Theoretical companion to [recmem]/[simplemem]."),
         ],
         related=["recmem", "simplemem"]),

    dict(id="amory", title="Amory: Coherent Narrative-Driven Agent Memory through Agentic Reasoning",
         source="arXiv", author="Zhou et al.", date="2026-01", type="Research",
         url="https://arxiv.org/abs/2601.06282",
         branches=["consolidation", "representation"],
         notes=[
            dict(b="consolidation", k="Argues current frameworks fragment conversations into isolated embeddings or graph nodes; proposes building a coherent narrative via agentic reasoning instead.",
                 r="Bridges consolidation and representation: the unit of memory should preserve narrative coherence, not just be a retrievable shard. Connects to [cast-episodic]'s who/when/where stance."),
         ],
         related=["cast-episodic", "useful-memories-faulty", "kg-wrong-abstraction"]),

    dict(id="compiled-memory", title="Compiled Memory / Atlas: More Precise Instructions, Not More Information",
         source="arXiv", author="Rhodes & Kang", date="2026-03", type="Research",
         url="https://arxiv.org/abs/2603.15666",
         branches=["consolidation"],
         notes=[
            dict(b="consolidation", k="Shifts the question from memory *management* (retrieve/page within a budget) to memory *utility*: what experience is worth keeping, and how it should change agent behavior. 'Atlas' compiles accumulated experience into precise instructions.",
                 r="Reframes the goal of consolidation around behavior change, not storage. Strong complement to the cost cluster — efficiency is moot if you keep the wrong things."),
         ],
         related=["recmem", "slack-context", "useful-memories-faulty"]),

    dict(id="evermemos", title="EverMemOS: A Self-Organizing Memory Operating System",
         source="arXiv / ADS", author="Hu et al.", date="2026-01", type="Research",
         url="https://ui.adsabs.harvard.edu/abs/2026arXiv260102163H",
         branches=["consolidation", "representation"],
         notes=[
            dict(b="consolidation", k="Notes most memory systems store isolated records and retrieve fragments, limiting consolidation of evolving user state and conflict resolution. Proposes a self-organizing memory OS for structured long-horizon reasoning.",
                 r="'Memory OS' framing that ties consolidation to conflict resolution (Temporality) and structure (Representation). Conceptual cousin of Letta/MemGPT-style OS metaphors."),
         ],
         related=["simplemem", "dmem", "human-inspired-mem"]),

    dict(id="dmem", title="D-Mem: A Dual-Process Memory System for LLM Agents",
         source="arXiv", author="You et al.", date="2026-03", type="Research",
         url="https://arxiv.org/abs/2603.18631",
         branches=["consolidation", "representation"],
         notes=[
            dict(b="consolidation", k="Critiques incremental per-turn extraction/update; proposes a dual-process design (fast + slow paths) for high-fidelity memory access over long horizons.",
                 r="Dual-process (System-1/System-2) is a recurring shape; here applied to when to consolidate cheaply vs reason deeply. Connects to [retrieve-or-think]'s retrieve-vs-think policy."),
         ],
         related=["retrieve-or-think", "evermemos", "human-inspired-mem"]),

    # ---------- Knowledge Representation ----------
    dict(id="graph-memory-survey", title="Graph-based Agent Memory: Taxonomy, Techniques, and Applications",
         source="arXiv / ADS", author="Yang et al.", date="2026-02", type="Survey",
         url="https://ui.adsabs.harvard.edu/abs/2026arXiv260205665Y",
         branches=["representation"],
         notes=[
            dict(b="representation", k="The survey of graph-structured agent memory: why graphs (relational modeling, knowledge accumulation, self-evolution), the technique landscape, and applications across multi-turn dialogue, games, and scientific discovery.",
                 r="The map of the KG-memory design space — read before committing to or rejecting a graph. Read against [kg-wrong-abstraction] for the dissent."),
         ],
         related=["kg-wrong-abstraction", "gaama", "personalai", "memory-survey-hu"]),

    dict(id="kg-wrong-abstraction", title="Hot take: knowledge graphs are the wrong abstraction for agent memory",
         source="Reddit r/LLMDevs", author="u/Expert-Address-2918", date="2026-04", type="Community",
         url="https://www.reddit.com/r/LLMDevs/comments/1so9rvk/",
         branches=["representation"],
         notes=[
            dict(b="representation", k="Argues the field over-converged on entity–relationship graphs (Mem0, Zep, supermemory). Costs flagged: an extra entity-extraction LLM step (latency) and hallucinated edges that fabricate connections — when the real job is fast retrieval of the right past context.",
                 r="The sharpest practitioner counter-argument to KGs. Worth weighing before adopting a graph layer; [gaama] partially answers it (mega-hub fix), [graph-memory-survey] is the steelman."),
         ],
         related=["graph-memory-survey", "gaama", "git-s3-memory", "what-i-learned-coding-agent"]),

    dict(id="gaama", title="GAAMA: Graph Augmented Associative Memory for Agents",
         source="arXiv", author="Paul et al.", date="2026-03", type="Research",
         url="https://arxiv.org/abs/2603.27910",
         branches=["representation"],
         notes=[
            dict(b="representation", k="Flat RAG loses structural relationships; entity-centric KGs suffer 'mega-hub' effects (a few nodes accrue too many edges). GAAMA proposes graph-augmented associative memory to keep structure without the hub blowup.",
                 r="A concrete fix for one of the KG failure modes [kg-wrong-abstraction] complains about. Useful if you want graph structure but fear scaling pathologies."),
         ],
         related=["kg-wrong-abstraction", "graph-memory-survey", "personalai"]),

    dict(id="personalai", title="PersonalAI: Systematic Comparison of KG Storage and Retrieval for Personalized LLM Agents",
         source="arXiv", author="Menschikov et al.", date="2026-03", type="Research",
         url="https://arxiv.org/abs/2506.17001",
         branches=["representation", "evaluation"],
         notes=[
            dict(b="representation", k="Systematically compares knowledge-graph storage/retrieval approaches for personalized agents, against the backdrop that RAG improves factual accuracy but lacks structured memory and doesn't scale in complex long-term settings.",
                 r="The closest thing to an apples-to-apples KG-design comparison; pairs with [mem0-vs-graphiti] (vector-vs-graph in distributed setting) for store-selection decisions."),
         ],
         related=["graph-memory-survey", "gaama", "mem0-vs-graphiti"]),

    dict(id="beyond-atomic-facts", title="Rethinking How to Remember: Beyond Atomic Facts in Lifelong LLM Agent Memory",
         source="arXiv", author="Sun et al.", date="2026-05", type="Research",
         url="https://arxiv.org/abs/2605.19952",
         branches=["representation", "consolidation"],
         notes=[
            dict(b="representation", k="Critiques the dominant extracted-fact paradigm: handcrafted static prompts compress raw dialogue into atomic facts that are stored, matched, and injected — losing the ability to reason deeply over history. Proposes going beyond atomic facts.",
                 r="The most on-the-nose challenge to atomic-facts-as-primitive. Read before committing to a fact-extraction pipeline; connects to [amory] (narrative) and [cast-episodic] (events) as richer alternatives."),
         ],
         related=["amory", "cast-episodic", "useful-memories-faulty"]),

    dict(id="cast-episodic", title="CAST: Character-and-Scene Episodic Memory for Agents",
         source="arXiv", author="Ma et al.", date="2026-02", type="Research",
         url="https://arxiv.org/abs/2602.06051",
         branches=["representation"],
         notes=[
            dict(b="representation", k="Most agent memory emphasizes semantic recall and stores experience as key-value/vector/graph, which struggles to represent coherent events. CAST models episodic memory grounded in who/when/where (characters and scenes).",
                 r="The episodic-coherence counterpoint to fact/vector stores; aligns with [amory] (narrative) and [adamem] (fragmentation). Connects to Temporality via the 'when' grounding."),
         ],
         related=["amory", "beyond-atomic-facts", "three-layer-memory"]),

    dict(id="three-layer-memory", title="How I implemented 3-layer memory for LLM agents (semantic + episodic + procedural)",
         source="Reddit r/LLMDevs", author="u/No_Advertising2536", date="2026-03", type="Community",
         url="https://www.reddit.com/r/LLMDevs/comments/1s8njqy/",
         branches=["representation"],
         notes=[
            dict(b="representation", k="Practitioner build motivated by agents repeating mistakes (deploy → forget migrations → DB crash). Implements the cognitive-science triad — semantic (what you know), episodic (what happened), procedural (how to do things) — and open-sources it.",
                 r="Grassroots evidence that the semantic/episodic/procedural layering from research is being adopted by builders. Pairs with [cast-episodic] (episodic) and the procedural-skills theme of the academic explorer."),
         ],
         related=["cast-episodic", "what-i-learned-coding-agent", "unified-memory-stack"]),

    # ---------- Temporality & Updating ----------
    dict(id="temporal-kg-pomdp", title="Temporal Knowledge-Graph Memory in a Partially Observable Environment",
         source="arXiv", author="Kim, François-Lavet, Cochez", date="2026-02", type="Research",
         url="https://arxiv.org/abs/2408.05861",
         branches=["temporal", "representation"],
         notes=[
            dict(b="temporal", k="Agents in partially observable environments need persistent memory to integrate observations over time; KGs naturally represent evolving state. Introduces a benchmark where both world dynamics and the agent's memory are explicitly graph-shaped.",
                 r="Grounds temporal-KG memory in a controllable evaluation setting — rare for this topic. Connects temporality to representation: time is modeled as graph evolution."),
         ],
         related=["graph-memory-survey", "aurra-bitemporal", "yourmemory"]),

    dict(id="aurra-bitemporal", title="Aurra's bi-temporal memory vs Mem0 — is Mem0 behind?",
         source="Reddit r/LLMDevs", author="u/Jst_Qrius", date="2026-05", type="Community",
         url="https://www.reddit.com/r/LLMDevs/comments/1t3pj9e/",
         branches=["temporal"],
         notes=[
            dict(b="temporal", k="A Mem0 user hits the classic wall: agents 'forget' the timeline of facts (amnesia when a user updates info). Tries Aurra's bi-temporal memory (tracks event time vs ingestion time) and reports it handles fact updates better.",
                 r="Field evidence that fact-update/timeline handling is the concrete weakness pushing people off vector-only stores — and that bi-temporal modeling is the differentiator. Connects to [useful-memories-faulty] (why naive updates fail)."),
         ],
         related=["useful-memories-faulty", "temporal-kg-pomdp", "openmemory-mem0"]),

    dict(id="yourmemory", title="Show HN: YourMemory — persistent memory layer with temporal reasoning",
         source="Hacker News", author="SachitRafa", date="2026-05", type="Community",
         url="https://news.ycombinator.com/item?id=48270325",
         branches=["temporal", "forgetting"],
         notes=[
            dict(b="temporal", k="Biologically-inspired decay plus temporal reasoning; a CLI to infer knowledge from stored memory with zero token/LLM cost, plus a dashboard that can double as an audit trail.",
                 r="Combines temporality with forgetting (decay) and nods at governance (audit trail). Representative of the 'zero-LLM, local, dashboarded' indie memory wave alongside [superlocalmemory]."),
         ],
         related=["superlocalmemory", "aurra-bitemporal", "human-inspired-mem"]),

    # ---------- Forgetting & Lifecycle ----------
    dict(id="human-inspired-mem", title="Human-Inspired Memory Architecture for LLM Agents",
         source="arXiv", author="Kerestecioglu et al.", date="2026-05", type="Research",
         url="https://arxiv.org/abs/2605.08538",
         branches=["forgetting", "representation"],
         notes=[
            dict(b="forgetting", k="Six cognitive mechanisms: sleep-phase consolidation, interference-based forgetting, engram maturation, reconsolidation upon retrieval, and entity knowledge graphs — a principled lifecycle rather than heuristic decay.",
                 r="The most complete bio-grounded lifecycle proposal; turns 'forgetting' from a TTL into a set of mechanisms. Unvalidated at scale, like most of this cluster — weigh against eval scarcity ([persistbench])."),
         ],
         related=["superlocalmemory", "persistbench", "yourmemory", "dmem"]),

    dict(id="superlocalmemory", title="SuperLocalMemory V3.3: 'The Living Brain' — bio-inspired forgetting, multi-channel retrieval, zero-LLM",
         source="arXiv", author="Bhardwaj", date="2026-04", type="Research",
         url="https://arxiv.org/abs/2604.04514",
         branches=["forgetting", "retrieval"],
         notes=[
            dict(b="forgetting", k="Opens on the paradox: coding agents have vast parametric knowledge yet can't remember an hour ago. Critiques single-channel vector retrieval that needs cloud LLMs and implements no cognitive processes. Adds biologically-inspired forgetting, cognitive quantization, and multi-channel retrieval — all local/zero-LLM.",
                 r="Bundles forgetting + multi-channel retrieval + local-first into one system; the indie counterpart to Cloudflare's managed multi-channel approach. Connects to [yourmemory] (zero-LLM, local) and [git-s3-memory] (local-first ethos)."),
         ],
         related=["yourmemory", "human-inspired-mem", "cf-agent-memory-blog"]),

    dict(id="persistbench", title="PersistBench: When Should Long-Term Memories Be Forgotten by LLMs?",
         source="arXiv / ADS", author="Pulipaka et al.", date="2026-02", type="Research",
         url="https://ui.adsabs.harvard.edu/abs/2026arXiv260201146P",
         branches=["forgetting", "evaluation"],
         notes=[
            dict(b="forgetting", k="Persisting facts (e.g. 'user is vegetarian') aids personalization but also introduces safety risks that are largely overlooked. PersistBench measures when persistence becomes a liability and when memories *should* be forgotten.",
                 r="Reframes forgetting as a safety requirement, not just hygiene — and is one of the only benchmarks targeting forgetting at all. Bridges Forgetting and Evaluation; pairs with the 'forgetting is unmeasured' gap."),
         ],
         related=["human-inspired-mem", "locomo-plus", "engramabench"]),

    # ---------- Storage Substrate ----------
    dict(id="git-s3-memory", title="Git and S3 as the memory layer for agents",
         source="Hacker News / X", author="VijitDhingra1", date="2026-06", type="Community",
         url="https://news.ycombinator.com/item?id=48389370",
         branches=["substrate"],
         notes=[
            dict(b="substrate", k="Proposes plain Git + S3 as the durable memory substrate for agents — versioned, cheap, auditable object storage rather than a bespoke memory service.",
                 r="The freshest signal in the 'deliberately boring substrate' movement: keep full history cheaply, derive memory downstream. Counterpoint to managed services; pairs with [chatdb] and [what-i-learned-coding-agent]. (Low vote count — early/thin.)"),
         ],
         related=["chatdb-archive", "what-i-learned-coding-agent", "agentcore-session-storage", "useful-memories-faulty"]),

    dict(id="agentcore-session-storage", title="Amazon Bedrock AgentCore Runtime: managed session storage for persistent filesystem state",
         source="AWS What's New", author="AWS", date="2026-03", type="Product",
         url="https://aws.amazon.com/about-aws/whats-new/2026/03/bedrock-agentcore-runtime-session-storage/",
         branches=["substrate"],
         notes=[
            dict(b="substrate", k="Managed session storage (preview) persists an agent's filesystem state — code, installed packages, generated artifacts — across stop/resume cycles, which was previously lost.",
                 r="A different memory layer than semantic memory: durable working state, not distilled knowledge. Important to keep distinct in a design — the runtime can own session durability while your store owns knowledge."),
         ],
         related=["git-s3-memory", "context-window-components"]),

    dict(id="chatdb-archive", title="Self-hosted archive for all AI conversations (hybrid keyword + semantic search)",
         source="Reddit r/vibecoding", author="u/Sufficient_Guard9850", date="2026-03", type="Community",
         url="https://www.reddit.com/r/vibecoding/comments/1rhjlzs/",
         branches=["substrate", "retrieval"],
         notes=[
            dict(b="substrate", k="'ChatDB' — a self-hosted conversation archive across multiple AI apps, with a proper hybrid keyword + semantic search interface, deployable free on Cloudflare.",
                 r="Demonstrates the storage+search split: keep transcripts, layer hybrid retrieval on top. The hybrid (lexical+semantic) retrieval choice connects to the Retrieval category."),
         ],
         related=["git-s3-memory", "what-i-learned-coding-agent", "chatgpt-library"]),

    dict(id="what-i-learned-coding-agent", title="What I Learned Building a Memory System for My Coding Agent (SQLite, FTS5)",
         source="Reddit r/ClaudeCode", author="u/Medium_Island_2795", date="2026-02", type="Community",
         url="https://www.reddit.com/r/ClaudeCode/comments/1r1w397/",
         branches=["substrate"],
         notes=[
            dict(b="substrate", k="Argues many agents don't need a vector DB: SQLite + FTS5 full-text search covers a lot, with far less operational weight.",
                 r="The pragmatic floor of the substrate spectrum — strong reminder to not reach for pgvector/graph DBs by default. Echoes [kg-wrong-abstraction]'s 'simpler is fine' instinct."),
         ],
         related=["git-s3-memory", "chatdb-archive", "kg-wrong-abstraction", "what-using-production"]),

    dict(id="chatgpt-library", title="OpenAI rolls out ChatGPT Library to store your personal files",
         source="TLDR Newsletter", author="TLDR AI", date="2026-03", type="Newsletter",
         url="https://links.tldrnewsletter.com/jI4fQv",
         branches=["substrate"],
         notes=[
            dict(b="substrate", k="Consumer-facing personal file/content store inside ChatGPT.",
                 r="Market signal that 'remember my stuff' is becoming a default consumer expectation, shaping what agents are assumed to retain. Low technical depth."),
         ],
         related=["chatdb-archive"]),

    dict(id="memorybank-rust", title="Show HN: MemoryBank — unify memory across agents, improve context rot (Rust)",
         source="Hacker News", author="feelingsonice", date="2026-04", type="Community",
         url="https://github.com/feelingsonice/MemoryBank",
         branches=["substrate", "multiagent"],
         notes=[
            dict(b="substrate", k="Local memory layer (Rust) motivated by memory being tool-locked (re-explaining things when switching tools/sessions) and by markdown-append memories that dump everything into context and rot.",
                 r="Cross-tool, local substrate aimed squarely at context rot and portability — connects to Interop ([memorywire], [unified-memory-stack]) and Working-Memory/context-rot."),
         ],
         related=["unified-memory-stack", "memorywire", "context-window-components"]),

    # ---------- Multi-Agent & Shared Memory ----------
    dict(id="mem0-vs-graphiti", title="Cost and Accuracy of Long-Term Memory in Distributed Multi-Agent Systems",
         source="arXiv", author="Wolff & Bennati", date="2026-06", type="Research",
         url="https://arxiv.org/abs/2601.07978",
         branches=["multiagent", "evaluation"],
         notes=[
            dict(b="multiagent", k="A testbed for long-term memory in distributed multi-agent systems (cloud+edge), directly comparing Mem0 (vector-based) vs Graphiti/Zep (graph-based) on system-level cost and accuracy — not just the tokens/latency that framework-published evals report.",
                 r="The single most decision-useful head-to-head for splitting work between a vector store and a graph store in a multi-agent setting. Bridges Multi-Agent and Evaluation; complements [personalai] (KG-internal comparison)."),
         ],
         related=["personalai", "precision-belief-state", "slack-context", "cf-agent-memory-blog"]),

    # ---------- Working Memory & Context ----------
    dict(id="context-window-components", title="What fills the context window (the 7 competing components)",
         source="Reddit r/LLMDevs", author="u/Vuducdung28", date="2026-02", type="Community",
         url="https://www.reddit.com/r/LLMDevs/comments/1rfh6p4/",
         branches=["context"],
         notes=[
            dict(b="context", k="Production-grounded (LangGraph) deep dive on the seven things competing for the window — system prompts, user messages, conversation state, long-term memory, RAG, tool definitions, output schemas — with token ranges for each.",
                 r="Sets the budget frame: long-term memory is just one of seven consumers, so memory design is inseparable from context engineering. The practical entry point to this category."),
         ],
         related=["arc-context", "agentic-context-engineering", "contextweaver"]),

    dict(id="contextweaver", title="ContextWeaver: Selective and Dependency-Structured Memory Construction",
         source="arXiv", author="Wu et al.", date="2026-04", type="Research",
         url="https://arxiv.org/abs/2604.23069",
         branches=["context", "consolidation"],
         notes=[
            dict(b="context", k="Sliding-window and prompt-compression context management omit earlier structured info later steps rely on; retrieval-based memory surfaces relevant content but overlooks dependencies. Builds memory selectively with explicit dependency structure.",
                 r="Targets the failure where compression drops the one earlier fact a later step needs — a dependency-aware answer to context rot. Connects consolidation (what to keep) with context (what to show)."),
         ],
         related=["arc-context", "context-window-components", "agentic-context-engineering"]),

    dict(id="arc-context", title="ARC: Active and Reflection-driven Context Management for Long-Horizon Agents",
         source="arXiv", author="Yao et al.", date="2026-01", type="Research",
         url="https://arxiv.org/abs/2601.12030",
         branches=["context"],
         notes=[
            dict(b="context", k="Names 'context rot' — performance degradation as interaction histories grow — as a failure to maintain coherent, task-relevant internal state. Proposes active + reflection-driven context management for deep-search/long-horizon agents.",
                 r="Canonical reference for the context-rot problem this category orbits. Pairs with [contextweaver] (structural fix) and [retrieve-or-think] (retrieve-vs-reason policy)."),
         ],
         related=["contextweaver", "retrieve-or-think", "context-window-components"]),

    dict(id="agentic-context-engineering", title="Agentic Context Engineering: Evolving Contexts for Self-Improving Models",
         source="arXiv / ADS", author="Zhang et al.", date="2026-03", type="Research",
         url="https://ui.adsabs.harvard.edu/abs/2025arXiv251004618Z",
         branches=["context", "consolidation"],
         notes=[
            dict(b="context", k="Context adaptation (modifying inputs vs updating weights) suffers two failure modes: brevity bias (concise summaries drop domain insight) and context collapse (iterative rewriting erodes detail).",
                 r="Names the exact degradation mode behind LLM-rewritten memory — the context-side mirror of [useful-memories-faulty]. Strong argument against over-summarizing either context or stored memory."),
         ],
         related=["useful-memories-faulty", "contextweaver", "arc-context"]),

    # ---------- Evaluation & Cost ----------
    dict(id="locomo-plus", title="LoCoMo-Plus: Beyond-Factual Cognitive Memory Evaluation",
         source="arXiv", author="Li et al.", date="2026-02", type="Research",
         url="https://arxiv.org/abs/2602.10715",
         branches=["evaluation"],
         notes=[
            dict(b="evaluation", k="Existing benchmarks (LoCoMo foremost) focus on surface factual recall, but good responses often hinge on implicit constraints — user state, goals, values — never explicitly queried later. LoCoMo-Plus evaluates that 'beyond-factual' setting.",
                 r="Marks the benchmark frontier shifting from 'did it recall the fact' to 'did it honor implicit user context'. Pairs with [adamem] (user-centric retrieval) and [precision-belief-state] (retrieval precision)."),
         ],
         related=["precision-belief-state", "engramabench", "adamem", "persistbench"]),

    dict(id="engramabench", title="EngramaBench: Long-Term Conversational Memory with Structured Graph Retrieval",
         source="arXiv", author="Julian Acuna", date="2026-04", type="Research",
         url="https://arxiv.org/abs/2604.21229",
         branches=["evaluation"],
         notes=[
            dict(b="evaluation", k="Benchmark for multi-session memory: five personas, 100 multi-session conversations, 150 queries spanning factual recall, cross-space integration, and more.",
                 r="A concrete harness for evaluating cross-session retrieval quality. Use alongside [precision-belief-state] (precision) and [locomo-plus] (beyond-factual) to triangulate."),
         ],
         related=["locomo-plus", "precision-belief-state", "mem0-vs-graphiti"]),

    dict(id="what-using-production", title="What are people actually using for agent memory in production?",
         source="Reddit r/LLMDevs", author="u/MeasurementSelect251", date="2026-01", type="Community",
         url="https://www.reddit.com/r/LLMDevs/comments/1qiueyd/",
         branches=["evaluation"],
         notes=[
            dict(b="evaluation", k="Field thread: chat-history-only, vector-DB RAG, and summary+embedding hybrids all 'work for demos' but break once the agent runs a while — preferences drift, the same mistakes recur, stale context gets pulled purely on semantic closeness.",
                 r="The blunt production reality check that motivates half this map (temporal updating, forgetting, beyond-similarity retrieval). The 'stale context on semantic closeness' complaint is exactly [adamem]'s thesis."),
         ],
         related=["building-at-scale", "adamem", "aurra-bitemporal", "what-i-learned-coding-agent"]),

    dict(id="building-at-scale", title="Building memory systems at production scale (100k+ users): lessons from 10+ implementations",
         source="Reddit r/LLMDevs", author="u/singh_taranjeet", date="2026-04", type="Community",
         url="https://www.reddit.com/r/LLMDevs/comments/1sn3dnx/",
         branches=["evaluation", "multiagent"],
         notes=[
            dict(b="evaluation", k="Lessons from ~10 production deployments (healthcare, fintech, consumer SaaS, dev tooling) on what actually matters vs the 'just add a vector DB' tutorials.",
                 r="The hard-won operational counterweight to research/product claims. Read with [what-using-production] as the practitioner reality layer of the Evaluation category."),
         ],
         related=["what-using-production", "mem0-vs-graphiti", "memory-circuit-analysis"]),

    dict(id="memory-circuit-analysis", title="What Happens Inside Agent Memory? Circuit Analysis from Emergence to Diagnosis",
         source="arXiv / ADS", author="Mao et al.", date="2026-05", type="Research",
         url="https://ui.adsabs.harvard.edu/abs/2026arXiv260503354M",
         branches=["evaluation"],
         notes=[
            dict(b="evaluation", k="Agent memory failures are silent — a fluent answer can hide a failure to extract, retain, or retrieve. Traces feature circuits across Qwen-3 (0.6B–14B) to map the write–manage–read loop to internal computations.",
                 r="A mechanistic-interpretability angle on *why* memory fails, complementing black-box benchmarks. Connects the write/manage/read framing used across consolidation, substrate, and retrieval."),
         ],
         related=["precision-belief-state", "building-at-scale", "engramabench"]),

    # ---------- Interop, Schema & Governance ----------
    dict(id="memorywire", title="memorywire: A Vendor-Neutral Wire Format for Agent Memory Operations",
         source="arXiv", author="Munirathinam", date="2026-05", type="Research",
         url="https://arxiv.org/abs/2606.01138",
         branches=["interop"],
         notes=[
            dict(b="interop", k="Mem0, Letta/MemGPT, Cognee, Zep/Graphiti, MemoryOS, MemTensor each ship their own SDK, storage layout, and vocabulary — no shared wire format. Every integration is bespoke, every migration rebuilds from scratch, and none ships a governance surface to review writes. Proposes a neutral wire format.",
                 r="The interoperability + governance gap stated plainly — directly relevant if a service spans multiple stores (vector + graph + object storage). Pairs with [schema-quality] (schema discipline) and [unified-memory-stack] (DIY unification)."),
         ],
         related=["schema-quality", "unified-memory-stack", "cf-agent-memory-infoq", "mem0-vs-graphiti"]),

    dict(id="schema-quality", title="Agent Memory Is Only as Good as Its Schema",
         source="Daily Dose of DS", author="Daily Dose of DS", date="2026-05", type="Newsletter",
         url="https://www.dailydoseofds.com/",
         branches=["interop"],
         notes=[
            dict(b="interop", k="Deep dive on production-grade agent memory arguing memory quality is bounded by schema quality — get the schema wrong and retrieval/consolidation can't recover.",
                 r="Elevates schema design to a first-class concern; the human-readable companion to [memorywire]'s machine wire-format. Connects to Representation (the schema encodes the representation choice)."),
         ],
         related=["memorywire", "graph-memory-survey", "beyond-atomic-facts"]),

    dict(id="unified-memory-stack", title="Built a unified LLM memory system combining Memori + Mem0 + Supermemory",
         source="Reddit r/LLMDevs", author="u/0sparsh2", date="2025-11", type="Community",
         url="https://www.reddit.com/r/LLMDevs/comments/1p2szij/",
         branches=["interop", "substrate"],
         notes=[
            dict(b="interop", k="DIY unification: Memori's interceptor architecture (zero code changes), Mem0's research-validated retrieval/consolidation, and Supermemory's structure — composed into one stack.",
                 r="Exactly the multi-store composition pattern that motivates a wire format. Real-world evidence builders are already gluing frameworks together by hand. Connects to [memorybank-rust] (cross-tool) and [memorywire] (the standard that would obviate the glue)."),
         ],
         related=["memorywire", "memorybank-rust", "openmemory-mem0"]),

    dict(id="openmemory-mem0", title="OpenMemory by Mem0: 'local' but still needs an OpenAI key?",
         source="Reddit r/LLMDevs", author="u/Perplexed_86400", date="2026-02", type="Community",
         url="https://www.reddit.com/r/LLMDevs/comments/1rdv0jz/",
         branches=["interop", "substrate"],
         notes=[
            dict(b="interop", k="Notes that Mem0's OpenMemory MCP advertises local/private operation but still requires an OpenAI key (embeddings + gpt-4.1-nano) for extraction in the default Docker setup.",
                 r="Operational gotcha for anyone assuming a 'local' memory framework is self-contained — the LLM dependency leaks in via extraction/embeddings. Relevant to substrate/privacy and to the zero-LLM designs ([superlocalmemory], [yourmemory]) reacting to exactly this."),
         ],
         related=["superlocalmemory", "yourmemory", "unified-memory-stack"]),
]

# ---------------------------------------------------------------------------
# Orientation reading path: curated order, grouped. (id, label, group)
# ---------------------------------------------------------------------------
ORIENTATION = [
    ("memory-survey-hu", "Memory in the Age of AI Agents — the taxonomy", "Orient"),
    ("cf-agent-memory-blog", "Cloudflare Agent Memory — the reference service", "Orient"),
    ("context-window-components", "What fills the context window — the budget frame", "Frame"),
    ("slack-context", "Slack: structured memory + distilled truth in prod", "Consolidate"),
    ("useful-memories-faulty", "Why LLM-rewritten memory degrades", "Consolidate"),
    ("kg-wrong-abstraction", "The case against KGs as the default", "Represent"),
    ("graph-memory-survey", "The case for graph memory (survey)", "Represent"),
    ("beyond-atomic-facts", "Beyond atomic facts", "Represent"),
    ("aurra-bitemporal", "The timeline/fact-update problem, from the field", "Time"),
    ("precision-belief-state", "Retrieval-correctness ≠ answer-correctness", "Evaluate"),
    ("mem0-vs-graphiti", "Vector vs graph: cost & accuracy head-to-head", "Evaluate"),
    ("what-using-production", "What actually breaks in production", "Reality"),
    ("git-s3-memory", "The boring-substrate counter-movement", "Substrate"),
    ("memorywire", "Interop & governance: the missing wire format", "Govern"),
]

# Cross-cutting heuristics & pitfalls (synthesized across the corpus)
HEURISTICS = [
    "RETAIN RAW, DISTILL SEPARATELY: keep full episodic traces / transcripts as immutable ground truth (cheap object storage) and treat any LLM-consolidated 'distilled truth' as a derived, fallible layer you can rebuild — because continuous LLM rewriting provably degrades memory (Slack, Useful-Memories-Faulty, Agentic-Context-Engineering).",
    "MULTI-CHANNEL + FUSION over single-vector: the shipped production default (Cloudflare) is parallel channels fused with RRF, not one cosine lookup — but add channels deliberately, since each adds latency, cost, and spurious-match surface.",
    "MEASURE RETRIEVAL, NOT JUST ANSWERS: a system that returns its whole belief store scores recall 1.0 and passes answer-quality evals. Evaluate retrieval precision separately (precision-aware / beyond-factual benchmarks) or you can't tell a good retriever from a verbose one.",
    "MODEL TIME EXPLICITLY: the #1 field complaint about vector-only memory is timeline amnesia on fact updates. Decide supersede-vs-version up front; bi-temporal modeling is the differentiator builders switch for.",
    "OPTIMIZE FOR UTILITY, NOT CAPACITY: ask what experience changes future behavior, not what fits the window. Eager per-turn extraction is the main cost driver — batch/recurrent consolidation cuts tokens at the price of staleness.",
    "DON'T REACH FOR THE HEAVY STORE BY DEFAULT: many agents are well served by SQLite + FTS over a transcript store; KGs add an entity-extraction LLM step, hallucinated edges, and mega-hub scaling pathologies. Justify the graph/vector DB.",
    "PLAN FOR PORTABILITY & AUDIT EARLY: every framework ships bespoke storage and vocabulary with no shared wire format and almost no governance surface — composing stores by hand (Memori+Mem0+Supermemory) is common, and migration currently means rebuilding from scratch.",
]
PITFALLS = [
    "SEMANTIC-CLOSENESS ≠ RELEVANCE: ranking purely on embedding distance pulls in stale-but-similar context and misses evidence about user state/goals that isn't lexically near the query (AdaMem; 'what people use in production').",
    "SILENT MEMORY FAILURES: extraction/retention/retrieval can fail while the agent still answers fluently — failures are invisible without retrieval-level metrics or interpretability (Circuit Analysis).",
    "CONTEXT COLLAPSE / BREVITY BIAS: iterative summarization of context or memory erodes domain detail and drops the one earlier structured fact a later step depends on (Agentic Context Engineering; ContextWeaver).",
    "APPEND-ONLY ROT: markdown-append / log-accumulation memory grows until retrieval is polluted by clutter and cap saturation; without a forgetting lifecycle, recall quality decays over runtime.",
    "PERSISTENCE AS A SAFETY RISK: durably remembering user facts isn't purely beneficial — persisted attributes can create safety/privacy liabilities, and forgetting is the least-measured part of the stack (PersistBench).",
    "'LOCAL' ISN'T ALWAYS LOCAL: frameworks advertised as local/private can still require a cloud LLM/embedding key for extraction (OpenMemory/Mem0) — verify the dependency graph before assuming self-containment.",
    "VENDOR EVALS HIDE SYSTEM COST: framework-published benchmarks optimize tokens/latency and omit system-level cost and accuracy, especially in distributed multi-agent settings (Cost-and-Accuracy study).",
]

# ---------------------------------------------------------------------------
# Assemble + emit
# ---------------------------------------------------------------------------
def normalize_notes():
    """Note dicts use the compact key 'b'; the renderer expects 'branch'."""
    for s in S:
        s["notes"] = [
            dict(branch=n["b"], k=n["k"], r=n.get("r", "")) for n in s["notes"]
        ]


def build_data():
    normalize_notes()
    sections = []
    for key, label in BRANCH_LABELS.items():
        meta = SECTION_META[key]
        ids = [s["id"] for s in S if key in s["branches"]]
        sections.append(dict(
            key=key, label=label,
            consideration=meta["consideration"],
            questions=meta["questions"],
            tensions=meta["tensions"],
            takeaways=meta["takeaways"],
            sources=ids,
        ))
    return dict(
        sources=S,
        sections=sections,
        orientation=ORIENTATION,
        heuristics=HEURISTICS,
        pitfalls=PITFALLS,
        branch_labels=BRANCH_LABELS,
    )


def extract_style(shell_html):
    m = re.search(r"<style>.*?</style>", shell_html, re.S)
    if not m:
        raise SystemExit("could not find <style> block in shell")
    return m.group(0)


BODY = """<body>
<header>
  <div class="brand">
    <h1>Agent Memory &middot; Design Considerations</h1>
    <div class="sub">Field companion to the academic explorer &middot; {n} sources, {t} considerations &middot; code-intel-digest mirror &middot; built 2026-06-04</div>
  </div>
  <div class="spacer"></div>
  <button id="themebtn" type="button" aria-label="Toggle color theme">&#9790; Dark</button>
</header>
<div class="layout">
  <nav id="nav"></nav>
  <main>
    <div id="controls" class="controls">
      <input id="q" placeholder="Search titles, distillations, takeaways, sources&hellip;">
      <select id="ftype"><option value="">All types</option></select>
      <select id="fbranch"><option value="">All considerations</option></select>
      <select id="fsort">
        <option value="rel">Sort: curated order</option>
        <option value="date">Sort: date &darr;</option>
        <option value="type">Sort: type</option>
        <option value="title">Sort: title</option>
      </select>
      <span class="hint" id="resultcount"></span>
    </div>
    <div id="view"></div>
  </main>
</div>
"""

SCRIPT = r"""<script>
const D = JSON.parse(document.getElementById('data').textContent);
const byId = {}; D.sources.forEach(s=>byId[s.id]=s);
const esc = s => (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

const NAV = [
  {k:'__home',l:'Overview'},
  {grp:'Explore'},
  {k:'__all',l:'All sources'},
  {k:'__orient',l:'★ Orientation path'},
  {k:'__cross',l:'★ Heuristics & pitfalls'},
  {grp:'Design considerations'},
  ...D.sections.map(s=>({k:s.key,l:s.label,n:s.sources.length})),
];
let active='__home', q='', ftype='', fbranch='', fsort='rel';

function buildNav(){
  const nav=document.getElementById('nav'); nav.innerHTML='';
  NAV.forEach(it=>{
    if(it.grp){const d=document.createElement('div');d.className='grouphdr';d.textContent=it.grp;nav.appendChild(d);return;}
    const b=document.createElement('button');b.dataset.k=it.k;
    b.innerHTML=esc(it.l)+(it.n!=null?`<span class="count">${it.n}</span>`:'');
    if(it.k===active)b.classList.add('active');
    b.onclick=()=>{active=it.k;render();};
    nav.appendChild(b);
  });
}
(function(){
  const types=[...new Set(D.sources.map(s=>s.type).filter(Boolean))].sort();
  const ft=document.getElementById('ftype'); types.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;ft.appendChild(o);});
  const fb=document.getElementById('fbranch');
  Object.entries(D.branch_labels).forEach(([k,l])=>{const o=document.createElement('option');o.value=k;o.textContent=l;fb.appendChild(o);});
})();
document.getElementById('q').oninput=e=>{q=e.target.value.toLowerCase();render();};
document.getElementById('ftype').onchange=e=>{ftype=e.target.value;render();};
document.getElementById('fbranch').onchange=e=>{fbranch=e.target.value;render();};
document.getElementById('fsort').onchange=e=>{fsort=e.target.value;render();};

function hl(t){ if(!q)return esc(t); const i=(t||'').toLowerCase().indexOf(q); if(i<0)return esc(t);
  return esc(t.slice(0,i))+'<mark>'+esc(t.slice(i,i+q.length))+'</mark>'+esc(t.slice(i+q.length)); }

function matches(s){
  if(ftype && s.type!==ftype) return false;
  if(fbranch && !s.branches.includes(fbranch)) return false;
  if(q){ const hay=(s.title+' '+s.source+' '+s.author+' '+s.type+' '+s.notes.map(n=>n.k+' '+n.r).join(' ')).toLowerCase();
    if(!hay.includes(q)) return false; }
  return true;
}
function sortSrc(arr){
  const a=[...arr];
  if(fsort==='date') a.sort((x,y)=>(y.date||'').localeCompare(x.date||''));
  else if(fsort==='type') a.sort((x,y)=>(x.type||'').localeCompare(y.type||'')||(x.title||'').localeCompare(y.title||''));
  else if(fsort==='title') a.sort((x,y)=>(x.title||'').localeCompare(y.title||''));
  return a;
}
function relatedHTML(s){
  const rel=(s.related||[]).map(id=>{const r=byId[id];
    return r?`<button class="reln" onclick="jumpTo('${id}')">${esc(r.title)}</button>`:'';}).filter(Boolean).join('');
  return rel?`<div class="lbl">related sources</div><div class="rels">${rel}</div>`:'';
}
function cardHTML(s){
  const chips=s.branches.map(b=>`<span class="chip b">${esc(D.branch_labels[b]||b)}</span>`).join('');
  const notes=s.notes.map(n=>`
     <div class="lbl">${esc(D.branch_labels[n.branch]||n.branch)} &middot; distillation</div><p>${hl(n.k)}</p>
     ${n.r?`<div class="lbl">connections & takeaway</div><p>${hl(n.r)}</p>`:''}`).join('');
  return `<div class="card" id="src-${esc(s.id)}" data-id="${esc(s.id)}">
    <div class="ttl">${hl(s.title||s.id)}</div>
    <div class="meta"><span class="chip type">${esc(s.type)}</span><span>${esc(s.source||'')}</span>${s.author?`<span class="byline">${esc(s.author)}</span>`:''}${s.date?`<code class="bc-code">${esc(s.date)}</code>`:''}${chips}</div>
    <div class="body">${notes}${relatedHTML(s)}
      <div class="links"><a href="${esc(s.url)}" target="_blank" rel="noopener">Open source &#8599;</a></div>
    </div></div>`;
}
function wireCards(){
  document.querySelectorAll('.card').forEach(c=>c.onclick=e=>{
    if(e.target.tagName==='A'||e.target.classList.contains('reln'))return; c.classList.toggle('open');});
}
function renderList(ids){
  let arr = ids ? ids.map(i=>byId[i]).filter(Boolean) : D.sources;
  arr = sortSrc(arr.filter(matches));
  document.getElementById('resultcount').textContent = arr.length+' source'+(arr.length!=1?'s':'');
  return arr.length? arr.map(cardHTML).join('') : '<div class="empty">No sources match.</div>';
}
function panel(cls,title,items){ if(!items||!items.length)return'';
  return `<div class="panel ${cls}"><h3>${esc(title)}</h3><ul>${items.map(i=>`<li>${esc(i)}</li>`).join('')}</ul></div>`; }
function showControls(on){document.getElementById('controls').style.display=on?'flex':'none';}

// jump to a related source: reset filters, switch to All, open + scroll it
function jumpTo(id){
  active='__all'; q=''; ftype=''; fbranch=''; fsort='rel';
  const qb=document.getElementById('q'); if(qb)qb.value='';
  const tb=document.getElementById('ftype'); if(tb)tb.value='';
  const bb=document.getElementById('fbranch'); if(bb)bb.value='';
  render();
  requestAnimationFrame(()=>{const el=document.getElementById('src-'+id);
    if(el){el.classList.add('open');el.scrollIntoView({behavior:'smooth',block:'center'});}});
}

function render(){
  buildNav();
  const v=document.getElementById('view');
  if(active==='__home'){ showControls(false); v.innerHTML=homeHTML(); }
  else if(active==='__all'){ showControls(true); v.innerHTML='<h2 class="sectionhead">All sources</h2>'+renderList(null); wireCards(); }
  else if(active==='__orient'){ showControls(false); v.innerHTML=orientHTML(); wireCards(); }
  else if(active==='__cross'){ showControls(false); v.innerHTML=crossHTML(); }
  else { showControls(true); const s=D.sections.find(x=>x.key===active);
    v.innerHTML=`<h2 class="sectionhead">${esc(s.label)}</h2><p class="subtopic">${esc(s.consideration)}</p>`
      +panel('themes','Design questions this raises',s.questions)
      +panel('gaps','Tensions & tradeoffs',s.tensions)
      +panel('notable','Takeaways',s.takeaways)
      +'<h3 style="margin:16px 0 8px">Sources</h3>'+renderList(s.sources); wireCards(); }
  window.scrollTo(0,0);
}
function homeHTML(){
  const stats=`${D.sources.length} sources · ${D.sections.length} design considerations · ${D.orientation.length}-step orientation path`;
  return `<h2 class="sectionhead">Overview</h2><p class="subtopic">${stats}</p>
  <div class="panel"><h3>What this is</h3><p class="val">A navigable map of <b>practitioner, industry, and community</b> sources on agentic memory — product launches, engineering write-ups, field reports, newsletters, and the design-relevant slice of recent research — organized by <b>memory design consideration</b> rather than by product or vendor. It is the field-and-practice companion to the academic <a href="agentic_memory_explorer.html">Agentic Memory Systems</a> explorer. Sources surfaced via the code-intel-digest local mirror (code-intel-copilot MCP).</p>
  <p class="hint">Each source carries a distillation (key points), connections + a takeaway, and links to related sources you can jump to. Much of the recent research here is 2026 preprints — treat metrics as author self-reports.</p></div>
  <div class="panel"><h3>Start here</h3><ul>
    <li><b>&#9733; Orientation path.</b> A 14-step order to get current fast, grouped by stage.</li>
    <li><b>&#9733; Heuristics & pitfalls.</b> Cross-cutting design rules synthesized across the whole corpus.</li>
    <li><b>Design considerations</b> (left nav). Each carries the questions it raises, its tensions/tradeoffs, and takeaways.</li>
  </ul></div>
  <div class="panel themes"><h3>The field in one paragraph</h3><p class="val">Through 2025&ndash;2026 agent memory went from research topic to product category: managed services shipped (Cloudflare Agent Memory, Mem0, Zep, LangMem, Letta) while surveys formalized the field in parallel. Production teams (Slack) learned to replace accumulated chat logs with structured, validated, distilled memory; research showed naive LLM-driven consolidation degrades over time, that knowledge graphs are contested as the default abstraction, and that timeline/fact-update handling is the recurring weak spot of vector-only stores. Meanwhile a deliberately-boring counter-movement (Git + S3, SQLite + FTS, self-hosted transcript archives) pushes back on heavyweight memory services, and the field still lacks shared wire formats, governance surfaces, and benchmarks that measure retrieval &mdash; not just answers &mdash; or measure forgetting at all.</p></div>`;
}
function orientHTML(){
  let rows=D.orientation.map((r,i)=>{const s=byId[r[0]];
    return `<div class="readrow"><div class="rk">${i+1}</div><div class="grp">${esc(r[2])}</div>
      <div><a href="#" onclick="event.preventDefault();openOne('${r[0]}')"><b>${esc(r[1])}</b></a>
      <div class="hint">${esc(s?s.source+' · '+s.date:r[0])}${s?` · <a href="${esc(s.url)}" target="_blank" rel="noopener">open ↗</a>`:''}</div></div></div>`;
  }).join('');
  return `<h2 class="sectionhead">&#9733; Orientation path</h2><p class="subtopic">Fourteen sources to get current fast, ordered by stage: orient → frame → consolidate → represent → time → evaluate → reality → substrate → govern. Click a title to expand its card inline.</p>${rows}
  <div id="oneview" style="margin-top:16px"></div>`;
}
function openOne(id){const s=byId[id];const o=document.getElementById('oneview');
  if(!s){o.innerHTML='<div class="empty">Not in the set.</div>';return;}
  o.innerHTML=cardHTML(s);o.querySelector('.card').classList.add('open');wireCards();o.scrollIntoView({behavior:'smooth'});}
function crossHTML(){
  return `<h2 class="sectionhead">&#9733; Heuristics & pitfalls</h2><p class="subtopic">Cross-cutting design rules synthesized across the corpus &mdash; the through-lines that recur regardless of which store or vendor you pick.</p>`
   +panel('themes','Design heuristics',D.heuristics)
   +panel('gaps','Pitfalls to avoid',D.pitfalls);
}
const TKEY='amd-theme';
function setTheme(t){document.documentElement.dataset.theme=t;try{localStorage.setItem(TKEY,t);}catch(e){}
  const b=document.getElementById('themebtn');if(b)b.innerHTML=(t==='dark'?'☀ Light':'☾ Dark');}
setTheme((()=>{try{return localStorage.getItem(TKEY)||'light';}catch(e){return 'light';}})());
document.getElementById('themebtn').onclick=()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement.id!=='q'){const el=document.getElementById('q');
    if(el&&el.offsetParent!==null){e.preventDefault();el.focus();el.select();}}
  if(e.key==='Escape'&&document.activeElement.id==='q'){q='';document.getElementById('q').value='';render();}
});
render();
</script>"""

# a little extra CSS for the few new classes (byline, type chip, related buttons)
EXTRA_CSS = """<style>
.chip.type{color:var(--violet);border-color:var(--violet-bg);background:var(--violet-bg);font-weight:600}
.byline{color:var(--faint)}
.rels{display:flex;flex-wrap:wrap;gap:7px;margin-top:2px}
.reln{font:inherit;font-size:12.5px;color:var(--accent);background:var(--accent-weak);border:1px solid var(--accent-weak);
  padding:4px 10px;border-radius:20px;cursor:pointer;text-align:left;transition:border-color .15s}
.reln:hover{border-color:var(--accent);text-decoration:underline}
</style>"""


def main():
    shell = SHELL.read_text()
    style = extract_style(shell)
    data = build_data()
    body = BODY.format(n=len(data["sources"]), t=len(data["sections"]))
    data_blob = ('<script id="data" type="application/json">'
                 + json.dumps(data, ensure_ascii=False) + '</script>')
    html = (
        '<!DOCTYPE html>\n<html lang="en"><head>\n'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>Agent Memory &middot; Design Considerations</title>\n'
        '<meta name="description" content="Practitioner & field companion to the agentic-memory literature explorer, organized by memory design consideration.">\n'
        + style + "\n" + EXTRA_CSS + "</head>\n"
        + body + data_blob + "\n" + SCRIPT + "\n</body></html>\n"
    )
    OUT.write_text(html)
    print(f"wrote {OUT}  ({len(html):,} bytes, {len(data['sources'])} sources, {len(data['sections'])} considerations)")


if __name__ == "__main__":
    main()
