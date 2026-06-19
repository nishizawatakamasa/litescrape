from contextlib import ExitStack
from dataclasses import dataclass, fields
from types import TracebackType
from typing import Any, Protocol, Self

from camoufox.sync_api import Camoufox
from patchright.sync_api import (
    Browser,
    Page as PatchrightPage,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import Page as PlaywrightPage

Page = PatchrightPage | PlaywrightPage


@dataclass(frozen=True, slots=True)
class RecycleEvery:
    browser: int | None = None
    context: int | None = None
    page: int | None = None

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if value is not None and value < 1:
                raise ValueError(f'{f.name} は 1 以上で指定してください (got {value})')


class _Driver(Protocol):
    @property
    def browser(self) -> Browser: ...

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def launch(self, options: dict[str, Any]) -> None: ...
    def close(self) -> None: ...


class _PatchrightDriver:
    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError('browser が起動していません')
        return self._browser

    def start(self) -> None:
        self._pw = sync_playwright().start()

    def stop(self) -> None:
        if self._pw is not None:
            self._pw.stop()
            self._pw = None

    def launch(self, options: dict[str, Any]) -> None:
        self._browser = self._pw.chromium.launch(**options)

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None


class _CamoufoxDriver:
    def __init__(self) -> None:
        self._stack: ExitStack | None = None
        self._browser: Browser | None = None

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError('browser が起動していません')
        return self._browser

    def start(self) -> None:
        self._stack = ExitStack()

    def stop(self) -> None:
        self._stack = None

    def launch(self, options: dict[str, Any]) -> None:
        self._browser = self._stack.enter_context(Camoufox(**options))

    def close(self) -> None:
        if self._browser is not None:
            self._stack.close()
            self._browser = None


class BrowseSession:
    def __init__(
        self,
        driver: _Driver,
        *,
        browser_options: dict[str, Any] | None = None,
        context_options: dict[str, Any] | None = None,
        recycle: RecycleEvery | None = None,
    ) -> None:
        self._driver = driver
        self._recycle = recycle or RecycleEvery()
        self._browser_options = dict(browser_options or {})
        self._context_options = dict(context_options or {})
        self._context = None
        self._page: Page | None = None
        self._page_calls = 0
        self._entered = False

    def __enter__(self) -> Self:
        self._driver.start()
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._entered:
            return
        self._close_browser()
        self._driver.stop()
        self._entered = False
        self._page_calls = 0

    def page(self) -> Page:
        if not self._entered:
            raise RuntimeError('with ブロックの外で page() を呼べません')
        if self._page is None:
            self._open_browser()
        elif (b := self._recycle.browser) and self._page_calls % b == 0:
            self._close_browser()
            self._open_browser()
        elif (c := self._recycle.context) and self._page_calls % c == 0:
            self._close_context()
            self._open_context()
        elif (p := self._recycle.page) and self._page_calls % p == 0:
            self._close_page()
            self._open_page()
        self._page_calls += 1
        return self._page

    def _open_browser(self) -> None:
        self._driver.launch(self._browser_options)
        self._open_context()

    def _close_browser(self) -> None:
        self._close_context()
        self._driver.close()

    def _open_context(self) -> None:
        self._context = self._driver.browser.new_context(**self._context_options)
        self._open_page()

    def _close_context(self) -> None:
        self._close_page()
        if self._context is not None:
            self._context.close()
            self._context = None

    def _open_page(self) -> None:
        self._page = self._context.new_page()

    def _close_page(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None


def open_patchright(
    *,
    browser_options: dict[str, Any] | None = None,
    context_options: dict[str, Any] | None = None,
    recycle: RecycleEvery | None = None,
) -> BrowseSession:
    return BrowseSession(
        _PatchrightDriver(),
        browser_options=browser_options,
        context_options=context_options,
        recycle=recycle,
    )


def open_camoufox(
    *,
    browser_options: dict[str, Any] | None = None,
    context_options: dict[str, Any] | None = None,
    recycle: RecycleEvery | None = None,
) -> BrowseSession:
    return BrowseSession(
        _CamoufoxDriver(),
        browser_options=browser_options,
        context_options=context_options,
        recycle=recycle,
    )
