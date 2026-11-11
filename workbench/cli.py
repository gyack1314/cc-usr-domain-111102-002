import argparse
import json
import sys
from .io import inspect_bundle,write_json
from .catalog import Catalog
from .competing import analyze,load_rows,load_rows_catalog
from .checks import check_result
from .export import export_result

def _run(rows,out_path):
    result=analyze(rows)
    check_result(result)
    exported=export_result(result)
    if out_path:
        write_json(out_path,exported)
        return {'exported_to':str(out_path),'subject_count':result['subject_count'],
                'groups':sorted(result['groups']),'check':'ok'}
    return exported

def main():
    parser=argparse.ArgumentParser(description='业务资料读取、本地存档与竞争风险统计')
    subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('inspect');p.add_argument('directory')
    p=subs.add_parser('ingest');p.add_argument('directory');p.add_argument('database')
    p=subs.add_parser('catalog');p.add_argument('database')
    p=subs.add_parser('competing',help='延迟入组竞争风险统计')
    p.add_argument('directory');p.add_argument('--out',dest='out_path')
    p=subs.add_parser('competing-db',help='从本地存档计算竞争风险统计')
    p.add_argument('database');p.add_argument('import_id',type=int);p.add_argument('--out',dest='out_path')
    args=parser.parse_args()
    try:
        if args.command=='inspect':result=inspect_bundle(args.directory)
        elif args.command=='ingest':result={'import_id':Catalog(args.database).ingest(args.directory)}
        elif args.command=='catalog':result=Catalog(args.database).summary()
        elif args.command=='competing':result=_run(load_rows(args.directory),args.out_path)
        else:
            result=_run(load_rows_catalog(Catalog(args.database),args.import_id),args.out_path)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,KeyError,AssertionError,TypeError) as exc:
        print(f'资料读取或统计失败，请核对文件与字段约定：{exc}',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
