# LiteScrape

自分用・非汎用

## インストール
`uv add litescrape`  

※ `run_patchright` を使うとき：Google ChromeをPCにインストールしておく。  
※ `run_camoufox` を使うとき：`uv run camoufox fetch`  

## 実装機能

### litescrape

- `LitePage`
- `LiteElement`
- `LiteElementGroup`
- `ElementScan`
- `LiteFrame`
- `LiteShadowRoot`
- `LiteParser`
- `LiteNode`
- `LiteNodeGroup`
- `NodeScan`

### litescrape.utils

- `parse_html(path: Path) -> LexborHTMLParser | None`
- `meta_html(meta: Mapping[str, object | None]) -> str`
- `from_here(file: str) -> Callable[[str], Path]`
- `append_csv(path: Path, row: dict) -> None`
- `write_csv(path: Path, rows: list[dict]) -> None`
- `write_parquet(path: Path, rows: list[dict]) -> None`
- `hash_name(key: str) -> str`
- `write_text(path: Path, data: str) -> bool`
- `write_bytes(path: Path, data: bytes) -> bool`
- `save_log(path: Path, level: str = 'WARNING') -> None`
- `process_map[T, R](worker: Callable[[T], R], items: Iterable[T], workers: int | None = None, *, chunksize: int | None = None) -> list[R | None]`
- `glob_paths(dir_path: Path, pattern: str = '*.html') -> list[str]`
- `counter(start: int = 1) -> Iterator[int]`

### litescrape.browser

- `Span`
- `run_patchright(*, browser: dict | None = None, context: dict | None = None, span: Span | None = None) -> PatchrightRunner`
- `run_camoufox(*, browser: dict | None = None, context: dict | None = None, span: Span | None = None) -> CamoufoxRunner`
- `PatchrightRunner.page() -> Page` / `CamoufoxRunner.page() -> Page`

`browser` / `context` は Playwright へ渡す起動オプション。`span` は litescrape の再生成間隔（`page()` 呼び出し回数ごとに独立して効く。省略時は再生成しない）。`page()` を呼ぶたびに内部カウントが 1 進む。

## 使用例

### crawl.py
```python
from urllib.parse import urlencode

from litescrape import lite_page
from litescrape.browser import Span, run_patchright
from litescrape.utils import save_log, from_here, counter, write_csv

here = from_here(__file__)
save_log(here('log/crawling.log'))

with run_patchright(
    browser={'channel': 'chrome', 'headless': False},
    context={'viewport': {'width': 1920, 'height': 1080}},
    span=Span(browser=300, context=100, page=20),
) as pr:
    page = s.page()
    p = lite_page(page)
    p.goto('https://home.katitas.jp/buyers_search')
    prefecture_urls = p.ii('div ul li a[href^="https://home.katitas.jp/buyers_search/area"]').urls

    n = len(prefecture_urls)
    urls = []
    for i, prefecture_url in enumerate(prefecture_urls):
        print(f'prefecture_url {i}/{n - 1}')
        for page_num in counter():
            page = s.page()
            p = lite_page(page)
            if not p.goto(f'{prefecture_url}?{urlencode({"page": page_num})}', sleep_after=(0.5, 1)):
                break
            if not (bukken_elems := p.ii('ul li div a[href^="https://home.katitas.jp"]:has(p)')):
                break
            urls.extend(bukken_elems.urls)
write_csv(here('csv/urls.csv'), [{'url': url} for url in urls])
```

### scrape.py
```python
from datetime import datetime, timezone
import time

import pandas as pd

from litescrape import lite_page
from litescrape.browser import Span, run_patchright
from litescrape.utils import (
    save_log,
    append_csv,
    from_here,
    meta_html,
    hash_name,
    write_text,
    write_bytes,
)

here = from_here(__file__)
save_log(here('log/scraping.log'))

items = list(pd.read_csv(here('csv/urls.csv'))['url'].items())
n = len(items)

with run_patchright(
    browser={'channel': 'chrome', 'headless': False},
    context={'viewport': {'width': 1920, 'height': 1080}},
    span=Span(browser=300, context=100),
) as pr:
    for url_index, request_url in items:
        print(f'url_index {url_index}/{n - 1}')
        page = s.page()
        p = lite_page(page)
        if not p.goto(request_url):
            append_csv(here('csv/failed.csv'), {
                'url_index': url_index,
                'request_url': request_url,
                'reason': 'goto',
            })
            continue
        html = meta_html({
            'litescrape:url_index': url_index,
            'litescrape:saved_at': datetime.now(timezone.utc),
            'litescrape:request_url': request_url,
            'litescrape:final_url': page.url,
        }) + page.content()
        if not write_text(here('html') / f'{hash_name(page.url)}.html', html):
            append_csv(here('csv/failed.csv'), {
                'url_index': url_index,
                'request_url': request_url,
                'reason': 'write_text',
            })

        page.screenshot(path=here(f'media/{url_index}-full-page.png'), full_page=True)

        elem_iframe = p.i('iframe[src^="https://home.katitas.jp"]')
        elem_iframe.scroll_into_view()
        time.sleep(3)
        elem_iframe.screenshot(here(f'media/{url_index}-gmap.png'), isolate=True)

        img_li_scan = p.ii('p.text-left').scan.m(r'画像をクリックすると拡大画像がご覧に').n('ul').ii('li').scan
        img_li = img_li_scan.m(r'外観') or img_li_scan.m(r'^(?!.*間取).*')
        img_url = img_li.i('a').url
        if (body := p.bytes_at(img_url)):
            write_bytes(here(f'media/{url_index}-img-desc.jpg'), body)

        main_img_url = p.i('img.w-full.object-contain').src
        if (body := p.bytes_at(main_img_url)):
            write_bytes(here(f'media/{url_index}-img-main.jpg'), body)
```

