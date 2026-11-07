"""CSV validation and sales metrics, independent of the user interface."""
import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd

COLUMNS = ['order_id', 'customer_id', 'order_date', 'status', 'product_id',
           'category', 'quantity', 'unit_price_rub']
CLEAN_COLUMNS = COLUMNS + ['revenue_kopecks']


@dataclass
class Validation:
    clean: pd.DataFrame
    issues: pd.DataFrame
    total_rows: int


def validate_csv(data: bytes) -> Validation:
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Сохраните CSV в кодировке UTF-8.') from exc
    if not text.strip():
        raise ValueError('Файл пуст.')
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('Отсутствуют заголовки или есть повторяющиеся имена столбцов.')
    missing = set(COLUMNS) - set(reader.fieldnames)
    if missing:
        raise ValueError('Не хватает столбцов: ' + ', '.join(sorted(missing)))
    valid, issues, seen = [], [], set()
    total = 0
    for raw in reader:
        total += 1
        row_number = total + 1
        row = {key: (raw.get(key) or '').strip() for key in COLUMNS}
        errors = []
        if None in raw or any(raw.get(key) is None for key in COLUMNS):
            errors.append('Неверное число полей')
        if any(not value for value in row.values()):
            errors.append('Пропущены обязательные значения')
        if row['status'] not in ('paid', 'cancelled'):
            errors.append('Статус должен быть paid или cancelled')
        try:
            parsed = date.fromisoformat(row['order_date'])
            if parsed.isoformat() != row['order_date']:
                raise ValueError
        except ValueError:
            errors.append('Дата должна быть существующей датой YYYY-MM-DD')
        try:
            quantity = int(row['quantity'])
            if quantity <= 0 or quantity > 1_000_000 or str(quantity) != row['quantity']:
                raise ValueError
        except ValueError:
            errors.append('Количество — целое от 1 до 1000000')
        try:
            price = Decimal(row['unit_price_rub'].replace(',', '.'))
            if not price.is_finite() or not 0 <= price <= 1_000_000_000:
                raise InvalidOperation
            kopecks = price * 100
            if kopecks != kopecks.to_integral_value():
                raise InvalidOperation
        except InvalidOperation:
            errors.append('Цена — число от 0 до 1000000000 с точностью до копейки')
        if errors:
            issues.append({'row': row_number, 'order_id': row['order_id'],
                           'reason': '; '.join(errors)})
            continue
        row['quantity'] = quantity
        row['unit_price_rub'] = str(price)
        row['revenue_kopecks'] = quantity * int(kopecks)
        row['_row'] = row_number
        signature = tuple(row[c] for c in CLEAN_COLUMNS)
        if signature in seen:
            issues.append({'row': row_number, 'order_id': row['order_id'], 'reason': 'Точный повтор строки'})
            continue
        seen.add(signature)
        valid.append(row)
    frame = pd.DataFrame(valid, columns=CLEAN_COLUMNS + ['_row'])
    if not frame.empty:
        # Conflicting item keys and order metadata are ambiguous: reject every affected row.
        item_conflict = frame.duplicated(['order_id', 'product_id'], keep=False)
        metadata = frame.groupby('order_id')[['customer_id', 'order_date', 'status']].nunique()
        bad_orders = set(metadata.index[(metadata > 1).any(axis=1)])
        bad_orders.update(frame.loc[item_conflict, 'order_id'])
        conflict = frame['order_id'].isin(bad_orders)
        for _, row in frame.loc[conflict].iterrows():
            issues.append({'row': row['_row'], 'order_id': row['order_id'],
                           'reason': 'Конфликт товарных строк или реквизитов заказа'})
        frame = frame.loc[~conflict].copy()
    frame = frame.drop(columns='_row').reset_index(drop=True)
    # Python integers avoid int64 overflow when many large valid amounts are summed.
    frame['revenue_kopecks'] = frame['revenue_kopecks'].astype(object)
    issue_frame = pd.DataFrame(issues, columns=['row', 'order_id', 'reason']).sort_values('row')
    assert len(frame) + len(issue_frame) == total
    return Validation(frame, issue_frame, total)


def analyze(clean: pd.DataFrame, start=None, end=None):
    filtered = clean.copy()
    if start:
        filtered = filtered.loc[filtered['order_date'] >= str(start)]
    if end:
        filtered = filtered.loc[filtered['order_date'] <= str(end)]
    paid = filtered.loc[filtered['status'] == 'paid'].copy()
    orders = paid.groupby(['order_id', 'customer_id', 'order_date'], as_index=False)['revenue_kopecks'].sum()
    revenue = sum(int(value) for value in paid['revenue_kopecks'])
    count = len(orders)
    customer_counts = orders.groupby('customer_id').size()
    customers = len(customer_counts)
    repeats = int((customer_counts >= 2).sum())
    metrics = {'revenue_rub': revenue / 100, 'paid_orders': count,
               'avg_order_rub': revenue / 100 / count if count else 0,
               'paying_customers': customers, 'repeat_customers': repeats,
               'repeat_customer_pct': 100 * repeats / customers if customers else 0}
    daily = orders.groupby('order_date', as_index=False).agg(
        revenue_kopecks=('revenue_kopecks', 'sum'), paid_orders=('order_id', 'count'))
    daily['revenue_rub'] = daily.pop('revenue_kopecks') / 100
    if count:
        calendar = pd.date_range(start or orders['order_date'].min(), end or orders['order_date'].max())
        daily = daily.set_index('order_date').reindex(calendar.strftime('%Y-%m-%d'), fill_value=0).rename_axis('order_date').reset_index()
    categories = paid.groupby('category', as_index=False).agg(
        units=('quantity', 'sum'), revenue_kopecks=('revenue_kopecks', 'sum'))
    categories['revenue_rub'] = categories.pop('revenue_kopecks') / 100
    categories = categories.sort_values('revenue_rub', ascending=False)
    products = paid.groupby('product_id', as_index=False).agg(
        units=('quantity', 'sum'), revenue_kopecks=('revenue_kopecks', 'sum'))
    products['revenue_rub'] = products.pop('revenue_kopecks') / 100
    products = products.sort_values(['revenue_rub', 'product_id'], ascending=[False, True]).head(10)
    return {'metrics': metrics, 'daily': daily, 'categories': categories,
            'products': products, 'filtered': filtered}


def csv_bytes(frame):
    return frame.to_csv(index=False).encode('utf-8-sig')


def report_zip(validation, result, start=None, end=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, frame in [('cleaned_all', validation.clean), ('issues_all', validation.issues),
                            ('selected_period', result['filtered']), ('daily', result['daily']),
                            ('categories', result['categories']), ('products', result['products'])]:
            archive.writestr(name + '.csv', csv_bytes(frame))
        archive.writestr('summary.json', json.dumps({
            'start': str(start) if start else None, 'end': str(end) if end else None,
            'input_rows': validation.total_rows, 'accepted_rows': len(validation.clean),
            'excluded_rows': len(validation.issues), **result['metrics']}, ensure_ascii=False, indent=2))
    return buffer.getvalue()
