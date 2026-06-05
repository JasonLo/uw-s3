"""Tests for the Textual TUI (headless via pilot)."""

from unittest.mock import patch, MagicMock

from textual.widgets import Footer, Header, OptionList

from uw_s3.bucket_registry import CAMPUS_ENDPOINT, WEB_ENDPOINT, BucketRegistry
from uw_s3.tui.app import UWS3App
from uw_s3.tui.screens.base import NetworkBar, network_status_text
from uw_s3.tui.screens.confirm import ConfirmScreen
from uw_s3.tui.screens.main_menu import MainMenuScreen


def _make_app() -> UWS3App:
    """Create a UWS3App with a mocked Minio client and an offline router.

    The router's probe is stubbed and its registry reset so tests never touch
    the network or the on-disk bucket cache.
    """
    with patch("uw_s3.client.Minio"):
        app = UWS3App(access_key="test", secret_key="test")
    app.s3.registry = BucketRegistry()
    app.s3.probe = lambda: None  # type: ignore[method-assign]
    return app


async def test_app_launches_main_menu() -> None:
    app = _make_app()
    async with app.run_test() as _pilot:
        assert isinstance(app.screen, MainMenuScreen)


async def test_main_menu_has_expected_widgets() -> None:
    app = _make_app()
    async with app.run_test() as _pilot:
        app.screen.query_one(Header)
        app.screen.query_one(Footer)
        app.screen.query_one(NetworkBar)
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
        await pilot.pause()
        assert app.return_code is not None or not app.is_running


def test_network_status_text() -> None:
    assert "offline" in network_status_text(set())
    assert "Campus + Web" in network_status_text({CAMPUS_ENDPOINT, WEB_ENDPOINT})
    assert "Web only" in network_status_text({WEB_ENDPOINT})


async def test_network_bar_present() -> None:
    app = _make_app()
    async with app.run_test() as _pilot:
        app.screen.query_one(NetworkBar)


async def test_no_endpoint_switch_binding() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        # 'e' was the old endpoint-switch key; it must no longer change anything.
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, MainMenuScreen)


async def test_navigate_to_bucket_management() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        with patch.object(app.s3, "list_buckets", return_value=[]):
            await pilot.press("1")
            await pilot.pause()
            from uw_s3.tui.screens.bucket_management import BucketManagementScreen

            assert isinstance(app.screen, BucketManagementScreen)


async def test_navigate_back_with_escape() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        with patch.object(app.s3, "list_buckets", return_value=[]):
            await pilot.press("1")
            await pilot.pause()
            from uw_s3.tui.screens.bucket_management import BucketManagementScreen

            assert isinstance(app.screen, BucketManagementScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MainMenuScreen)


async def test_confirm_screen_yes() -> None:
    app = _make_app()
    results: list[bool | None] = []

    async with app.run_test() as pilot:
        app.push_screen(ConfirmScreen("Delete?"), callback=results.append)
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)

        await pilot.click("#confirm-yes")
        await pilot.pause()
        assert results == [True]


async def test_confirm_screen_no() -> None:
    app = _make_app()
    results: list[bool | None] = []

    async with app.run_test() as pilot:
        app.push_screen(ConfirmScreen("Delete?"), callback=results.append)
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)

        await pilot.click("#confirm-no")
        await pilot.pause()
        assert results == [False]


async def test_confirm_screen_escape_dismisses_as_false() -> None:
    app = _make_app()
    results: list[bool | None] = []

    async with app.run_test() as pilot:
        app.push_screen(ConfirmScreen("Delete?"), callback=results.append)
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert results == [False]


async def test_navigate_to_file_manager() -> None:
    app = _make_app()
    async with app.run_test() as pilot:
        with patch.object(app.s3, "list_buckets", return_value=[]):
            await pilot.press("2")
            await pilot.pause()
            from uw_s3.tui.screens.file_manager import FileManagerScreen

            assert isinstance(app.screen, FileManagerScreen)


async def test_unmount_cleans_active_mounts() -> None:
    app = _make_app()
    mock_rm = MagicMock()
    app.active_mounts["test-bucket"] = mock_rm

    async with app.run_test() as _pilot:
        pass  # app exits, triggering on_unmount

    mock_rm.unmount.assert_called_once()
    assert app.active_mounts == {}