### extract.py
```python
from pathlib import Path

from litescrape import lite_parser
from litescrape.utils import from_here, glob_paths, parse_html, process_map, write_parquet

def main():
    here = from_here(__file__)
    html_paths = glob_paths(here('html'), '*.html')
    results = [r for r in process_map(extract, html_paths) if r]
    write_parquet(here('parquet/extract.parquet'), results)

def extract(file_path: str) -> dict | None:
    if not (parser := parse_html(Path(file_path))):
        return None
    p = lite_parser(parser)
    dt_scan = p.ii('dt').scan
    dd_text = lambda pattern: dt_scan.m(pattern).n('dd').text
    return {
        'url_index': p.i('meta[name="litescrape:url_index"]').attr('content'),
        'saved_at': p.i('meta[name="litescrape:saved_at"]').attr('content'),
        'request_url': p.i('meta[name="litescrape:request_url"]').attr('content'),
        'final_url': p.i('meta[name="litescrape:final_url"]').attr('content'),
        'ファイル名': Path(file_path).name,

        '取り扱い店舗': p.ii('p').scan.m(r'取り扱い店舗').n('p').text,
        
        '価格': dd_text(r'価格'),
        '月々の支払い': dd_text(r'月々の支払い'),
        '間取': dd_text(r'間取'),
        '土地面積': dd_text(r'土地面積'),
        '建物面積': dd_text(r'建物面積'),
        
        '所在地': dd_text(r'所在地'),
        '交通': dd_text(r'交通'),
        '接道状況': dd_text(r'接道状況'),
        '私道面積': dd_text(r'私道面積'),
        'セットバック': dd_text(r'セットバック'),
        '建物構造': dd_text(r'建物構造'),
        '国土法提出': dd_text(r'国土法提出'),
        '駐車場': dd_text(r'駐車場'),
        '車庫区分': dd_text(r'車庫区分'),
        '都市計画': dd_text(r'都市計画'),
        '物件種別': dd_text(r'物件種別'),
        '建ぺい率 /容積率': dd_text(r'建ぺい率.*容積率'),
        '土地権利': dd_text(r'土地権利'),
        '地目': dd_text(r'地目'),
        '築年月': dd_text(r'築年月'),
        '取引態様': dd_text(r'取引態様'),
        '引渡日（入居予定日）': dd_text(r'引渡日.*入居予定日'),
        '用途地域': dd_text(r'用途地域'),
        '現況': dd_text(r'現況'),
        '設備・条件': dd_text(r'設備.*条件'),
        '備考': dd_text(r'備考'),
        '最寄りの学校': dd_text(r'最寄.*の学校'),
        '物件番号': dd_text(r'物件番号'),
        '情報更新日': dd_text(r'情報更新日'),
        '次回更新予定日': dd_text(r'次回更新予定日'),
        
        'スタッフからのコメント': p.ii('div').scan.m(r'スタッフからのコメント').n('div').text,
        '物件の魅力': p.ii('p').scan.m(r'物件の魅力').n('p').text,
        
        'img_desc': '\n'.join(p.ii('p.text-left').scan.m(r'画像をクリックすると拡大画像がご覧に').n('ul').ii('li').texts)
    }

if __name__ == '__main__':
    main()
```

