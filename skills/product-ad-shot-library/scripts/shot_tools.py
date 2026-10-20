"""Local technical helpers; semantic decisions must be supplied by a reviewer."""
import argparse, io, json, math, re, subprocess, tempfile
from pathlib import Path

def run(args):
    p = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors='replace')[-2500:])
    return p

def save(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def probe(a, source):
    try:
        return json.loads(run([a.ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', source]).stdout)
    except FileNotFoundError:
        p = subprocess.run([a.ffmpeg, '-hide_banner', '-i', str(source)], capture_output=True)
        text = p.stderr.decode(errors='replace')
        d = re.search(r'Duration: (\d+):(\d+):([\d.]+)', text)
        v = next((line for line in text.splitlines() if 'Video:' in line), '')
        fps = re.search(r'([\d.]+) fps', v)
        if not d or not v: raise RuntimeError('Cannot probe media without ffprobe: ' + text[-1000:])
        h, m, s = map(float, d.groups())
        return {'format': {'duration': h * 3600 + m * 60 + s},
                'streams': [{'codec_type': 'video', 'avg_frame_rate': (fps.group(1) if fps else '0') + '/1'}],
                'probe_method': 'ffmpeg_text_fallback_centisecond_precision'}

def duration(doc):
    return float(doc['format']['duration'])

def inspect(a):
    source = Path(a.source).resolve(strict=True); doc = probe(a, source)
    result = run([a.ffmpeg, '-hide_banner', '-i', source, '-vf',
                  f"scale=160:-2,select='gt(scene,{a.threshold})',showinfo", '-an', '-f', 'null', '-'])
    cuts = sorted(set(float(t) for t in re.findall(r'pts_time:([\d.]+)', result.stderr.decode(errors='replace'))))
    save(a.output, {'source': str(source), 'bytes': source.stat().st_size,
                    'mtime_ns': source.stat().st_mtime_ns, 'probe': doc,
                    'candidate_cuts': [0.0] + [x for x in cuts if 0 < x < duration(doc)] + [duration(doc)],
                    'note': 'Detection candidates only; visual review required.'})

def contact(a):
    from PIL import Image, ImageDraw
    source = Path(a.source).resolve(strict=True); end = a.end if a.end is not None else duration(probe(a, source))
    if not 0 <= a.start < end <= duration(probe(a, source)) + .001 or not 2 <= a.count <= 100:
        raise ValueError('Invalid interval or count (2..100)')
    output = Path(a.output)
    if output.exists(): raise FileExistsError(output)
    cols = min(6, a.count); sheet = Image.new('RGB', (cols * 200, math.ceil(a.count / cols) * 300), 'white')
    draw = ImageDraw.Draw(sheet)
    for i in range(a.count):
        t = a.start + (end - a.start) * (i + .5) / a.count
        data = run([a.ffmpeg, '-v', 'error', '-ss', t, '-i', source, '-frames:v', '1', '-vf', 'scale=320:-2', '-f', 'image2pipe', '-vcodec', 'png', '-']).stdout
        im = Image.open(io.BytesIO(data)); im.thumbnail((196, 270))
        x, y = i % cols * 200, i // cols * 300
        sheet.paste(im, (x, y + 23)); draw.text((x + 3, y + 3), f'{t:.3f}s', fill='black')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as f: sheet.save(f, format='JPEG', quality=90)

def export(a):
    rows = json.loads(Path(a.plan).read_text(encoding='utf-8')); root = Path(a.output).resolve()
    if not isinstance(rows, list) or not rows: raise ValueError('Plan must be a nonempty array')
    jobs, targets, docs = [], set(), {}
    for r in rows:
        source = Path(r['source']).resolve(strict=True)
        if root == source.parent or source.parent in root.parents:
            raise ValueError('Output cannot be inside a source directory')
        if source not in docs: docs[source] = probe(a, source)
        start, end = float(r['start']), float(r['end'])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration(docs[source]) + .001):
            raise ValueError('Invalid interval: ' + str(r))
        if r['review_method'] not in {'full_playback', 'manual_keyframes', 'grouped_unreviewed', 'unresolved'}:
            raise ValueError('Unknown review evidence')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', r['clip_id']): raise ValueError('Invalid clip ID')
        category = Path(r['category'])
        if category.is_absolute() or '..' in category.parts or not category.parts or '\\' in r['category']:
            raise ValueError('Unsafe category')
        target = (root / category / (r['clip_id'] + '.mp4')).resolve()
        if root not in target.parents: raise ValueError('Escaping output root')
        receipt = target.with_suffix('.receipt.json')
        if target in targets or target.exists() or receipt.exists(): raise FileExistsError(target)
        targets.add(target); jobs.append((r, source, target, receipt))
    for r, source, target, receipt in jobs:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='shot-export-', dir=target.parent) as work:
            tmp = Path(work) / 'clip.mp4'; length = float(r['end']) - float(r['start'])
            run([a.ffmpeg, '-v', 'error', '-nostdin', '-ss', r['start'], '-i', source,
                 '-t', length, '-map', '0:v:0', '-map', '0:a?', '-c:v', 'libx264', '-crf', '18',
                 '-preset', 'medium', '-c:a', 'aac', '-movflags', '+faststart', tmp])
            run([a.ffmpeg, '-v', 'error', '-xerror', '-i', tmp, '-f', 'null', '-'])
            doc = probe(a, tmp); video = next(s for s in docs[source]['streams'] if s['codec_type'] == 'video')
            num, den = map(float, video.get('avg_frame_rate', '0/1').split('/')); fps = num / den if den else 0
            tolerance = max(.15, 2 / fps if fps else .15)
            if abs(duration(doc) - length) > tolerance: raise RuntimeError('Duration verification failed')
            # Exclusive creation avoids overwriting an unexpected file during a long batch.
            with tmp.open('rb') as src, target.open('xb') as dst:
                import shutil
                shutil.copyfileobj(src, dst)
            save(receipt, {**r, 'source': str(source), 'output': str(target), 'bytes': target.stat().st_size,
                           'actual_duration': duration(doc), 'decode_ok': True, 'duration_tolerance': tolerance})
            print(json.dumps({'clip_id': r['clip_id'], 'output': str(target), 'decode_ok': True}, ensure_ascii=False), flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg', default='ffmpeg'); p.add_argument('--ffprobe', default='ffprobe')
    sub = p.add_subparsers(dest='command', required=True)
    x = sub.add_parser('inspect'); x.add_argument('--source', required=True); x.add_argument('--output', required=True); x.add_argument('--threshold', type=float, default=.25)
    x = sub.add_parser('contact'); x.add_argument('--source', required=True); x.add_argument('--output', required=True); x.add_argument('--start', type=float, default=0); x.add_argument('--end', type=float); x.add_argument('--count', type=int, default=9)
    x = sub.add_parser('export'); x.add_argument('--plan', required=True); x.add_argument('--output', required=True)
    a = p.parse_args()
    if a.command == 'inspect' and not 0 < a.threshold < 1: p.error('threshold must be between 0 and 1')
    {'inspect': inspect, 'contact': contact, 'export': export}[a.command](a)

if __name__ == '__main__': main()
