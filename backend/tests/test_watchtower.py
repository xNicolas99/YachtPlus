from unittest.mock import patch, MagicMock
import pytest

from api.services.watchtower import update_compose_project

@patch("api.services.watchtower.logger")
@patch("api.services.watchtower.compose_action", new_callable=MagicMock)
def test_update_compose_project_success(mock_compose_action, mock_logger):
    """
    Test that update_compose_project successfully calls compose_action twice
    and logs appropriately.
    """
    # Act
    update_compose_project("test_project")

    # Assert
    assert mock_compose_action.call_count == 2
    mock_compose_action.assert_any_call("test_project", "pull")
    mock_compose_action.assert_any_call("test_project", "up")

    mock_logger.info.assert_any_call("Auto-updating project: test_project")
    mock_logger.info.assert_any_call("Successfully updated test_project")

@patch("api.services.watchtower.logger")
@patch("api.services.watchtower.compose_action", new_callable=MagicMock)
def test_update_compose_project_exception(mock_compose_action, mock_logger):
    """
    Test that update_compose_project handles exceptions raised by compose_action,
    and logs the error instead of bubbling up.
    """
    # Arrange
    mock_compose_action.side_effect = Exception("Test error")

    # Act
    update_compose_project("test_project")

    # Assert
    mock_compose_action.assert_called_once_with("test_project", "pull")
    mock_logger.error.assert_called_once_with("Failed to update test_project: Test error")
