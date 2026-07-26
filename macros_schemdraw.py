"""schemdraw circuit macros — kept separate from SPICE macros."""
import sys, importlib, base64
from pathlib import Path

def schemdraw_svg(project_dir: str, name: str) -> str:
    """Import circuits/<module>.py, call <func>(), return SVG base64 data URI."""
    mod_name, func_name = name.rsplit('.', 1)
    circuits = str(Path(project_dir) / 'circuits')
    sys.path.insert(0, circuits)
    try:
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)
        d = func()
        svg = d.get_imagedata('svg')
        # white bg → page gray, black lines → light gray
        svg = svg.replace(b'fill: #ffffff', b'fill: #737373')
        svg = svg.replace(b'fill:#ffffff', b'fill:#737373')
        svg = svg.replace(b'stroke: #000000', b'stroke: #cacaca')
        svg = svg.replace(b'stroke:#000000', b'stroke:#cacaca')
        return f"data:image/svg+xml;base64,{base64.b64encode(svg).decode()}"
    finally:
        sys.path.pop(0)
