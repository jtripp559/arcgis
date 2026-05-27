# LogViewer/app.py
#
# Developer:    Julie Tripp
#
# Date: 2026-05-18
#
# Description:  Simple Flask web viewer for the CSV log files written by
#               MonitorArcGISEnterpriseLogs.py. Renders the most recent log CSV as
#               an interactive table (sort, filter, severity colors, source
#               filter, expandable messages). A Refresh button re-runs
#               MonitorArcGISEnterpriseLogs.py via subprocess to fetch fresh logs.
#
#               NOTE: Clicking Refresh also triggers the PowerAutomate email send
#               in the existing script if new log messages are found. That is the
#               existing script's behavior; this viewer does not change it.
#
# Run:
#   From an ArcGIS Pro conda prompt:
#       cd "D:\GenericScriptsDir\LogViewer"
#       python app.py
#   Then open http://localhost:5000 in your browser.
#
# Requirements: flask, pandas (pandas is in the ArcGIS Pro env; Flask may need
#   `pip install flask` into a cloned env).

import os
import re
import sys
import glob
import subprocess
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, render_template, request, jsonify, send_file, abort
import pandas as pd

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(APP_DIR)
REFRESH_SCRIPTS = [
    'MonitorArcGISEnterpriseLogs.py',
    'WindowsServicesMonitor.py',
]

TEAM_OUTPUT_PRIMARY = r'D:\GenericScriptsDir\Output'
TEAM_OUTPUT_FALLBACK = r'\\org-app2\D$\GenericScriptsDir\Output'
LOCAL_OUTPUT = os.path.join(SCRIPT_DIR, 'Output')


def get_log_dirs():
    dirs = []
    if os.path.isdir(TEAM_OUTPUT_PRIMARY):
        dirs.append(TEAM_OUTPUT_PRIMARY)
    elif os.path.isdir(TEAM_OUTPUT_FALLBACK):
        dirs.append(TEAM_OUTPUT_FALLBACK)
    if os.path.isdir(LOCAL_OUTPUT):
        dirs.append(LOCAL_OUTPUT)
    return dirs

EXPECTED_COLUMNS = [
    'logSource', 'type', 'time', 'code', 'source', 'process', 'thread',
    'methodName', 'machine', 'user', 'elapsed', 'requestID', 'message',
]

RANGE_OPTIONS = [
    ('this_month',     'This month'),
    ('this_quarter',   'This quarter'),
    ('this_year',      'This year'),
    ('last_6_months',  'Last 6 months'),
    ('last_12_months', 'Last 12 months'),
    ('all',            'All'),
]
DEFAULT_RANGE = 'this_month'

# Safety cap: even when a range matches more files than this, only the newest
# MAX_FILES_PER_REQUEST are read. Prevents a single click from kicking off
# thousands of reads over a network share.
MAX_FILES_PER_REQUEST = 1000

# Parallel read pool size. Network-bound CSV reads parallelize well.
READ_WORKERS = 16

# In-memory cache: path -> (mtime, df-with-logFile-column).
# Re-reads only when a file's mtime changes.
_csv_cache = {}

app = Flask(__name__)


