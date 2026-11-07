import unittest
from datetime import date
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP=Path(__file__).resolve().parents[1]/'app.py'


class InterfaceTests(unittest.TestCase):
    def test_date_filter_and_invalid_range(self):
        app=AppTest.from_file(str(APP),default_timeout=30).run()
        app.sidebar.date_input[0].set_value(date(2026,8,1)).run()
        self.assertEqual(len(app.exception),0)
        values={m.label:m.value for m in app.metric}
        self.assertLess(int(values['Оплаченные заказы']),161)
        app.sidebar.date_input[1].set_value(date(2026,7,1)).run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('Начало периода' in message.value for message in app.error))

    def test_demo_and_upload_empty_state(self):
        app=AppTest.from_file(str(APP),default_timeout=30).run()
        self.assertEqual(len(app.exception),0)
        values={m.label:m.value for m in app.metric}
        self.assertEqual(values['Оплаченные заказы'],'161')
        self.assertEqual(values['Исключено строк'],'10')
        app.sidebar.radio[0].set_value('Загрузить CSV').run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('Выберите CSV' in message.value for message in app.info))


if __name__=='__main__':unittest.main()
