"""Run from repository root: python -m harness --help."""
import argparse
import json
import sys

from .contract import load_inputs, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generic source-visible UI experiment Harness')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'run', 'preflight', 'accept', 'request'):
        command = sub.add_parser(name)
        command.add_argument('--site', required=True)
        if name != 'request':
            command.add_argument('--bundle', required=True)
        if name in ('run', 'preflight', 'accept', 'request'):
            command.add_argument('--out', required=True)
        if name in ('run', 'accept', 'request'):
            command.add_argument('--baseline-summary')
        if name in ('run', 'accept'):
            command.add_argument('--diagnosis')
        if name in ('run', 'preflight'):
            browser = command.add_mutually_exclusive_group()
            browser.add_argument('--cdp', default='http://127.0.0.1:9337')
            browser.add_argument('--launch-browser', action='store_true', help='Select browser launch (preflight only discovers unless --smoke is requested)')
        if name == 'preflight':
            command.add_argument('--smoke', action='store_true', help='Explicitly run the generic real browser transport smoke; no business tasks')
    args = parser.parse_args(argv)
    try:
        exit_code = 0
        if args.command == 'validate':
            site, bundle, cases = load_inputs(args.site, args.bundle)
            result = {'valid': True, **validate(site, bundle, cases)}
        elif args.command == 'run':
            from .runner import execute
            summary = execute(args.site, args.bundle, args.out, cdp_url=None if args.launch_browser else args.cdp,
                              baseline_summary=args.baseline_summary, diagnosis_path=args.diagnosis)
            result = {'summary': str(args.out) + '/summary.json', 'metrics': summary['metrics'], 'activation': summary['activation']}
            exit_code = 0 if (summary.get('measurement_status') == 'completed' and
                              summary['activation'].get('activation_allowed') and
                              summary['metrics'].get('passed_cases') == summary['metrics'].get('case_denominator')) else 1
        elif args.command == 'preflight':
            from .preflight import execute
            result = execute(args.site, args.bundle, args.out, cdp_url=args.cdp,
                             launch_browser=args.launch_browser, smoke=args.smoke)
            exit_code = 0 if result['ready_for_measurement'] else 1
        elif args.command == 'request':
            from .handoff import request
            result = request(args.site, args.out, args.baseline_summary)
        else:
            from .handoff import accept
            result = accept(args.site, args.bundle, args.out, args.baseline_summary, args.diagnosis)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code
    except Exception as exc:
        print(json.dumps({'error': str(exc), 'type': type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