def range_start_date(range_key, now=None):
    if now is None:
        now = dt.datetime.now()
    if range_key == 'this_month':
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if range_key == 'this_quarter':
        q_start_month = ((now.month - 1) // 3) * 3 + 1
        return now.replace(month=q_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    if range_key == 'this_year':
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if range_key == 'last_6_months':
        return now - dt.timedelta(days=183)
    if range_key == 'last_12_months':
        return now - dt.timedelta(days=365)
    return None


_FILENAME_TS_RE = re.compile(r'_logs_(\d{8})_(\d{6})\.csv$', re.IGNORECASE)
_WSM_FILENAME_TS_RE = re.compile(r'WindowsServicesMonitor_(\d{4})(\d{2})\.log$', re.IGNORECASE)

LOG_FILE_PATTERNS = ('*_logs_*.csv', 'WindowsServicesMonitor_*.log')


def file_timestamp(path):
    name = os.path.basename(path)
    m = _FILENAME_TS_RE.search(name)
    if m:
        try:
            return dt.datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
        except ValueError:
            pass
    m = _WSM_FILENAME_TS_RE.search(name)
    if m:
        try:
            return dt.datetime(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            pass
    return dt.datetime.fromtimestamp(os.path.getmtime(path))


def file_end_timestamp(path):
    """Last moment of time covered by the file.

    For point-in-time CSVs this equals file_timestamp(). For WSM monthly
    rolling logs it's the end of the month so the file isn't accidentally
    excluded by a range whose cutoff falls inside the month.
    """
    m = _WSM_FILENAME_TS_RE.search(os.path.basename(path))
    if m:
        try:
            year, month = int(m.group(1)), int(m.group(2))
            if month == 12:
                next_month = dt.datetime(year + 1, 1, 1)
            else:
                next_month = dt.datetime(year, month + 1, 1)
            return next_month - dt.timedelta(seconds=1)
        except ValueError:
            pass
    return file_timestamp(path)


def list_log_files(range_key=None):
    cutoff = range_start_date(range_key) if range_key else None
    seen_names = set()
    files = []
    for d in get_log_dirs():
        for pattern in LOG_FILE_PATTERNS:
            for path in glob.glob(os.path.join(d, pattern)):
                name = os.path.basename(path)
                if name in seen_names:
                    continue
                seen_names.add(name)
                if cutoff is not None and file_end_timestamp(path) < cutoff:
                    continue
                files.append(path)
    files.sort(key=os.path.getmtime, reverse=True)
    return files


def _format_time_value(v):
    # Time column may contain ms-since-epoch integers (from portal/server log
    # APIs) or already-formatted date strings (from log-file parsing). The
    # source script's bulk pd.to_datetime(..., unit='ms') call fails silently
    # on a mixed-type Series, so the CSV is written with raw mixed values.
    # Normalize per-value here.
    s = '' if v is None else str(v).strip()
    if s and s.isdigit() and 12 <= len(s) <= 14:
        try:
            return pd.to_datetime(int(s), unit='ms').strftime('%Y-%m-%d %H:%M:%S.%f')
        except Exception:
            return s
    return s


def load_csv(path):
    df = pd.read_csv(path, encoding='utf-8-sig', dtype=str, keep_default_na=False)
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = ''
    if 'time' in df.columns:
        df['time'] = df['time'].apply(_format_time_value)
        file_mtime = dt.datetime.fromtimestamp(os.path.getmtime(path))
        fallback_iso = file_mtime.strftime('%Y-%m-%d %H:%M:%S')
        fallback_display = file_mtime.strftime('%m/%d/%y %H:%M')

        def _to_iso_display(v):
            parsed = pd.to_datetime(v, errors='coerce')
            if pd.isna(parsed) or parsed.year < 2000:
                return (fallback_iso, fallback_display)
            return (parsed.strftime('%Y-%m-%d %H:%M:%S'),
                    parsed.strftime('%m/%d/%y %H:%M'))

        pairs = df['time'].apply(_to_iso_display)
        df['time_iso'] = pairs.apply(lambda p: p[0])
        df['time'] = pairs.apply(lambda p: p[1])
    return df


_WSM_LINE_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})\s+(\w+)\s+(.*)$'
)
_WSM_KEEP_LEVELS = {'WARNING', 'ERROR', 'SEVERE', 'CRITICAL'}


def parse_wsm_log(path):
    """Parse a WindowsServicesMonitor monthly .log file into the same row schema
    used by load_csv. Keeps only WARNING/ERROR/SEVERE/CRITICAL lines (matches
    the actionable-severity policy already used for ArcGIS CSVs). Continuation
    lines (e.g. traceback bodies) are appended to the prior kept row's message.
    """
    cols = EXPECTED_COLUMNS + ['time_iso']
    rows = []
    cur = None
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for raw_line in f:
                line = raw_line.rstrip('\n')
                m = _WSM_LINE_RE.match(line)
                if m:
                    if cur is not None:
                        rows.append(cur)
                        cur = None
                    ts, ms, level, msg = m.group(1), m.group(2), m.group(3).upper(), m.group(4)
                    if level not in _WSM_KEEP_LEVELS:
                        continue
                    try:
                        ts_dt = dt.datetime.strptime(
                            ts + '.' + ms + '000', '%Y-%m-%d %H:%M:%S.%f'
                        )
                    except ValueError:
                        continue
                    cur = {
                        'logSource': 'ms_service',
                        'type': level,
                        'time': ts_dt.strftime('%m/%d/%y %H:%M'),
                        'time_iso': ts_dt.strftime('%Y-%m-%d %H:%M:%S'),
                        'message': msg,
                        'code': '', 'source': '', 'process': '', 'thread': '',
                        'methodName': '', 'machine': '', 'user': '',
                        'elapsed': '', 'requestID': '',
                    }
                else:
                    if cur is not None:
                        cur['message'] += '\n' + line
        if cur is not None:
            rows.append(cur)
    except Exception as e:
        app.logger.warning(f"Failed to parse WSM log {path}: {e}")

    if rows:
        df = pd.DataFrame(rows)
        for c in cols:
            if c not in df.columns:
                df[c] = ''
        return df[cols]
    return pd.DataFrame(columns=cols)


