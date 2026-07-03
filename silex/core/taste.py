"""
Taste Heuristics Gate — enforcing architectural elegance and simple code designs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from silex.llm.base import SupportsLLM
from silex.utils.logger import setup_logger

log = setup_logger("silex.core.taste")


class TasteScores(BaseModel):
    simplicity: float = Field(ge=0.0, le=1.0, description="1.0 = highly minimal/standard; <0.7 = bloated/over-engineered")
    performance: float = Field(ge=0.0, le=1.0, description="1.0 = optimal/async/light; <0.7 = latency issues/inefficient")
    robustness: float = Field(ge=0.0, le=1.0, description="1.0 = clean errors/types; <0.7 = fragile/no safety margins")
    security: float = Field(ge=0.0, le=1.0, description="1.0 = perfect isolation/sandboxed; <0.7 = insecure defaults/leaks")


class TasteResponse(BaseModel):
    scores: TasteScores
    feedback: str = Field(description="Honest, harsh, actionable explanation of any taste violations or improvements.")
    is_tasteful: bool = Field(description="True if the design conforms to premium quality standards, False if rejected.")


class TasteFrictionBlock(Exception):
    """Raised when a plan or task fails taste heuristics and is rejected."""

    def __init__(self, feedback: str, scores: TasteScores) -> None:
        self.feedback = feedback
        self.scores = scores
        super().__init__(f"Taste Gate Violation: {feedback}")


TASTE_SYSTEM_PROMPT = """You are ARIA's Taste Heuristics Architect.

Evaluate the user's software engineering request or the proposed solution plan against the following Taste Heuristics (0.0 to 1.0 per metric):

1. SIMPLICITY: Does it use minimal, standard library, or clean solutions? Avoids bloat (e.g., adding heavy dependencies like Celery/Redis for simple schedules).
2. PERFORMANCE: Is it clean, asynchronous-friendly, and lightweight?
3. ROBUSTNESS: Does it have clean error handling, clear type annotations, and minimal code churn?
4. SECURITY: Avoids path traversals, insecure defaults, and execution of arbitrary code outside isolation.

Rules:
- Calculate the geometric mean of simplicity, performance, robustness, and security: (simplicity * performance * robustness * security) ^ (1/4).
- A request or plan is TASTEFUL (is_tasteful = true) ONLY if the geometric mean is >= 0.8.
- If rejected, your feedback must be EXACT, TECHNICAL, and CRITICAL. Recommend a simpler, cleaner alternative.
"""


class TasteEvaluator:
    """Enforces design purity and prevents over-engineered or sloppy plans."""

    def __init__(self, llm_client: SupportsLLM, taste_threshold: float = 0.8) -> None:
        self.llm = llm_client
        self.taste_threshold = taste_threshold

    async def evaluate(self, user_input: str) -> None:
        """
        Evaluate user input for software architecture taste.
        Raises TasteFrictionBlock if scores fall below threshold.
        """
        log.debug("Evaluating taste of input request...")
        
        try:
            result = await self.llm.complete_json(
                schema=TasteResponse,
                system_prompt=TASTE_SYSTEM_PROMPT,
                user_input=f"USER REQUEST TO EVALUATE:\n{user_input}",
                temperature=0.1,
                request_kind="taste_critic",
            )
            
            # Compute geometric mean score
            scores = result.scores
            geo_mean = (scores.simplicity * scores.performance * scores.robustness * scores.security) ** 0.25
            
            log.debug(
                f"Taste evaluation: Tasteful={result.is_tasteful} (GeoMean={geo_mean:.3f}) "
                f"Simplicity={scores.simplicity:.2f} Performance={scores.performance:.2f} "
                f"Robustness={scores.robustness:.2f} Security={scores.security:.2f}"
            )
            
            # Force reject if geometric mean falls below threshold
            if geo_mean < self.taste_threshold or not result.is_tasteful:
                log.warning(f"Taste friction triggered! Rejection feedback: {result.feedback[:100]}...")
                raise TasteFrictionBlock(result.feedback, scores)
                
        except TasteFrictionBlock:
            raise
        except Exception as e:
            log.warning(f"Taste evaluator error (failing open): {e}")
            return
