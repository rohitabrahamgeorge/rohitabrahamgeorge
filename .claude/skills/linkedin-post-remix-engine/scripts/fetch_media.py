"""Download a pick's original visuals so Claude can look at them before recreating.

  python fetch_media.py <post_id>     -> runs/<date>/<post_id>/original-*.{jpg,png,gif,pdf}

LinkedIn media URLs are signed and expire after a few days, so fetch them in the same run.
"""
import json
import mimetypes
import os
import sys
import urllib.request
from common import load, run_dir


def main(pid):
    p = load("posts.json", {"posts": {}})["posts"].get(pid)
    if not p:
        sys.exit(f"unknown post {pid}")
    d = os.path.join(run_dir(), pid)
    os.makedirs(d, exist_ok=True)
    saved = []
    for i, u in enumerate(p["media_urls"][:6]):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            r = urllib.request.urlopen(req, timeout=60)
            ctype = r.headers.get("Content-Type", "").split(";")[0]
            ext = mimetypes.guess_extension(ctype) or ".bin"
            ext = {".jpe": ".jpg", ".jpeg": ".jpg"}.get(ext, ext)
            path = os.path.join(d, f"original-{i}{ext}")
            open(path, "wb").write(r.read())
            saved.append(path)
        except Exception as e:  # noqa: BLE001
            print(f"could not fetch media {i}: {e}", file=sys.stderr)
    json.dump(p, open(os.path.join(d, "source.json"), "w"), indent=2, ensure_ascii=False)
    print("\n".join(saved) or "no media saved")
    # GIFs: also export a few frames as PNG so they can be viewed
    for s in saved:
        if s.endswith(".gif"):
            from PIL import Image
            im = Image.open(s)
            n = getattr(im, "n_frames", 1)
            for k in sorted({0, n // 3, 2 * n // 3, n - 1}):
                im.seek(k)
                fp = s.replace(".gif", f"-frame{k}.png")
                im.convert("RGB").save(fp)
                print(fp)
            print(f"gif: {n} frames, {im.info.get('duration', '?')}ms per frame")


if __name__ == "__main__":
    main(sys.argv[1])