def _load_file_cached(path):
    """Dispatch by extension: .csv -> load_csv, .log -> parse_wsm_log.
    Caches by (path, mtime); only re-reads files whose mtime changed.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _csv_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == '.csv':
            df = load_csv(path)
        elif ext == '.log':
            df = parse_wsm_log(path)
        else:
            return None
        df['logFile'] = os.path.basename(path)
        _csv_cache[path] = (mtime, df)
        return df
    except Exception as e:
        app.logger.warning(f"Failed to load {path}: {e}")
        return None


@app.route('/')
def index():
    range_key = request.args.get('range', DEFAULT_RANGE)
    if range_key not in {k for k, _ in RANGE_OPTIONS}:
        range_key = DEFAULT_RANGE
    selected_range_label = dict(RANGE_OPTIONS)[range_key]

    matched = list_log_files(range_key)
    truncated = False
    if len(matched) > MAX_FILES_PER_REQUEST:
        files = matched[:MAX_FILES_PER_REQUEST]
        truncated = True
    else:
        files = matched

    if files:
        with ThreadPoolExecutor(max_workers=READ_WORKERS) as ex:
            dfs = [df for df in ex.map(_load_file_cached, files) if df is not None]
    else:
        dfs = []

    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=EXPECTED_COLUMNS + ['logFile'])

    # Precise line-level cutoff: a WSM monthly file may straddle the cutoff,
    # so filter rows whose time_iso is older than it. Uses lexical compare on
    # the YYYY-MM-DD HH:MM:SS strings (correct because ISO format is ordered).
    cutoff = range_start_date(range_key)
    if cutoff is not None and not combined.empty and 'time_iso' in combined.columns:
        cutoff_iso = cutoff.strftime('%Y-%m-%d %H:%M:%S')
        combined = combined[combined['time_iso'] >= cutoff_iso]

    rows = combined.to_dict('records')
    sources = sorted(
        [s for s in combined.get('logSource', pd.Series(dtype=str)).unique().tolist() if s]
    )

    return render_template(
        'index.html',
        ranges=RANGE_OPTIONS,
        selected_range=range_key,
        selected_range_label=selected_range_label,
        file_count=len(files),
        matched_count=len(matched),
        truncated=truncated,
        max_files=MAX_FILES_PER_REQUEST,
        rows=rows,
        sources=sources,
    )


@app.route('/file/<filename>')
def serve_file(filename):
    # Resolve a CSV by basename against the configured log directories.
    # Strip any path-traversal attempts before looking it up.
    safe = os.path.basename(filename)
    if safe in ('', '.', '..') or '/' in filename or '\\' in filename:
        abort(400)
    for d in get_log_dirs():
        candidate = os.path.join(d, safe)
        if os.path.isfile(candidate):
            # Serve as text/plain so the browser displays it inline in a new tab.
            return send_file(candidate, mimetype='text/plain')
    abort(404)


@app.route('/refresh', methods=['POST'])
def refresh():
    results = []
    overall_ok = True
    for name in REFRESH_SCRIPTS:
        path = os.path.join(SCRIPT_DIR, name)
        if not os.path.exists(path):
            results.append({'script': name, 'ok': False, 'error': f'Script not found: {path}'})
            overall_ok = False
            continue
        try:
            result = subprocess.run(
                [sys.executable, path],
                cwd=SCRIPT_DIR,
                capture_output=True,
                text=True,
                timeout=600,
            )
            ok = (result.returncode == 0)
            if not ok:
                overall_ok = False
            results.append({
                'script': name,
                'ok': ok,
                'returncode': result.returncode,
                'stdout_tail': (result.stdout or '')[-1000:],
                'stderr_tail': (result.stderr or '')[-1000:],
            })
        except subprocess.TimeoutExpired:
            results.append({'script': name, 'ok': False, 'error': 'Script timed out after 10 minutes'})
            overall_ok = False
        except Exception as e:
            results.append({'script': name, 'ok': False, 'error': str(e)})
            overall_ok = False
    return jsonify({'ok': overall_ok, 'results': results})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
