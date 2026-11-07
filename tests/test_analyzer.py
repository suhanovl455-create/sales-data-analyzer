import csv
import io
import json
from pathlib import Path
import unittest
import zipfile
from analyzer import COLUMNS, validate_csv, analyze, report_zip


def sample(rows):
    f=io.StringIO(); writer=csv.writer(f);writer.writerow(COLUMNS);writer.writerows(rows)
    return f.getvalue().encode()


BASE = ['1','C1','2026-07-01','paid','P1','Аудио','2','100.10']


class AnalysisTests(unittest.TestCase):
    def test_order_count_money_repeats_and_cancellations(self):
        rows=[BASE, ['1','C1','2026-07-01','paid','P2','Кабели','1','99.80'],
              ['2','C1','2026-07-03','paid','P1','Аудио','1','100'],
              ['3','C2','2026-07-03','cancelled','P1','Аудио','1','9000']]
        v=validate_csv(sample(rows)); r=analyze(v.clean)
        self.assertEqual(r['metrics']['revenue_rub'],400)
        self.assertEqual(r['metrics']['paid_orders'],2)
        self.assertEqual(r['metrics']['avg_order_rub'],200)
        self.assertEqual(r['metrics']['repeat_customer_pct'],100)
        self.assertEqual(r['daily']['revenue_rub'].tolist(),[300,0,100])
        self.assertEqual(r['categories']['revenue_rub'].sum(),400)

    def test_exact_duplicates(self):
        v=validate_csv(sample([BASE,BASE]));self.assertEqual(len(v.clean),1)
        self.assertEqual(len(v.issues),1)

    def test_conflicting_order_excluded_completely(self):
        other=BASE.copy();other[-1]='101'
        third=BASE.copy();third[4]='P2'
        v=validate_csv(sample([BASE,other,third]));self.assertTrue(v.clean.empty)
        self.assertEqual(len(v.issues),3)

    def test_metadata_conflict(self):
        other=BASE.copy();other[1]='C2';other[4]='P2'
        self.assertTrue(validate_csv(sample([BASE,other])).clean.empty)

    def test_bad_values(self):
        for field,value in [(2,'2026-02-30'),(6,'1.5'),(6,'-1'),(7,'NaN'),(7,'-1'),(7,'1.001'),(1,''),(3,'pending')]:
            with self.subTest(field=field,value=value):
                row=BASE.copy();row[field]=value
                v=validate_csv(sample([row]));self.assertTrue(v.clean.empty)
                self.assertEqual(len(v.issues),1)

    def test_zero_price_and_decimal_comma(self):
        row=BASE.copy();row[7]='0'
        self.assertEqual(analyze(validate_csv(sample([row])).clean)['metrics']['revenue_rub'],0)
        row[7]='100,10'
        self.assertEqual(analyze(validate_csv(sample([row])).clean)['metrics']['revenue_rub'],200.2)

    def test_missing_headers_and_empty_file(self):
        for data in [b'',b'hello,world\n1,2\n']:
            with self.assertRaises(ValueError):validate_csv(data)

    def test_alternative_delimiters_and_bom(self):
        for separator in [';', '\t']:
            f=io.StringIO();writer=csv.writer(f,delimiter=separator)
            writer.writerow(COLUMNS);writer.writerow(BASE)
            result=validate_csv(f.getvalue().encode('utf-8-sig'))
            self.assertEqual(len(result.clean),1)
            self.assertTrue(result.issues.empty)

    def test_invalid_encoding_duplicate_headers_and_wrong_field_count(self):
        with self.assertRaises(ValueError):validate_csv(b'\xff\xfe')
        with self.assertRaises(ValueError):validate_csv(b'order_id,order_id\n1,2\n')
        for row in [BASE[:-1],BASE+['unexpected']]:
            result=validate_csv(sample([row]))
            self.assertTrue(result.clean.empty)
            self.assertEqual(len(result.issues),1)

    def test_empty_or_cancelled_or_filtered(self):
        for rows in [[],[BASE[:3]+['cancelled']+BASE[4:]]]:
            r=analyze(validate_csv(sample(rows)).clean)
            self.assertEqual(r['metrics']['paid_orders'],0)
        r=analyze(validate_csv(sample([BASE])).clean,'2026-08-01','2026-08-02')
        self.assertEqual(r['metrics']['revenue_rub'],0)

    def test_period_inclusive(self):
        v=validate_csv(sample([BASE]));r=analyze(v.clean,'2026-07-01','2026-07-01')
        self.assertEqual(r['metrics']['paid_orders'],1)

    def test_export(self):
        v=validate_csv(sample([BASE]));r=analyze(v.clean)
        with zipfile.ZipFile(io.BytesIO(report_zip(v,r))) as archive:
            self.assertIsNone(archive.testzip())
            summary=json.loads(archive.read('summary.json'))
            self.assertEqual(summary['revenue_rub'],200.2)
            self.assertEqual(len(archive.namelist()),7)

    def test_large_valid_amounts_do_not_overflow(self):
        rows=[]
        for i in range(100):
            row=BASE.copy();row[0]=str(i);row[6]='1000000';row[7]='1000000000'
            rows.append(row)
        result=analyze(validate_csv(sample(rows)).clean)
        self.assertEqual(result['metrics']['revenue_rub'],10**17)
        self.assertEqual(int(result['categories'].iloc[0]['revenue_rub']),10**17)


if __name__=='__main__': unittest.main()
