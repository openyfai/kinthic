import pytest
from unittest.mock import AsyncMock
from silex.core.taste import (
    TasteEvaluator,
    TasteFrictionBlock,
    TasteResponse,
    TasteScores,
)


@pytest.mark.asyncio
async def test_taste_gate_accepts():
    mock_llm = AsyncMock()
    mock_llm.complete_json.return_value = TasteResponse(
        scores=TasteScores(
            simplicity=0.9, performance=0.9, robustness=0.9, security=0.9
        ),
        feedback="Clean, minimal approach.",
        is_tasteful=True,
    )

    evaluator = TasteEvaluator(mock_llm)
    # Should complete without raising an exception
    await evaluator.evaluate("Implement a simple requests fetcher.")
    assert mock_llm.complete_json.called


@pytest.mark.asyncio
async def test_taste_gate_rejects_bloat():
    mock_llm = AsyncMock()
    mock_llm.complete_json.return_value = TasteResponse(
        scores=TasteScores(
            simplicity=0.4, performance=0.5, robustness=0.7, security=0.9
        ),
        feedback="Over-engineered. Do not use Celery and Redis for a simple daily cron task.",
        is_tasteful=False,
    )

    evaluator = TasteEvaluator(mock_llm)
    # Should raise TasteFrictionBlock
    with pytest.raises(TasteFrictionBlock) as excinfo:
        await evaluator.evaluate(
            "Setup Celery + Redis + Postgres to run a single task daily."
        )

    assert "Celery and Redis" in excinfo.value.feedback
    assert excinfo.value.scores.simplicity == 0.4
