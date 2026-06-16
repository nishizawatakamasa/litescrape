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
class Span:
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
        browser: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        span: Span | None = None,
    ) -> None:
        self._span = span or Span()
        self._browser_kw = dict(browser or {})
        self._context_kw = dict(context or {})
        self._browser = None
        self._ctx = None
        self._page: Page | None = None
        self._i = 0
        self._active = False

    def page(self) -> Page:
        if not self._active:
            raise RuntimeError('with ブロックの外で page() を呼べません')
        if self._page is None:
            self._open_browser()
        elif (b := self._span.browser) and self._i % b == 0:
            self._close_browser()
            self._open_browser()
        elif (c := self._span.context) and self._i % c == 0:
            self._close_context()
            self._open_context()
        elif (p := self._span.page) and self._i % p == 0:
            self._close_page()
            self._open_page()
        self._i += 1
        return self._page

    def _open_page(self) -> None:
        self._page = self._ctx.new_page()

    def _close_page(self) -> None:
        if self._page:
            self._page.close()
            self._page = None

    def _open_context(self) -> None:
        self._ctx = self._browser.new_context(**self._context_kw)
        self._open_page()

    def _close_context(self) -> None:
        self._close_page()
        if self._ctx:
            self._ctx.close()
            self._ctx = None


class PatchrightRunner(_RunnerBase):
    def __init__(
        self,
        *,
        browser: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        span: Span | None = None,
    ) -> None:
        super().__init__(browser=browser, context=context, span=span)
        self._pw: Playwright | None = None

    def __enter__(self) -> Self:
        self._pw = sync_playwright().start()
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._active:
            return
        self._close_browser()
        if self._pw:
            self._pw.stop()
            self._pw = None
        self._active = False
        self._i = 0

    def _open_browser(self) -> None:
        self._browser = self._pw.chromium.launch(**self._browser_kw)
        self._open_context()

    def _close_browser(self) -> None:
        self._close_context()
        if self._browser:
            self._browser.close()
        self._browser = None


class CamoufoxRunner(_RunnerBase):
    def __init__(
        self,
        *,
        browser: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        span: Span | None = None,
    ) -> None:
        super().__init__(browser=browser, context=context, span=span)
        self._fox_stack: ExitStack | None = None

    def __enter__(self) -> Self:
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self._active:
            return
        self._close_browser()
        self._active = False
        self._i = 0

    def _open_browser(self) -> None:
        self._fox_stack = ExitStack()
        self._browser = self._fox_stack.enter_context(Camoufox(**self._browser_kw))
        self._open_context()

    def _close_browser(self) -> None:
        self._close_context()
        if self._fox_stack:
            self._fox_stack.close()
            self._fox_stack = None
        self._browser = None


def run_patchright(
    *,
    browser: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    span: Span | None = None,
) -> PatchrightRunner:
    return PatchrightRunner(browser=browser, context=context, span=span)


def run_camoufox(
    *,
    browser: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    span: Span | None = None,
) -> CamoufoxRunner:
    return CamoufoxRunner(browser=browser, context=context, span=span)
