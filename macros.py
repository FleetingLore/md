"""
MkDocs macros for analog circuit simulation.

Macros:
  {{ circuit(data) }}       → CircuitJS interactive iframe
  {{ spice(netlist) }}      → ngspice simulation + toolbar
  {{ bode(netlist, node) }} → AC Bode plot + toolbar
  {{ tran(netlist, node) }} → Transient waveform plot + toolbar
"""

import subprocess, tempfile, os, shutil, re, hashlib, textwrap, base64, io, sys, importlib
from pathlib import Path

CIRCUITJS_URL = "https://www.falstad.com/circuit/circuitjs.html"
TIMEOUT_S     = 30

# ---- site theme colors ----
C_BG    = "#737373"
C_TEXT  = "#cacaca"
C_THEME = "#6cffca"
C_LINK  = "#8bf5ff"
C_MID   = "#929292"
C_GRID  = "#555555"

# inline SVG icons
_DATA_ICON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
    '<line x1="16" y1="17" x2="8" y2="17"/></svg>')

_CHART_ICON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 4-8"/><circle cx="7" cy="16" r="1.5"/>'
    '<circle cx="11" cy="8" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="19" cy="4" r="1.5"/></svg>')

_TRAN_ICON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 10l5 5 5-10"/>'
    '<circle cx="7" cy="10" r="1"/><circle cx="12" cy="15" r="1"/><circle cx="17" cy="5" r="1"/></svg>')

_COPY_ICON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>'
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>')

_EDIT_ICON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>'
    '<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>')

_RESTORE_ICON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="1 4 1 10 7 10"/>'
    '<path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>')


# ============================================================================
def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run_ngspice(netlist: str, cwd=None, auto_print=True):
    mod = _auto_add_print(netlist) if auto_print else netlist
    try:
        r = subprocess.run(["ngspice", "-b"], input=mod,
                           capture_output=True, text=True, timeout=TIMEOUT_S, cwd=cwd)
        return r.stdout, r.stderr, r.returncode == 0
    except subprocess.TimeoutExpired:
        return "", f"Simulation timed out ({TIMEOUT_S}s)", False
    except FileNotFoundError:
        return "", "ngspice not found – install with: brew install ngspice", False


def _auto_add_print(netlist: str) -> str:
    if re.search(r'\.print\s', netlist, re.IGNORECASE): return netlist
    if re.search(r'\.control\b', netlist, re.IGNORECASE): return netlist
    lines = netlist.strip().split('\n')
    body = '\n'.join(ln for ln in lines if not ln.strip().lower().startswith(('.ac ', '.tran ', '.dc ', '.print ', '.plot ', '.end')))
    nodes = {int(m.group(1)) for m in re.finditer(r'\b(\d+)\b', body) if int(m.group(1)) != 0}
    analyses = []
    for ln in lines:
        s = ln.strip().lower()
        if s.startswith('.ac '):   analyses.append('ac')
        elif s.startswith('.tran '): analyses.append('tran')
        elif s.startswith('.dc '):   analyses.append('dc')
    prints = []
    if nodes:
        nac = ' '.join(f'vdb({n}) vp({n})' for n in sorted(nodes))
        ntr = ' '.join(f'v({n})' for n in sorted(nodes))
        for a in analyses:
            if a == 'ac':   prints.append(f'.print ac {nac}')
            elif a == 'tran': prints.append(f'.print tran {ntr}')
            elif a == 'dc':   prints.append(f'.print dc {ntr}')
    out = []
    for ln in lines:
        if ln.strip() == '.end':
            out.extend(prints); out.append(ln)
        else:
            out.append(ln)
    return '\n'.join(out)


def _build_ctrl_netlist(netlist, data_file, wrdata_args, keep_analysis=None):
    lines = netlist.strip().split('\n')
    body, analysis = [], []
    for ln in lines:
        s = ln.strip().lower()
        if s.startswith(('.ac ', '.tran ', '.dc ')) or s == '.op':
            if keep_analysis is None or any(s.startswith(k) for k in keep_analysis):
                analysis.append(ln.strip().lstrip('.'))
        elif s == '.end': continue
        else: body.append(ln)
    ctrl = '.control\n' + '\n'.join(analysis)
    ctrl += f'\nwrdata {data_file} {wrdata_args}\n.endc'
    return '\n'.join(body) + '\n' + ctrl + '\n.end'


