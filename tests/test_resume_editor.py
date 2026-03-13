import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from hr_breaker.agents.resume_editor import edit_resume
from hr_breaker.models.editor import EditResult, ResumePatch


@pytest.mark.asyncio
async def test_edit_resume_returns_edit_result():
    """Test that edit_resume calls agent and returns EditResult."""
    expected = EditResult(
        patches=[ResumePatch(selector="#summary", action="replace", html="<p>New</p>")],
        reasoning="Updated summary",
    )
    mock_result = MagicMock()
    mock_result.output = expected

    with patch("hr_breaker.agents.resume_editor.Agent") as MockAgent:
        instance = MockAgent.return_value
        instance.run = AsyncMock(return_value=mock_result)

        result = await edit_resume("<p>Old</p>", "Original text", "Update summary")

        assert isinstance(result, EditResult)
        assert len(result.patches) == 1
        assert result.patches[0].selector == "#summary"
        instance.run.assert_called_once()
