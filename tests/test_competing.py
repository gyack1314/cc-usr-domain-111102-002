import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from workbench.io import read_json
from workbench.competing import analyze,load_rows
from workbench.checks import check_result
from tests.competing_checks import check,row

ROOT=Path(__file__).resolve().parents[1]

class CompetingTests(unittest.TestCase):
    def test_handworked_examples_and_independent_checks(self):
        check(self)

    def test_shipped_sample_matches_hand_calculation(self):
        result=analyze(load_rows(ROOT/'samples'))
        check_result(result)
        north=result['groups']['north'];south=result['groups']['south']
        overall=result['groups']['overall']
        # north：t=4d 共同 Y=3，两类终点各 1、删失 1
        point=next(p for p in north['timeline'] if p['time']==4*86400)
        self.assertEqual(point['at_risk'],['v1','v2','v3'])
        self.assertEqual(point['F_arrival'],Fraction(1,3))
        self.assertEqual(north['event_counts'],{'arrival':1,'cancel':1,'censor':1})
        self.assertEqual(north['median_arrival_time']['status'],'not_estimable')
        # south：v5 入组前已到港被旁路；v4 截止后到港按删失，无事件队列
        self.assertEqual([x['id'] for x in result['diagnostics']['excluded']],['v5'])
        self.assertEqual(south['event_counts'],{'arrival':0,'cancel':0,'censor':1})
        self.assertEqual(south['steps'],[])
        # 总体独立计算
        self.assertEqual(overall['subject_count'],4)
        self.assertEqual(overall['final']['F_arrival'],Fraction(1,4))
        self.assertEqual([x['id'] for x in result['diagnostics']['invalid']],['bad'])

    def test_cli_export_roundtrip_and_db_path(self):
        from workbench.catalog import Catalog
        from workbench.competing import load_rows_catalog
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'stats.json'
            proc=subprocess.run([sys.executable,'-m','workbench.cli','competing',
                                 str(ROOT/'samples'),'--out',str(out)],
                                cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            exported=read_json(out)
            self.assertEqual(exported['subject_count'],4)
            self.assertIn('numerator',exported['groups']['north']['final']['S'])
            db=Path(d)/'raw.sqlite3'
            import_id=Catalog(db).ingest(ROOT/'samples')
            result=analyze(load_rows_catalog(Catalog(db),import_id))
            check_result(result)
            self.assertEqual(result['subject_count'],4)

if __name__=='__main__':
    unittest.main()