### clean.ipynb
```python
import re

import pandas as pd
```
```python
df_shikutyoson = pd.read_csv('./shikutyoson.csv')
cities = df_shikutyoson["市区町村"].dropna().sort_values(key=lambda x: x.str.len(), ascending=False)
shikutyoson_pattern = "|".join(cities.map(lambda x: re.escape(x)))
```
```python
df_raw = pd.read_parquet('parquet/extract.parquet')
df_raw = df_raw.apply(lambda x: x.fillna('').str.normalize('NFKC').str.strip())
```
```python
df = df_raw.sort_values('saved_at')[['url_index', 'saved_at', 'request_url', 'final_url']].copy()

df['事例種別'] = df_raw['物件種別'].str.contains(r'中古|土地').map({True: '中古売出'})
df['総額'] = (
    df_raw['価格']
    .str.extract(r'([,\d]+)\s*万円', expand=False)
    .replace(',', '', regex=True)
    .pipe(lambda s: pd.to_numeric(s, errors='coerce') * 10000)
)
df['土地面積'] = df_raw['土地面積'].str.extract(r'([\d\.]+)')
df['建物面積'] = df_raw['建物面積'].str.extract(r'([\d\.]+)')
df['建物種別'] = df_raw['物件種別'].map({'中古戸建': '戸建て', '中古マンション': 'マンション', '土地': '土地'})
df[['所在都道府県', '所在市', '所在字', '所在番地']] = df_raw['所在地'].str.extract(fr'^(京都府|.+?[都道府県])({shikutyoson_pattern})(\D*)(.*)')

s1 = (
    df_raw['築年月']
    .replace({r'元年': r'1年'}, regex=True)
    .str.extract(r'(\d+)年', expand=False)
    .pipe(lambda s: pd.to_numeric(s, errors='coerce'))
)
s2 = df_raw['築年月'].str[:2].map({'令和': 2018, '平成': 1988, '昭和': 1925, '大正': 1911, '明治': 1867})
df['建築年'] = s1 + s2

df['構造体'] = df_raw['建物構造'].str.extract(r'^(\S+)')
df['階層'] = df_raw['建物構造'].str.extract(r'(\d+)階')
df['リノベ内容'] = df_raw['備考'].str.extract(r'(?s)^(20\d{2}/.*?)\n\D')
df['間取'] = df_raw['間取']
df['成約年月'] = df_raw['現況'].map({'空': '販売中', '古家付': '販売中'})
df['私道負担'] = df_raw['私道面積']
df['接道'] = df_raw['接道状況']

s1 = df_raw['最寄りの学校'].str.extract(r'([^/\s【】・、(]+?小学校)', expand=False) 
s2 = df_raw['物件の魅力'].str.extract(r'([^/\s【】・、(]+?小学校)', expand=False)
s3 = df_raw['備考'].str.extract(r'([^/\s【】・、(]+?小学校)', expand=False)
s4 = df_raw['img_desc'].str.extract(r'([^/\s【】・、(]+?小学校)', expand=False) 
df['小学校'] = s1.fillna(s2).fillna(s3).fillna(s4)

s1 = df_raw['最寄りの学校'].str.extract(r'([^/\s【】・、(]+?中学校)', expand=False) 
s2 = df_raw['物件の魅力'].str.extract(r'([^/\s【】・、(]+?中学校)', expand=False)
s3 = df_raw['備考'].str.extract(r'([^/\s【】・、(]+?中学校)', expand=False)
s4 = df_raw['img_desc'].str.extract(r'([^/\s【】・、(]+?中学校)', expand=False) 
df['中学校'] = s1.fillna(s2).fillna(s3).fillna(s4)

df['周辺環境'] = df_raw['備考'].map(lambda x: '\n'.join(l for l in x.splitlines() if re.search(r'(?:\d分|\dm)$', l)))
df['都市計画'] = df_raw['都市計画']
df['用途地域'] = df_raw['用途地域']
df[['建ぺい率', '容積率']] = df_raw['建ぺい率 /容積率'].str.extract(r'(\d+%)\D*(\d+%)')
df['水道'] = df_raw['設備・条件'].str.extract(r'(公営水道|上水道)')
df['下水'] = df_raw['設備・条件'].str.extract(r'(本下水|個別浄化槽|汲取|下水道)')
df['ガス'] = df_raw['設備・条件'].str.extract(r'(個別LPG|集中LPG|都市ガス|プロパンガス|オール電化)')
df['契約態様'] = df_raw['取引態様']
df['問合せ先'] = df_raw['取り扱い店舗']
df['駐車場'] = df_raw['駐車場']
df['交通'] = df_raw['交通']
df['物件の特徴'] = df_raw['物件の魅力']
df['仕様'] = df_raw['設備・条件']

df['土地権利'] = df_raw['土地権利']
df['地目'] = df_raw['地目']
df['引渡日（入居予定日）'] = df_raw['引渡日（入居予定日）']
df['物件番号'] = df_raw['物件番号']
df['情報更新日'] = df_raw['情報更新日']
```
```python
df.to_clipboard(index=False)
```