"""
Multi-Agent Debate Engine (Phase 4).

Orchestrates adversarial reasoning by splitting ARIA into three personas:
  - Agent A  (Thesis):    Pro position
  - Agent B  (Antithesis): Con position, GROUNDED IN LIVE KNOWLEDGE GRAPH
  - Judge    (Synthesis):  Truth synthesis, SEEDED WITH DB CONTRADICTIONS

Phase 3 upgrade:
  Agent B now queries the KnowledgeGraph for CONTRADICTS edges relevant to
  the debate topic before forming its argument. This grounds the Antithesis
  in the actual world model instead of relying purely on the transcript.

  The Judge receives open unresolved contradictions from ContradictionDetector
  so its synthesis can resolve live knowledge conflicts, not just debate points.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Callable, Any, TYPE_CHECKING
from pydantic import BaseModel, Field

from silex.llm.base import SupportsLLM
from silex.models.schemas import DebateArgument, DebateResolution, UncertaintyTopic
from silex.storage.database import Database
from silex.utils.logger import setup_logger

if TYPE_CHECKING:
    from silex.world.graph import KnowledgeGraph
    from silex.world.contradictions import ContradictionDetector

log = setup_logger("aria.debate")

AGENT_A_PROMPT = """You are Agent A, a rigorous debater.
You have been assigned to argue the PRO or PERSPECTIVE 1 side of the following topic.
You must be logically rigorous, cite structural or causal reasons, and brutally deconstruct the opposing view.
Do NOT compromise. Your goal is to win the argument based on pure logic and evidence.
Be concise but devastating."""

AGENT_B_PROMPT = """You are Agent B, a rigorous debater.
You have been assigned to argue the CON or PERSPECTIVE 2 side of the following topic.
You must be logically rigorous, cite structural or causal reasons, and brutally deconstruct the opposing view.
Do NOT compromise. Your goal is to win the argument based on pure logic and evidence.
Be concise but devastating.

CRITICAL: You will be provided with LIVE KNOWLEDGE GRAPH CONTEXT below. This contains known
CONTRADICTIONS, causal edges, and world model facts that Agent A's position must contend with.
You MUST use these graph-derived constraints as the factual foundation for your argument.
Do not ignore them — they are ground truth from the world model."""

JUDGE_PROMPT = """You are the Judge, the ultimate synthesizer of truth.
You are reviewing a debate between Agent A and Agent B.
Your job is NOT to pick a winner, but to find the truth.
1. Identify the strongest, most structurally sound points from both sides.
2. Identify logical fallacies or weak assumptions made by either side.
3. Synthesize a final, nuanced truth that transcends the binary argument.
4. If the debate reveals new causal facts (e.g., A causes B, or X enables Y), extract them as graph updates.
5. You will receive ACTIVE CONTRADICTIONS from the knowledge database below — your synthesis MUST
   address whether the debate evidence resolves, deepens, or is unrelated to each listed contradiction.
