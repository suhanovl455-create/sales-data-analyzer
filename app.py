from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from analyzer import validate_csv, analyze, report_zip

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='Анализ продаж', page_icon='📊', layout='wide')
st.title('Анализ продаж')
st.write('Загрузите заказы, проверьте качество данных и посмотрите показатели за выбранный период.')
with st.sidebar:
    st.header('Данные')
    mode = st.radio('Источник', ['Демонстрационный файл', 'Загрузить CSV'])
    uploaded = st.file_uploader('CSV с заказами', type=['csv']) if mode == 'Загрузить CSV' else None
    st.caption('Одна строка — один товар в заказе. Поддерживаются UTF-8 и разделители: запятая, точка с запятой, табуляция.')
    st.download_button('Скачать пример CSV', (ROOT/'data/demo_sales.csv').read_bytes(), 'demo_sales.csv', 'text/csv')
if mode == 'Загрузить CSV' and uploaded is None:
    st.info('Выберите CSV в боковой панели. Формат столбцов можно посмотреть в примере.')
    st.stop()
try:
    data = uploaded.getvalue() if uploaded is not None else (ROOT/'data/demo_sales.csv').read_bytes()
    validation = validate_csv(data)
except (ValueError, pd.errors.ParserError) as exc:
    st.error(str(exc)); st.stop()
quality, excluded, accepted = st.columns(3)
quality.metric('Строк в файле', validation.total_rows)
accepted.metric('Принято строк', len(validation.clean))
excluded.metric('Исключено строк', len(validation.issues))
if not validation.issues.empty:
    st.warning('Найдены ошибки и повторы. Исключённые строки не участвуют в расчётах — причины доступны во вкладке «Качество данных».')
if validation.clean.empty:
    st.dataframe(validation.issues, hide_index=True)
    st.info('Нет корректных строк для анализа. Исправьте файл и загрузите повторно.')
    st.stop()
minimum = pd.to_datetime(validation.clean['order_date'].min()).date()
maximum = pd.to_datetime(validation.clean['order_date'].max()).date()
with st.sidebar:
    start = st.date_input('С даты', minimum, min_value=minimum, max_value=maximum)
    end = st.date_input('По дату', maximum, min_value=minimum, max_value=maximum)
if start > end:
    st.error('Начало периода должно быть не позже окончания.'); st.stop()
result = analyze(validation.clean, start, end)
metrics = result['metrics']
st.subheader(f'{start:%d.%m.%Y} — {end:%d.%m.%Y}')
st.metric('Выручка', f"{metrics['revenue_rub']:,.2f} ₽".replace(',', ' '))
b,c = st.columns(2)
b.metric('Оплаченные заказы', metrics['paid_orders'])
c.metric('Средний чек', f"{metrics['avg_order_rub']:,.2f} ₽".replace(',', ' '))
d,e = st.columns(2)
e.metric('Покупатели с оплатой', metrics['paying_customers'])
d.metric('Повторные покупатели', f"{metrics['repeat_customer_pct']:.1f}%")
st.caption('Метрики считают только paid. Повторный покупатель — минимум два оплаченных заказа в выбранном периоде. Процент считается среди покупателей с оплатой.')
charts, tables, issues = st.tabs(['Динамика и категории', 'Таблицы', 'Качество данных'])
with charts:
    if metrics['paid_orders'] == 0:
        st.info('В этом периоде нет оплаченных заказов.')
    else:
        st.subheader('Выручка по дням')
        fig,ax = plt.subplots(figsize=(10,4))
        ax.plot(pd.to_datetime(result['daily']['order_date']), result['daily']['revenue_rub'], color='#197a70', linewidth=2)
        ax.set_ylabel('Выручка, ₽'); ax.grid(axis='y',alpha=.2)
        fig.autofmt_xdate(); fig.tight_layout(); st.pyplot(fig); plt.close(fig)
        st.subheader('Категории')
        frame=result['categories'].sort_values('revenue_rub')
        fig,ax=plt.subplots(figsize=(10,3))
        ax.barh(frame['category'],frame['revenue_rub'],color='#197a70')
        ax.set_xlabel('Выручка, ₽'); fig.tight_layout(); st.pyplot(fig); plt.close(fig)
        st.subheader('Топ-10 товаров по выручке')
        st.dataframe(result['products'], hide_index=True)
with tables:
    st.subheader('Продажи по дням'); st.dataframe(result['daily'],hide_index=True)
    st.subheader('Продажи по категориям'); st.dataframe(result['categories'],hide_index=True)
    st.subheader('Принятые строки за период'); st.dataframe(result['filtered'],hide_index=True)
with issues:
    st.write('Проверка относится ко всему исходному файлу, независимо от фильтра дат.')
    st.dataframe(validation.issues,hide_index=True)
    st.caption('Точные повторы удаляются после первой строки. При конфликте товара или реквизитов исключаются все корректно разобранные строки затронутого заказа. Строки с неверными полями исключаются по отдельности; заказ может остаться частичным до исправления источника.')
st.download_button('Скачать результаты ZIP', report_zip(validation,result,start,end), 'sales_analysis.zip','application/zip',type='primary')
with st.expander('Формат данных и ограничения'):
    st.write('Столбцы: order_id, customer_id, order_date, status, product_id, category, quantity, unit_price_rub. Дата YYYY-MM-DD, статус paid или cancelled. Ключ товарной строки — пара order_id + product_id. Цена в рублях, не более двух знаков после запятой. Возвраты, доставка, скидки и себестоимость не моделируются. Выручка не равна прибыли.')
