from contextlib import ExitStack
from dataclasses import dataclass, fields
from types import TracebackType
from typing import Any, Self

from camoufox.sync_api import Camoufox
from patchright.sync_api import (
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


class _RunnerBase:
    def __init__(
        self,
        *,
        browser_options: dict[str, Any] | None = None,
        context_options: dict[str, Any] | None = None,
        recycle: RecycleEvery | None = None,
    ) -> None:
        self._recycle = recycle or RecycleEvery()
        self._browser_options = dict(browser_options or {})
        self._context_options = dict(context_options or {})
        self._browser = None
        self._context = None
        self._page: Page | None = None
        self._page_calls = 0
        self._entered = False

    def __enter__(self) -> Self:
        self._entered = True
        return self

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

    def _open_page(self) -> None:
        self._page = self._context.new_page()

    def _close_page(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None

    def _open_context(self) -> None:
        self._context = self._browser.new_context(**self._context_options)
        self._open_page()

    def _close_context(self) -> None:
        self._close_page()
        if self._context is not None:
            self._context.close()
            self._context = None


class PatchrightRunner(_RunnerBase):
    def __init__(
        self,
        *,
        browser_options: dict[str, Any] | None = None,
        context_options: dict[str, Any] | None = None,
        recycle: RecycleEvery | None = None,
    ) -> None:
        super().__init__(
            browser_options=browser_options,
            context_options=context_options,
            recycle=recycle,
        )
        self._pw: Playwright | None = None

    def __enter__(self) -> Self:
        self._pw = sync_playwright().start()
        return super().__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._entered:
            return
        self._close_browser()
        self._pw.stop()
        self._pw = None
        self._entered = False
        self._page_calls = 0

    def _open_browser(self) -> None:
        self._browser = self._pw.chromium.launch(**self._browser_options)
        self._open_context()

    def _close_browser(self) -> None:
        self._close_context()
        if self._browser is not None:
            self._browser.close()
        self._browser = None


class CamoufoxRunner(_RunnerBase):
    def __init__(
        self,
        *,
        browser_options: dict[str, Any] | None = None,
        context_options: dict[str, Any] | None = None,
        recycle: RecycleEvery | None = None,
    ) -> None:
        super().__init__(
            browser_options=browser_options,
            context_options=context_options,
            recycle=recycle,
        )
        self._stack: ExitStack | None = None

    def __enter__(self) -> Self:
        self._stack = ExitStack()
        return super().__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._entered:
            return
        self._close_browser()
        self._stack = None
        self._entered = False
        self._page_calls = 0

    def _open_browser(self) -> None:
        self._browser = self._stack.enter_context(Camoufox(**self._browser_options))
        self._open_context()

    def _close_browser(self) -> None:
        self._close_context()
        self._stack.close()
        self._browser = None


def run_patchright(
    *,
    browser_options: dict[str, Any] | None = None,
    context_options: dict[str, Any] | None = None,
    recycle: RecycleEvery | None = None,
) -> PatchrightRunner:
    return PatchrightRunner(
        browser_options=browser_options,
        context_options=context_options,
        recycle=recycle,
    )


def run_camoufox(
    *,
    browser_options: dict[str, Any] | None = None,
    context_options: dict[str, Any] | None = None,
    recycle: RecycleEvery | None = None,
) -> CamoufoxRunner:
    return CamoufoxRunner(
        browser_options=browser_options,
        context_options=context_options,
        recycle=recycle,
    )
