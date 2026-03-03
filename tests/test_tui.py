"""Tests for the Textual TUI (headless via pilot)."""

from unittest.mock import patch, MagicMock

from textual.widgets import Footer, Header, OptionList

from uw_s3.tui.app import UWS3App
from uw_s3.tui.screens.base import EndpointBar
from uw_s3.tui.screens.confirm import ConfirmScreen
from uw_s3.tui.screens.main_menu import MainMenuScreen


def _make_app() -> UWS3App:
    """Create a UWS3App with a mocked Minio client."""
    with patch("uw_s3.Minio"):
        return UWS3App(access_key="test", secret_key="test")


async def test_app_launches_main_menu() -> None:
    app = _make_app()
    async with app.run_test() as _pilot:
        assert isinstance(app.screen, MainMenuScreen)


async def test_main_menu_has_expected_widgets() -> None:
    app = _make_app()
    async with app.run_test() as _pilot:
        app.screen.query_one(Header)
        app.screen.query_one(Footer)
        app.screen.query_one(EndpointBar)
        app.screen.query_one(OptionList)


async def test_main_menu_option_list_has_four_options() -> None:
    app = _make_app()
    async with app.run_test() as _pilot:
        ol = app.screen.query_one(OptionList)
        assert ol.option_count == 4


async def test_quit_key() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("q")
        assert app.return_code is not None or app._exit


async def test_endpoint_switch() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        assert app.endpoint_label == "Campus"
        await pilot.press("e")
        assert app.endpoint_label == "Web"
        await pilot.press("e")
        assert app.endpoint_label == "Campus"


async def test_endpoint_label_updates_subtitle() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        assert "Campus" in app.sub_title
        await pilot.press("e")
        assert "Web" in app.sub_title


async def test_navigate_to_bucket_management() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        with patch.object(app.s3, "list_buckets", return_value=[]):
            await pilot.press("b")
            await pilot.pause()
            from uw_s3.tui.screens.bucket_management import BucketManagementScreen

            assert isinstance(app.screen, BucketManagementScreen)


async def test_navigate_back_with_escape() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        with patch.object(app.s3, "list_buckets", return_value=[]):
            await pilot.press("b")
            await pilot.pause()
            from uw_s3.tui.screens.bucket_management import BucketManagementScreen

            assert isinstance(app.screen, BucketManagementScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MainMenuScreen)


async def test_confirm_screen_yes() -> None:
    app = _make_app()
    results: list[bool] = []

    async with app.run_test() as pilot:
        app.push_screen(ConfirmScreen("Delete?"), callback=results.append)
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)

        await pilot.click("#confirm-yes")
        await pilot.pause()
        assert results == [True]


async def test_confirm_screen_no() -> None:
    app = _make_app()
    results: list[bool] = []

    async with app.run_test() as pilot:
        app.push_screen(ConfirmScreen("Delete?"), callback=results.append)
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)

        await pilot.click("#confirm-no")
        await pilot.pause()
        assert results == [False]


async def test_unmount_cleans_active_mounts() -> None:
    app = _make_app()
    mock_rm = MagicMock()
    app.active_mounts["test-bucket"] = mock_rm

    async with app.run_test() as _pilot:
        pass  # app exits, triggering on_unmount

    mock_rm.unmount.assert_called_once()
    assert app.active_mounts == {}