You are objective, emotionless, and deeply wise."""


class DebateEngine:
    """Manages multi-agent debates and truth synthesis.

    Parameters
    ----------
    knowledge_graph:
        Live KnowledgeGraph instance. Used to retrieve CONTRADICTS edges
        relevant to the debate topic and inject them into Agent B's context.
    contradiction_detector:
        Live ContradictionDetector instance. Used to seed the Judge's
        synthesis prompt with open database contradictions.
    """

    def __init__(
        self,
        llm_client: SupportsLLM,
        db: Database,
        knowledge_graph: "KnowledgeGraph | None" = None,
        contradiction_detector: "ContradictionDetector | None" = None,
    ):
        self.llm = llm_client
        self.db = db
        self.kg = knowledge_graph
        self.contradictions = contradiction_detector

    async def run_debate(
        self,
        topic: str,
        rounds: int = 1,
        status_callback: Callable[..., Any] | None = None,
        parallel: bool = False,
    ) -> DebateResolution:
        """Run a full debate between A and B, judged by the Synthesizer."""
        log.info(f"Starting debate on topic: {topic} (parallel={parallel})")
        transcript = []

        if parallel:
            import asyncio
            from agent.orchestrator import WorkerOrchestrator
            from agent.security.lease import ActuationLease

            orchestrator = WorkerOrchestrator.instance()

            for r in range(rounds):
                if status_callback:
                    status_callback(
                        f"[magenta]  Agents A and B are formulating arguments in parallel (Round {r + 1})...[/]"
                    )

                # Issue leases for Agent A and Agent B
                lease_a = ActuationLease.issue(
                    task_id=f"debate_a_round_{r + 1}_{uuid.uuid4().hex[:4]}",
                    agent_id="Agent A",
                    ttl_seconds=300.0,
                    allowed_tools=["run_terminal_command"],
                )
                lease_b = ActuationLease.issue(
                    task_id=f"debate_b_round_{r + 1}_{uuid.uuid4().hex[:4]}",
                    agent_id="Agent B",
                    ttl_seconds=300.0,
                    allowed_tools=["run_terminal_command"],
                )

                # Spawn separate Docker workers simultaneously
                h_a = await orchestrator.spawn_worker(
                    task="echo 'Agent A formulating argument'",
                    tools=["run_terminal_command"],
                    lease=lease_a,
                )
                h_b = await orchestrator.spawn_worker(
                    task="echo 'Agent B formulating argument'",
                    tools=["run_terminal_command"],
                    lease=lease_b,
                )

                # Execute LLM completions concurrently in the main process
                # but associate them with the workers' lifecycle
                async def run_agent_a():
                    arg = await self._generate_argument("Agent A", topic, transcript)
                    # Write result to worker's workspace
                    output_file = h_a.workspace_dir / "output.json"
                    output_file.write_text(
                        json.dumps(arg.model_dump()), encoding="utf-8"
                    )
                    await h_a.result()  # Wait for container to exit
                    return arg

                async def run_agent_b():
                    arg = await self._generate_argument("Agent B", topic, transcript)
                    # Write result to worker's workspace
                    output_file = h_b.workspace_dir / "output.json"
                    output_file.write_text(
                        json.dumps(arg.model_dump()), encoding="utf-8"
                    )
                    await h_b.result()  # Wait for container to exit
                    return arg

                a_arg, b_arg = await asyncio.gather(run_agent_a(), run_agent_b())
                transcript.append(a_arg)
                transcript.append(b_arg)

        else:
            # Sequential mode (original)
            # Round 1
            if status_callback:
                status_callback("[red]  Agent A is formulating opening statement...[/]")

            a_arg = await self._generate_argument("Agent A", topic, transcript)
            transcript.append(a_arg)

            if status_callback:
                status_callback(
                    "[blue]  Agent B is querying world model and rebutting...[/]"
                )

            b_arg = await self._generate_argument("Agent B", topic, transcript)
            transcript.append(b_arg)

            # Additional rounds if requested
            for i in range(1, rounds):
                if status_callback:
                    status_callback(
                        f"[red]  Agent A is rebutting (Round {i + 1})...[/]"
                    )
                a_arg = await self._generate_argument("Agent A", topic, transcript)
                transcript.append(a_arg)

                if status_callback:
                    status_callback(
                        f"[blue]  Agent B is rebutting (Round {i + 1})...[/]"
                    )
                    b_arg = await self._generate_argument("Agent B", topic, transcript)
                transcript.append(b_arg)

        # Judgment
        if status_callback:
            status_callback("[green]  The Judge is synthesizing the truth...[/]")

        resolution = await self._judge_debate(topic, transcript)

        # Save to DB
        await self._save_debate(topic, transcript, resolution)

        return resolution

    async def _generate_argument(
        self, agent_id: str, topic: str, transcript: list[DebateArgument]
    ) -> DebateArgument:
        """Call LLM to generate a single debate turn.

        Agent B gets the live KnowledgeGraph contradiction context injected
        into its user prompt before responding.
        """
        prompt = AGENT_A_PROMPT if agent_id == "Agent A" else AGENT_B_PROMPT

        history = "TRANSCRIPT SO FAR:\n"
        for arg in transcript:
            history += f"{arg.agent_id}: {arg.claim}\nReasoning: {arg.reasoning}\n\n"

        # ── Agent B: inject KG contradiction context ────────────────────
        kg_block = ""
        if agent_id == "Agent B" and self.kg is not None:
            try:
                kg_context = await self.kg.retrieve_relevant_context(topic)
                # Extract nodes that have CONTRADICTS edges
                contradicting_nodes = [
                    n
                    for n in kg_context
                    if n.get("contradicts") or n.get("type") == "fact"
                ]
                if contradicting_nodes:
                    kg_block = (
                        "\n\n════════════════════════════════════════════════════\n"
                        "LIVE KNOWLEDGE GRAPH — CONTRADICTS EDGES\n"
                        "(These are ground-truth constraints from the world model.\n"
                        " Use them to attack Agent A's position with hard evidence.)\n"
                        "════════════════════════════════════════════════════\n"
                    )
                    for i, node in enumerate(contradicting_nodes[:6], 1):
                        kg_block += f"  [{i}] {node['content']} (confidence: {node.get('confidence', 0.5):.2f})\n"
                        if node.get("contradicts"):
                            conflicts = "; ".join(node["contradicts"][:3])
                            kg_block += f"      CONTRADICTS: {conflicts}\n"
                        if node.get("causes"):
                            effects = "; ".join(node["causes"][:2])
                            kg_block += f"      CAUSES: {effects}\n"
                    kg_block += "\n"
            except Exception as e:
                log.warning(f"KG retrieval for debate failed (non-fatal): {e}")

        content = (
            f"TOPIC: {topic}\n\n"
            f"{history}"
            f"{kg_block}"
            "It is your turn. Deliver your argument."
        )

        data = (
            await self.llm.complete_json(
                schema=DebateArgument,
                system_prompt=prompt,
                user_input=content,
                temperature=0.7,
                request_kind="debate_argument",
            )
        ).model_dump()
        # Ensure the agent_id is correct regardless of what the model hallucinates
        data["agent_id"] = agent_id
        return DebateArgument(**data)

    async def _judge_debate(
        self, topic: str, transcript: list[DebateArgument]
    ) -> DebateResolution:
        """Call LLM to synthesize the final resolution.

        The Judge's prompt is seeded with open database contradictions so it
        can produce resolutions that update the world model, not just the debate.
        """
        history = "DEBATE TRANSCRIPT:\n"
        for arg in transcript:
            history += (
                f"--- {arg.agent_id} ---\n"
                f"Claim: {arg.claim}\n"
                f"Logic: {arg.reasoning}\n"
                f"Evidence: {arg.evidence_or_logic}\n\n"
            )

        # ── Inject open database contradictions ────────────────────────
        db_contradiction_block = ""
        if self.contradictions is not None:
            try:
                unresolved = await self.contradictions.get_unresolved()
                if unresolved:
                    db_contradiction_block = (
                        "\n\n════════════════════════════════════════════════════\n"
                        "ACTIVE DATABASE CONTRADICTIONS (unresolved conflicts)\n"
                        "(Your synthesis must address whether the debate evidence\n"
                        " resolves, deepens, or is unrelated to each of these.)\n"
                        "════════════════════════════════════════════════════\n"
                    )
                    for i, c in enumerate(unresolved[:5], 1):
                        analysis = (
                            c.analysis[:120] if hasattr(c, "analysis") else str(c)[:120]
                        )
                        db_contradiction_block += f"  [{i}] {analysis}\n"
                    db_contradiction_block += "\n"
            except Exception as e:
                log.warning(
                    f"Contradiction retrieval for judge failed (non-fatal): {e}"
                )

        content = (
            f"TOPIC: {topic}\n\n"
            f"{history}"
            f"{db_contradiction_block}"
            "Evaluate and synthesize."
        )

        return await self.llm.complete_json(
            schema=DebateResolution,
            system_prompt=JUDGE_PROMPT,
            user_input=content,
            temperature=0.2,
            request_kind="debate_judge",
        )

    async def _save_debate(
        self, topic: str, transcript: list[DebateArgument], resolution: DebateResolution
    ) -> None:
        """Persist the debate outcome."""
        debate_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        transcript_json = json.dumps([t.model_dump() for t in transcript])
        resolution_json = json.dumps(resolution.model_dump())

        await self.db.execute(
            """
            INSERT INTO debates (id, topic, transcript_json, resolution_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (debate_id, topic, transcript_json, resolution_json, created_at),
        )
        log.info(f"Debate {debate_id} saved.")

    async def track_uncertainty(self, topic: str, why_uncertain: str) -> None:
        """Log a topic that ARIA is genuinely uncertain about."""
        u_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        await self.db.execute(
            """
            INSERT INTO uncertainties (id, topic, why_uncertain, status, created_at)
            VALUES (?, ?, ?, 'open', ?)
            """,
            (u_id, topic, why_uncertain, created_at),
        )
        log.info(f"Uncertainty tracked: {topic}")

    async def get_uncertainties(self) -> list[UncertaintyTopic]:
        """Fetch all tracked uncertainties."""
        rows = await self.db.fetch_all(
            "SELECT * FROM uncertainties WHERE status='open' ORDER BY created_at DESC"
        )
        return [UncertaintyTopic(**dict(r)) for r in rows]

    async def run_consensus_debate(
        self,
        draft_code: str,
        goal_description: str,
        status_callback: Callable[..., Any] | None = None,
    ) -> ConsensusDebateResponse:
        """Run a consensus-seeking debate between Architect, Engineer, and Auditor."""
        log.info(f"Starting consensus-seeking debate for goal: {goal_description}")

        current_code = draft_code
        rounds = 3
        avg_score = 0.0
        critiques = []

        for r in range(1, rounds + 1):
            if status_callback:
                status_callback(
                    f"[magenta]  Consensus Debate: Round {r}/{rounds}...[/]"
                )

            critiques = []

            # 1. System Architect
            arch_prompt = (
                "You are the System Architect.\n"
                "Critique the proposed implementation code for simplicity, design patterns, and modularity.\n"
                "Provide a score between 0.0 (horrible, over-engineered or sloppy) and 1.0 (perfectly simple and modular)."
            )
            arch_input = f"Goal: {goal_description}\nProposed Code:\n{current_code}"
            arch_critique = await self.llm.complete_json(
                schema=ConsensusCritique,
                system_prompt=arch_prompt,
                user_input=arch_input,
                temperature=0.2,
                request_kind="debate_consensus",
            )
            arch_critique.role = "SystemArchitect"
            critiques.append(arch_critique)

            # 2. Staff Engineer
            eng_prompt = (
                "You are the Staff Engineer.\n"
                "Critique the proposed implementation code for correctness, performance, and efficiency.\n"
                "Provide a score between 0.0 (incorrect, slow, or buggy) and 1.0 (highly performant and correct)."
            )
            eng_input = f"Goal: {goal_description}\nProposed Code:\n{current_code}"
            eng_critique = await self.llm.complete_json(
                schema=ConsensusCritique,
                system_prompt=eng_prompt,
                user_input=eng_input,
                temperature=0.2,
                request_kind="debate_consensus",
            )
            eng_critique.role = "StaffEngineer"
            critiques.append(eng_critique)

            # 3. Security Auditor
            sec_prompt = (
                "You are the Security Auditor.\n"
                "Critique the proposed implementation code for security, canonicalization, isolation, and path traversal safety.\n"
                "Provide a score between 0.0 (insecure, vulnerable) and 1.0 (perfectly secure and isolated)."
            )
            sec_input = f"Goal: {goal_description}\nProposed Code:\n{current_code}"
            sec_critique = await self.llm.complete_json(
                schema=ConsensusCritique,
                system_prompt=sec_prompt,
                user_input=sec_input,
                temperature=0.2,
                request_kind="debate_consensus",
            )
            sec_critique.role = "SecurityAuditor"
            critiques.append(sec_critique)

            # Calculate average score
            avg_score = sum(c.score for c in critiques) / 3.0
            log.info(f"Consensus Debate Round {r}: Average score = {avg_score:.3f}")

            # Retrieve SecurityAuditor score
            sec_score = next(
                (c.score for c in critiques if c.role == "SecurityAuditor"), 1.0
            )
            consensus_achieved = avg_score >= 0.9 and sec_score >= 0.8

            if consensus_achieved:
                log.info("Consensus achieved early!")
                if status_callback:
                    status_callback(
                        f"[green]  ✔ Consensus achieved early with score {avg_score:.2f}[/]"
                    )
                return ConsensusDebateResponse(
                    refined_code=current_code,
                    average_score=avg_score,
                    consensus_achieved=True,
                    critiques=critiques,
                )

            # If not achieved and not final round, refine code
            if r < rounds:
                if status_callback:
                    status_callback(
                        "[bright_cyan]  Consensus Debate: Refining code draft...[/]"
                    )

                refine_prompt = (
                    "You are the Refactor Coder.\n"
                    "Your job is to rewrite the proposed code draft to resolve all critiques and suggestions from the Architect, Engineer, and Auditor.\n"
                    "Output only the complete refactored code without explanations."
                )

                critiques_summary = ""
                for c in critiques:
                    critiques_summary += f"--- Role: {c.role} (Score: {c.score:.2f}) ---\nCritique: {c.critique}\nSuggestions:\n"
                    for s in c.suggestions:
                        critiques_summary += f"  - {s}\n"
                    critiques_summary += "\n"

                refine_input = (
                    f"Original Proposed Code:\n{current_code}\n\n"
                    f"Critiques received:\n{critiques_summary}\n\n"
                    f"Rewrite the code to solve all these issues perfectly."
                )

                refine_response = await self.llm.think(
                    system_prompt=refine_prompt,
                    user_input=refine_input,
                    temperature=0.2,
                )
                current_code = refine_response.response.strip()
                # Strip markdown code blocks if any
                if current_code.startswith("```"):
                    lines = current_code.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1] == "```":
                        lines = lines[:-1]
                    current_code = "\n".join(lines).strip()

        sec_score = next(
            (c.score for c in critiques if c.role == "SecurityAuditor"), 1.0
        )
        consensus_achieved = avg_score >= 0.9 and sec_score >= 0.8
        return ConsensusDebateResponse(
            refined_code=current_code,
            average_score=avg_score,
            consensus_achieved=consensus_achieved,
            critiques=critiques,
        )


class ConsensusCritique(BaseModel):
    role: str = Field(default="", description="The debate role name")
    score: float = Field(ge=0.0, le=1.0, description="Score assigned to the draft code")
    critique: str = Field(description="Detailed architectural critique")
    suggestions: list[str] = Field(
        default_factory=list, description="Specific improvements suggested"
    )


class ConsensusDebateResponse(BaseModel):
    refined_code: str = Field(description="The final optimized/refined code draft")
    average_score: float = Field(
        description="The average consensus score from all 3 roles"
    )
    consensus_achieved: bool = Field(
        description="True if average score >= 0.9 and Security Auditor score >= 0.8"
    )
    critiques: list[ConsensusCritique] = Field(
        default_factory=list, description="All critiques from all roles"
    )