def _escape(t): return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _escape_attr(t): return t.replace('"', '&quot;')


def _clean_output(raw):
    lines, cleaned, skip = raw.split("\n"), [], True
    for ln in lines:
        if skip and (ln.startswith("******") or "ngspice" in ln.lower()): continue
        skip = False; cleaned.append(ln)
    return "\n".join(cleaned).strip()


def _data_uri(text, mime="text/plain"):
    return f"data:{mime};base64,{base64.b64encode(text.encode()).decode()}"


def _b64(data):
    if isinstance(data, bytes):
        return base64.b64encode(data).decode()
    return base64.b64encode(data.encode()).decode()


def _svg_uri(b: bytes):
    return f"data:image/svg+xml;base64,{base64.b64encode(b).decode()}"


def _resolve_netlist(netlist, caller=None):
    if netlist is not None: return textwrap.dedent(netlist).strip()
    if caller is not None:
        raw = caller()
        return textwrap.dedent(raw).strip() if raw else ""
    return ""


def _fallback(netlist, reason):
    return (f'<div class="spice-block"><div class="spice-warning">⚠️ {_escape(reason)}</div>'
            f'<pre class="spice-netlist"><code class="language-spice">{_escape(netlist)}</code></pre></div>')


def _toolbar(title: str = "", data_b64: str = "", chart_btns: str = "") -> str:
    """Toolbar: title left, charts / data / edit / copy-restore right."""
    data_btn = f'<button title="数据" class="spice-data-btn">{_DATA_ICON}</button>'
    return (
        f'<div class="spice-toolbar">'
        f'<span class="spice-toolbar-title">{title}</span>'
        f'<span class="spice-toolbar-actions">'
        f'{chart_btns}'
        f'{data_btn}'
        f'<button onclick="toggleEdit(this)" title="编辑" class="spice-edit-btn" '
        f'data-edit="{_escape_attr(_EDIT_ICON)}">{_EDIT_ICON}</button>'
        f'<button onclick="copySpiceNetlist(this)" title="Copy" class="spice-copy-btn" '
        f'data-icon="{_escape_attr(_COPY_ICON)}" data-restore="{_escape_attr(_RESTORE_ICON)}">{_COPY_ICON}</button>'
        f'</span>'
        f'</div>'
    )


def _spice_details(escaped, ok, title="SPICE", data_b64="", chart_btns=""):
    tb = _toolbar(title, data_b64, chart_btns)
    return (f'{tb}<div class="spice-code-area">'
            f'<pre class="spice-netlist"><code class="language-spice">{escaped}</code></pre></div>')


