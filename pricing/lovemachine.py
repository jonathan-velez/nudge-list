"""Collection-wide Shopify stock comparator, hosted by the existing helper."""
import datetime as dt
import json
import re
from pathlib import Path
import urllib.request

ORIGIN = 'https://lovemachinesurfboards.com'
COLLECTION = ORIGIN + '/collections/all-fm'
LIMIT = 250

def fetch_page(page, collection=COLLECTION):
    request = urllib.request.Request(
        f'{collection}/products.json?limit={LIMIT}&page={page}',
        headers={'Accept': 'application/json', 'User-Agent': 'NudgeList/1.0 inventory monitor'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

def sizes(text):
    text = text.lower().translate(str.maketrans({'′': "'", '’': "'", '‘': "'", '″': '"', '“': '"', '”': '"', '–': '-', '−': '-'}))
    return {f"{int(feet)}'{int(inches)}" for feet, inches in re.findall(
        r"(?<![\w.])(\d+)\s*(?:'+|ft\.?|feet|foot|-)\s*(\d{1,2})(?![\d.])", text)}

def identity(value):
    if type(value) not in (int, str) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError('Invalid Shopify identity')
    return str(value)

def normalize(products, origin=ORIGIN, target_sizes=None, require_brand=False):
    target_sizes = {"6'4", "6'6"} if target_sizes is None else target_sizes
    result = {}
    seen = set()
    for product in products:
        if not isinstance(product, dict):
            raise ValueError('Invalid product')
        pid = identity(product.get('id'))
        if pid in seen:
            raise ValueError('Duplicate product across collection pages; retry next check')
        seen.add(pid)
        title, handle, variants = (product.get(k) for k in ('title', 'handle', 'variants'))
        if not isinstance(title, str) or not title or not isinstance(handle, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', handle):
            raise ValueError('Invalid product title/handle')
        if not isinstance(variants, list) or not variants or len(variants) >= LIMIT:
            raise ValueError('Missing or potentially truncated variants')
        model = bool(re.search(r'(?<!\w)fm(?!\w)', title, re.I))
        if require_brand:
            model = model and bool(re.search(r'(?<!\w)love\s*machine(?!\w)',
                                             title + ' ' + str(product.get('vendor', '')), re.I))
        for variant in variants:
            if not isinstance(variant, dict) or type(variant.get('available')) is not bool:
                raise ValueError('Missing boolean purchase availability')
            vid = identity(variant.get('id'))
            texts = [variant.get(k) for k in ('title', 'option1', 'option2', 'option3')]
            if any(t is not None and not isinstance(t, str) for t in texts):
                raise ValueError('Invalid variant description')
            # A size selected by the variant overrides a size in the product title.
            found = sizes(' '.join(t for t in texts if t)) or sizes(title)
            if not model or len(found) != 1 or not found <= target_sizes:
                continue
            key = pid + ':' + vid
            if key in result:
                raise ValueError('Duplicate matching variant')
            price = variant.get('price')
            if price is not None and (not isinstance(price, str) or not re.fullmatch(r'\d+(?:\.\d+)?', price)):
                raise ValueError('Invalid variant price')
            result[key] = {'product_id': pid, 'variant_id': vid, 'title': title,
                           'size': next(iter(found)), 'available': variant['available'],
                           'price': price, 'url': f'{origin}/products/{handle}?variant={vid}'}
    return dict(sorted(result.items()))

def collect(fetch=fetch_page, state=Path('/state/lovemachine'), now=None, *,
            origin=ORIGIN, target_sizes=None, require_brand=False,
            report_title='LoveMachine FM inventory'):
    products = []
    for page in range(1, 21):
        payload = fetch(page)
        if not isinstance(payload, dict) or not isinstance(payload.get('products'), list):
            raise ValueError('Expected Shopify products array; preserve baseline')
        rows = payload['products']
        if len(rows) > LIMIT:
            raise ValueError('Invalid collection page size')
        products.extend(rows)
        if len(rows) < LIMIT:
            break
    else:
        raise ValueError('Collection pagination safety limit reached; preserve baseline')
    if not products:
        raise ValueError('Empty FM collection; preserve baseline')
    current = normalize(products, origin, target_sizes, require_brand)
    state = Path(state)
    path = state / 'latest.json'
    previous = json.loads(path.read_text()) if path.exists() else None
    old = previous['boards'] if previous else {}
    events = []
    for key, row in current.items():
        prior = old.get(key)
        if previous and row['available'] and (prior is None or not prior['available']):
            reason = 'new listing' if prior is None else 'restock'
            events.append(f'{reason} | {row["title"]} | size {row["size"]} | price {row["price"] or "unknown"} (store currency) | {row["url"]}')
    revision = previous['revision'] if previous else 0
    report = previous['report'] if previous else report_title + '\nInitial inventory baseline stored. Waiting for new in-stock listings or restocks.\n'
    if events:
        revision += 1
        report = '\n'.join([report_title, f'Availability event #{revision}', *events]) + '\n'
    # Keep missing identities and their last stock state. An incomplete but valid
    # page must not turn an available board into a spurious restock on recovery.
    stored = {'captured_at': (now or dt.datetime.now(dt.timezone.utc)).isoformat(),
              'boards': old | current, 'observed': current,
              'revision': revision, 'report': report}
    state.mkdir(parents=True, exist_ok=True)
    tmp = state / 'latest.tmp'
    tmp.write_text(json.dumps(stored, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)
    return report
