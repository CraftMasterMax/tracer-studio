"""Render the demo doc to PNGs (iso/front/top + wire states) for visual
review and pixel debugging. Usage: python tools/snapshot.py [outdir]"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from forma.ui.camera import Camera
from forma.ui.mainwindow import demo_document
from forma.ui.renderer import SceneRenderer


def main():
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/forma-shots")
    outdir.mkdir(parents=True, exist_ok=True)
    r = SceneRenderer()
    doc = demo_document()
    solid = doc.recompute()
    v, n, f = solid.to_render_arrays()
    r.resize(900, 600)
    r.set_mesh(v, n, f)
    r._grid_auto(solid.bounding_box)
    for kind in ("iso", "front", "top", "right"):
        cam = Camera()
        if kind != "iso":
            cam.set_view(kind)
        cam.fit(solid.bounding_box)
        img = r.render(cam, solid.bounding_box)
        Image.fromarray(img).save(outdir / f"{kind}.png")
        nonbg = np.mean(np.any(np.abs(img[:, :, :3].astype(int) - 30) > 24, axis=2))
        print(kind, "coverage", f"{nonbg:.3f}")
    print("saved to", outdir)


if __name__ == "__main__":
    main()