def _make_bode_svg(netlist, node_clean):
    """Returns (svg_bytes, output_text) or raises."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    data_file = "_spice_data.txt"
    wrdata_args = f"vdb({node_clean}) vp({node_clean})"
    mod = _build_ctrl_netlist(netlist, data_file, wrdata_args, keep_analysis=['.ac'])
    with tempfile.TemporaryDirectory() as td:
        stdout, stderr, ok = _run_ngspice(mod, cwd=td, auto_print=False)
        dp = os.path.join(td, data_file)
        if not os.path.isfile(dp):
            raise RuntimeError(stdout + "\n" + stderr + "\n(no data exported)")
        data = np.loadtxt(dp)
        freq, mag = data[:, 0], data[:, 1]
        phase = data[:, 2] if data.shape[1] > 2 else None
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5), sharex=True, constrained_layout=True)
        ax1.semilogx(freq, mag, color=C_THEME, lw=1.5)
        ax1.set_ylabel("Magnitude (dB)", color=C_TEXT)
        ax1.grid(True, alpha=0.25, color=C_MID)
        ax1.tick_params(colors=C_TEXT, labelsize=8)
        for s in ax1.spines.values(): s.set_color(C_GRID)
        ax2.semilogx(freq, phase if phase is not None else mag*0, color=C_LINK, lw=1.5)
        ax2.set_ylabel("Phase (°)", color=C_TEXT)
        ax2.set_xlabel("Frequency (Hz)", color=C_TEXT)
        ax2.grid(True, alpha=0.25, color=C_MID)
        ax2.tick_params(colors=C_TEXT, labelsize=8)
        for s in ax2.spines.values(): s.set_color(C_GRID)
        fig.patch.set_facecolor(C_BG)
        ax1.set_facecolor(C_BG); ax2.set_facecolor(C_BG)
        buf = io.BytesIO()
        fig.savefig(buf, format="svg", dpi=100, facecolor=C_BG, edgecolor="none", bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue(), _clean_output(stdout + "\n" + stderr)


def _make_tran_svg(netlist, node):
    """Returns (svg_bytes, output_text) or raises."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    data_file = "_spice_tran.txt"
    mod = _build_ctrl_netlist(netlist, data_file, node, keep_analysis=['.tran'])
    with tempfile.TemporaryDirectory() as td:
        stdout, stderr, ok = _run_ngspice(mod, cwd=td, auto_print=False)
        dp = os.path.join(td, data_file)
        if not os.path.isfile(dp):
            raise RuntimeError(stderr)
        data = np.loadtxt(dp)
        t, sig = data[:, 0], data[:, 1] if data.shape[1] > 1 else data[:, 0]
        fig, ax = plt.subplots(figsize=(8, 3), constrained_layout=True)
        ax.plot(t, sig, color=C_THEME, lw=1.5)
        ax.set_ylabel(_escape(node), color=C_TEXT)
        ax.set_xlabel("Time (s)", color=C_TEXT)
        ax.grid(True, alpha=0.25, color=C_MID)
        ax.tick_params(colors=C_TEXT, labelsize=8)
        for s in ax.spines.values(): s.set_color(C_GRID)
        fig.patch.set_facecolor(C_BG); ax.set_facecolor(C_BG)
        buf = io.BytesIO()
        fig.savefig(buf, format="svg", dpi=100, facecolor=C_BG, edgecolor="none", bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue(), _clean_output(stdout + "\n" + stderr)


# ============================================================================
def define_env(env):

    @env.macro
    def circuit(data, width="100%", height=500):
        return (f'<div class="circuit-container"><iframe src="{CIRCUITJS_URL}?ctz={data.strip()}" '
                f'style="width:{width};height:{height}px;border-radius:6px" loading="lazy" '
                f'title="CircuitJS simulation"></iframe></div>')

    @env.macro
    def spice(netlist=None, caller=None, title="SPICE"):
        netlist = _resolve_netlist(netlist, caller)
        if not netlist: return ""
        has_ac   = bool(re.search(r'\.ac\s', netlist, re.IGNORECASE))
        has_tran = bool(re.search(r'\.tran\s', netlist, re.IGNORECASE))
        chart_btns = ""
        if has_ac:
            chart_btns += f'<button title="Bode 图" class="spice-chart-btn">{_CHART_ICON}</button>'
        if has_tran:
            chart_btns += f'<button title="瞬态波形" class="spice-chart-btn">{_TRAN_ICON}</button>'
        return f'<div class="spice-block">{_spice_details(_escape(netlist), True, title, "", chart_btns)}</div>'

    @env.macro
    def bode(netlist=None, node="v(2)", title="Bode Plot", caller=None, label="SPICE"):
        netlist = _resolve_netlist(netlist, caller)
        if not netlist: return ""
        chart_btns = f'<button title="Bode 图" class="spice-chart-btn">{_CHART_ICON}</button>'
        return f'<div class="spice-block">{_spice_details(_escape(netlist), True, label, "", chart_btns)}</div>'

    @env.macro
    def tran(netlist=None, node="v(2)", title="Transient Response", caller=None, label="SPICE"):
        netlist = _resolve_netlist(netlist, caller)
        if not netlist: return ""
        chart_btns = f'<button title="瞬态波形" class="spice-chart-btn">{_TRAN_ICON}</button>'
        return f'<div class="spice-block">{_spice_details(_escape(netlist), True, label, "", chart_btns)}</div>'

    @env.macro
    def sch(name):
        try:
            from macros_schemdraw import schemdraw_svg
            uri = schemdraw_svg(env.project_dir, name)
            return f'<img src="{uri}" style="max-width:100%" loading="lazy" alt="{name}">'
        except Exception as e:
            return f'<div class="spice-warning">⚠️ sch({name}): {str(e)}</div>'

