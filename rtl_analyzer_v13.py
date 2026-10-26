import os
import re
import shutil
import sys
import subprocess
import tempfile
import json
import importlib
import importlib.util
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DEFAULT_YOSYS = r"C:\Users\LENOVO\oss-cad-suite-windows-x64-20261014\oss-cad-suite\bin\yosys.exe"

st.set_page_config(page_title="RTL Analyzer AI", page_icon="🔬", layout="wide")
st.markdown("""
<style>
:root{--bg:#0b1120;--panel:#111c2e;--line:#26364b;--teal:#19c6b4;--teal2:#087f80;--text:#e5edf7;--muted:#91a4ba}
.stApp{background:radial-gradient(ellipse at 15% 0%,#14283a 0%,transparent 45%),var(--bg);color:var(--text)}
#MainMenu,footer{visibility:hidden}
header[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1180px;padding-top:1.2rem;padding-bottom:4rem}
[data-testid="stSidebar"]{background:#0e1a2b;border-right:1px solid var(--line)}
.hero{background:linear-gradient(135deg,#123247 0%,#0b1120 65%);border:1px solid var(--line);border-radius:18px;padding:30px 34px;margin:4px 0 16px 0}
.hero h1{margin:0 0 6px 0;font-size:2.3rem;letter-spacing:-.5px;color:var(--text)}
.hero p{margin:0 0 14px 0;color:var(--muted);font-size:1.05rem}
.pill{display:inline-block;margin:0 8px 6px 0;padding:5px 13px;border-radius:999px;background:#0f2a35;border:1px solid var(--teal2);color:var(--teal);font-size:.82rem;font-weight:600}
.steps{display:flex;gap:12px;margin:0 0 18px 0}
.step{flex:1;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 16px}
.step b{color:var(--teal)}.step span{display:block;color:var(--muted);font-size:.88rem;margin-top:3px}
.stApp h2,.stApp h3{color:var(--text);border-left:4px solid var(--teal);padding-left:12px}
.stTextArea textarea{font-family:'JetBrains Mono',Consolas,'Courier New',monospace;font-size:14px;background:#0a1626;border:1px solid var(--line);border-radius:10px;color:var(--text)}
[data-testid="stMetric"]{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.stButton>button,.stDownloadButton>button{border-radius:10px;font-weight:650;border:1px solid var(--teal);background:var(--teal2);color:#fff;transition:all .15s}
.stButton>button:hover,.stDownloadButton>button:hover{background:var(--teal);color:#06202a;transform:translateY(-1px);box-shadow:0 6px 18px rgba(25,198,180,.25)}
.stButton>button[kind="primary"]{background:linear-gradient(90deg,#087f80,#19c6b4);color:#04161d;font-size:1.02rem;padding:.65rem 1rem}
[data-testid="stDataFrame"],[data-testid="stExpander"]{border:1px solid var(--line);border-radius:12px}
[data-testid="stAlert"]{border-radius:12px}
hr{border-color:var(--line)}
@media (max-width:700px){.steps{flex-direction:column}.hero{padding:22px}.hero h1{font-size:1.7rem}}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>🔬 RTL Analyzer <span style="color:#19c6b4">AI</span></h1>
  <p>Paste your Verilog. The AI finds the errors, explains them and writes the corrected version. Yosys then verifies the fix.</p>
  <span class="pill">🧠 AI error detection</span><span class="pill">✅ Yosys-verified fixes</span><span class="pill">🆓 Free AI providers</span><span class="pill">⚖️ Formal equivalence</span>
</div>
<div class="steps">
  <div class="step"><b>1 · Add your design</b><span>Upload a .v / .sv file or type in the editor</span></div>
  <div class="step"><b>2 · Run AI Smart Debug</b><span>Errors explained, corrected code generated</span></div>
  <div class="step"><b>3 · Verify and export</b><span>Yosys check, equivalence, report, download</span></div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🤖 AI assistant")
    AI_PRESETS = {
        "Groq: FREE (easiest, email signup)": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "https://console.groq.com/keys", "GROQ_API_KEY", "Sign up with just an email. No credit card."),
        "Google Gemini: FREE": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", "https://aistudio.google.com/app/apikey", "GEMINI_API_KEY", "Sign in with your Google account. Note: free-tier prompts may be used by Google."),
        "OpenRouter: FREE models": ("https://openrouter.ai/api/v1", "openai/gpt-oss-20b:free", "https://openrouter.ai/keys", "OPENROUTER_API_KEY", "Free models carry a :free suffix; edit the model name if it is retired."),
        "Claude: paid (best quality)": None,
    }
    ai_provider = st.selectbox("AI provider", list(AI_PRESETS), key="ai_provider_v8")
    _slug = re.sub(r"\W+", "_", ai_provider)
    if AI_PRESETS[ai_provider] is None:
        ai_model = st.text_input("Claude model", value="claude-sonnet-5-5", key=f"model_{_slug}")
        ai_key = st.text_input("Anthropic API key", value=os.environ.get("ANTHROPIC_API_KEY", ""), type="password", key=f"key_{_slug}")
        st.markdown("[Get a key](https://console.anthropic.com) (paid, needs credits)")
        ai_cfg = {"provider": "claude", "model": ai_model.strip(), "key": ai_key.strip(), "label": f"Claude ({ai_model.strip()})"}
    else:
        _url, _dmodel, _keylink, _env, _note = AI_PRESETS[ai_provider]
        ai_model = st.text_input("Model", value=_dmodel, key=f"model_{_slug}")
        ai_key = st.text_input("Free API key", value=os.environ.get(_env, ""), type="password", key=f"key_{_slug}")
        st.markdown(f"[Click here to get your free key]({_keylink})")
        st.caption(_note)
        with st.expander("Advanced"):
            _override = st.text_input("Custom endpoint base URL (optional)", value="", key=f"url_{_slug}")
        ai_cfg = {"provider": "openai", "url": (_override.strip() or _url).rstrip("/"), "model": ai_model.strip(), "key": ai_key.strip(), "label": ai_model.strip(), "compact": True}
    ai_cfg["timeout"] = int(st.number_input("AI timeout (seconds)", min_value=10, max_value=600, value=180, step=10, key="ai_timeout_v8"))
    st.divider()
    st.header("Tool configuration")
    yosys_path = st.text_input("Yosys executable (optional)", value=DEFAULT_YOSYS)
    st.caption("If this file is missing or blocked by Windows, the app automatically falls back to the built-in Yosys (yowasp-yosys), which needs no .exe.")
    yosys_status_slot = st.container()
    st.divider()
    st.markdown("**Timing / physical metrics**")
    st.caption("Real library area and timing require a technology Liberty (.lib) file. Sign-off timing also requires valid constraints and a supported timing engine such as OpenSTA. Generic Yosys cell counts are not physical area or delay.")

DEFAULT_RTL = '''module mux2 (\n    input a,\n    input b,\n    input sel,\n    output y\n);\nassign y = sel ? b : a;\nendmodule\n'''

# Session state
if "rtl_editor_value" not in st.session_state:
    st.session_state.rtl_editor_value = DEFAULT_RTL
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "last_analyzed_rtl" not in st.session_state:
    st.session_state.last_analyzed_rtl = None

# Upload is a way to load text into the single editor, not a second editor.
up = st.file_uploader("Load Verilog source into the editor (.v / .sv)", type=["v", "sv"], key="rtl_upload")
if up is not None:
    try:
        loaded = up.getvalue().decode("utf-8", errors="replace")
        if st.session_state.get("last_loaded_upload") != (up.name, len(up.getvalue())):
            st.session_state.rtl_editor_value = loaded
            st.session_state.last_loaded_upload = (up.name, len(up.getvalue()))
            st.session_state.analysis_result = None
    except Exception as exc:
        st.error(f"Could not read uploaded source: {exc}")

st.subheader("1. Verilog RTL Editor")
rtl_code = st.text_area("Edit your design here", key="rtl_editor_value", height=360, label_visibility="collapsed", help="This is the only editor for the active design. Diagnostics below refresh whenever Streamlit reruns after an edit.")

# Select the design top explicitly; source order is not a reliable way to identify it.
module_choices = list(dict.fromkeys(re.findall(r"\bmodule\s+([A-Za-z_]\w*)", re.sub(r"/\*.*?\*/|//[^\n]*", "", rtl_code, flags=re.S))))
if module_choices:
    previous_top = st.session_state.get("selected_top_module")
    default_index = module_choices.index(previous_top) if previous_top in module_choices else 0
    top_module = st.selectbox("Top module to analyze", module_choices, index=default_index, key="selected_top_module")
else:
    top_module = None
    st.warning("No module declaration detected yet. Add a module before running synthesis.")

ai_top = st.container()   # AI Smart Debug is rendered here, right under the editor


def strip_comments(code):
    # Preserve newlines for line-number reporting.
    code = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), code, flags=re.S)
    return re.sub(r"//[^\n]*", "", code)


def live_diagnostics(code):
    clean = strip_comments(code)
    rows = []
    def add(line, severity, message):
        rows.append({"Line": line, "Severity": severity, "Finding": message, "Source": "Quick source check"})
    if not code.strip():
        return [{"Line": 1, "Severity": "ERROR", "Finding": "Editor is empty. Enter or load Verilog RTL.", "Source": "Quick source check"}]
    starts = list(re.finditer(r"\bmodule\b", clean))
    ends = list(re.finditer(r"\bendmodule\b", clean))
    if not starts:
        add(1, "ERROR", "No module declaration found.")
    if len(starts) != len(ends):
        pos = starts[-1].start() if starts else 0
        add(clean.count("\n", 0, pos) + 1, "ERROR", f"Found {len(starts)} module keyword(s) but {len(ends)} endmodule keyword(s). Check module boundaries.")
    names = re.findall(r"\bmodule\s+([A-Za-z_]\w*)", clean)
    for name in sorted(set(names)):
        if names.count(name) > 1:
            m = re.search(r"\bmodule\s+" + re.escape(name) + r"\b", clean)
            add(clean.count("\n", 0, m.start()) + 1, "ERROR", f"Duplicate module name '{name}'.")
    begin_count = len(re.findall(r"\bbegin\b", clean))
    end_count = len(re.findall(r"\bend\b", clean))
    if begin_count != end_count:
        add(1, "WARNING", f"Found {begin_count} begin keyword(s) and {end_count} end keyword(s). Check procedural block boundaries.")
    # Also catch minified/single-line RTL where an assign does not begin the line.
    # This is a hint only; Yosys remains the authoritative parser.
    for match in re.finditer(r"\bassign\b([^;\n]*)(?=\bendmodule\b|$)", clean):
        fragment = match.group(0)
        if ";" not in fragment:
            line_no = clean.count("\n", 0, match.start()) + 1
            add(line_no, "WARNING", "Continuous assignment may be missing a semicolon before the next statement or endmodule.")
    for line_no, raw in enumerate(clean.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("`"):
            continue
        if re.match(r"^assign\b", line) and not line.endswith(";"):
            add(line_no, "WARNING", "Continuous assignment may be missing a semicolon.")
        if re.match(r"^(wire|reg|logic|integer|parameter|localparam)\b", line):
            # ANSI port declarations and parameter headers can end with comma or ')' instead.
            if not line.endswith((";", ",", ")", ");", "):", "],")) and not line.endswith(":"):
                add(line_no, "WARNING", "Declaration may be missing a semicolon or comma. Confirm the surrounding port/declaration list.")
        if re.search(r"\bassign\s+(\w+)\s*=\s*\1\s*;", line):
            add(line_no, "ERROR", "Signal is continuously assigned to itself.")
    if re.search(r"\balways\s*@\s*\(\s*\*\s*\)", clean):
        add(1, "INFO", "Combinational always block detected. Check that every assigned signal receives a value on every path to avoid latch inference.")
    if re.search(r"\balways\s*@\s*\([^)]*(posedge|negedge)", clean):
        add(1, "INFO", "Clocked logic detected. Non-blocking assignments (<=) are generally preferred in clocked always blocks.")
    if not rows:
        rows.append({"Line": "—", "Severity": "INFO", "Finding": "No common source-level patterns flagged. Run Full Analysis; this quick check cannot prove correctness.", "Source": "Quick source check"})
    return sorted(rows, key=lambda r: (r["Line"] == "—", r["Line"] if isinstance(r["Line"], int) else 0))


def optimization_suggestions(code, yosys_log=""):
    clean = strip_comments(code)
    out = []
    if re.search(r"\balways\s*@\s*\(\s*\*\s*\)", clean):
        out.append({"Priority": "Review", "Suggestion": "Inspect combinational always blocks for incomplete assignments; Yosys may report inferred latches in the synthesis log."})
    if re.search(r"\bcase\s*\(", clean) and not re.search(r"\bdefault\s*:", clean):
        out.append({"Priority": "Review", "Suggestion": "A case statement has no visible default branch. For combinational logic, verify all cases are assigned; a default may prevent latch inference."})
    if re.search(r"\balways\s*@\s*\([^)]*(posedge|negedge)", clean) and re.search(r"\b(?:<=|=)", clean):
        out.append({"Priority": "Review", "Suggestion": "Review sequential assignments, reset style, and clock enables. Use non-blocking assignments in edge-triggered blocks unless there is a specific reason not to."})
    if re.search(r"\bassign\s+(\w+)\s*=\s*\1\s*;", clean):
        out.append({"Priority": "High", "Suggestion": "Self-assignment detected; this is likely unintended and should be corrected."})
    if yosys_log:
        for line in yosys_log.splitlines():
            if re.search(r"latch", line, re.I) and re.search(r"infer|warning|latch", line, re.I):
                out.append({"Priority": "High", "Suggestion": "Yosys log mentions a latch. Inspect the reported signal and make combinational assignments complete if a latch is unintended."})
                break
        if re.search(r"multiple conflicting drivers|multiple drivers", yosys_log, re.I):
            out.append({"Priority": "High", "Suggestion": "Yosys reports multiple drivers. Ensure each procedural signal is driven from only one intended process/source."})
    if not out:
        out.append({"Priority": "Info", "Suggestion": "No rule-based optimization warning was detected. This is not proof of optimal PPA; inspect synthesis statistics and timing under a target library/constraints."})
    return out


def locate_tool(user_path, name):
    p = Path(user_path.strip().strip('"')) if user_path.strip() else None
    if p and p.is_file():
        return str(p)
    return shutil.which(name)


# Built-in Yosys: the yowasp-yosys pip package runs Yosys inside Python, so no separate
# yosys.exe is launched. This avoids Windows Code Integrity / App Control blocks on unsigned .exe files.
YOSYS_PY_CMD = [sys.executable, "-c", "import sys\nfrom yowasp_yosys import run_yosys\nsys.exit(run_yosys(sys.argv[1:]))"]


def yowasp_available():
    importlib.invalidate_caches()
    return importlib.util.find_spec("yowasp_yosys") is not None


def _probe_yosys(cmd, timeout=400):
    try:
        r = subprocess.run(list(cmd) + ["-V"], capture_output=True, text=True, timeout=timeout, errors="replace")
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return (r.returncode == 0 and "yosys" in out.lower()), out[-300:]
    except subprocess.TimeoutExpired:
        return False, "timed out while starting"
    except Exception as exc:
        return False, str(exc)


def get_yosys(user_path):
    """Return a working Yosys command (list) or None. Tries: your path, PATH, then built-in yowasp-yosys."""
    key = (user_path or "").strip()
    cache = st.session_state.setdefault("_yosys_cache", {})
    if key in cache:
        return cache[key]["cmd"]
    candidates, tried = [], []
    p = Path(key.strip('"')) if key else None
    if p and p.is_file():
        candidates.append(([str(p)], f"native executable: {p}"))
    w = shutil.which("yosys")
    if w and not (p and str(p) == w):
        candidates.append(([w], f"native executable on PATH: {w}"))
    if yowasp_available():
        candidates.append((YOSYS_PY_CMD, "built-in Yosys (yowasp-yosys, runs inside Python)"))
    for cmd, label in candidates:
        ok, info = _probe_yosys(cmd)
        if ok:
            cache[key] = {"cmd": cmd, "label": label, "tried": tried}
            return cmd
        tried.append(f"{label}: {info}")
    cache[key] = {"cmd": None, "label": "none", "tried": tried}
    return None


with st.sidebar:
    with yosys_status_slot:
        with st.spinner("Detecting Yosys (the first built-in start can take up to a minute)..."):
            _ycmd = get_yosys(yosys_path)
        _yinfo = st.session_state["_yosys_cache"][(yosys_path or "").strip()]
        if _ycmd:
            st.success(f"Yosys ready: {_yinfo['label']}")
        else:
            st.error("No working Yosys found.")
            for _t in _yinfo["tried"]:
                st.caption("Tried: " + _t)
        if _yinfo["tried"] and _ycmd:
            for _t in _yinfo["tried"]:
                st.caption("Skipped: " + _t)
        if not yowasp_available():
            if st.button("Install built-in Yosys (no .exe needed)", key="install_yowasp"):
                with st.spinner("Installing yowasp-yosys with pip..."):
                    r = subprocess.run([sys.executable, "-m", "pip", "install", "yowasp-yosys"], capture_output=True, text=True, errors="replace")
                st.session_state.pop("_yosys_cache", None)
                if r.returncode == 0:
                    st.rerun()
                else:
                    st.error("pip install failed:\n" + (r.stdout + r.stderr)[-600:])
        if st.button("Re-detect Yosys", key="redetect_yosys"):
            st.session_state.pop("_yosys_cache", None)
            st.rerun()


def parse_stats(log):
    """Parse Yosys stat output. Supports both the old ('Number of cells: 10')
    and new ('10 cells') formats."""
    def last(patterns):
        for pat in patterns:
            found = re.findall(pat, log, re.M)
            if found:
                return int(found[-1])
        return None
    area = re.findall(r"Chip area for (?:top )?module .*?:\s*([0-9.eE+-]+)", log)
    return {
        "Synthesized cells": last([r"^\s*(\d+)\s+cells\s*$", r"^\s*Number of cells:\s*(\d+)\s*$"]),
        "Wires": last([r"^\s*(\d+)\s+wires\s*$", r"^\s*Number of wires:\s*(\d+)\s*$"]),
        "Wire bits": last([r"^\s*(\d+)\s+wire bits\s*$", r"^\s*Number of wire bits:\s*(\d+)\s*$"]),
        "Library area": float(area[-1]) if area else None,
    }


def parse_yosys_error_lines(log):
    """Extract source locations from common Yosys diagnostics; preserve the full raw log."""
    rows = []
    seen = set()
    patterns = [
        re.compile(
            r"(?P<file>(?:[A-Za-z]:)?[^\r\n]*?\.(?:v|sv|vh)):"
            r"(?P<line>\d+)(?:[.:](?P<col>\d+))?"
            r"(?:[-.](?:\d+)(?:[.:](?:\d+))?)?:?\s*(?P<msg>.*)",
            re.I,
        ),
        re.compile(
            r"(?P<file>[^\s]+\.(?:v|sv|vh))\((?P<line>\d+)\):\s*(?P<msg>.*)",
            re.I,
        ),
    ]
    for raw in log.splitlines():
        line_text = raw.strip()
        if not line_text:
            continue
        for pat in patterns:
            m = pat.search(line_text)
            if not m:
                continue
            msg = m.group("msg").strip()
            severity = "ERROR" if re.search(r"\b(error|syntax error|fatal)\b", msg, re.I) else (
                "WARNING" if re.search(r"\bwarning\b", msg, re.I) else "INFO"
            )
            row = {
                "Line": int(m.group("line")),
                "Column": m.groupdict().get("col") or "—",
                "Severity": severity,
                "Finding": msg or line_text,
                "Source": "Yosys",
            }
            key = (row["Line"], row["Column"], row["Severity"], row["Finding"])
            if key not in seen:
                rows.append(row)
                seen.add(key)
            break
    for raw in log.splitlines():
        stripped = raw.strip()
        if re.search(r"\b(?:ERROR|FATAL):\s*", stripped, re.I):
            # Avoid duplicating an error already extracted with a source line.
            if any(row["Line"] != "—" and row["Finding"] in stripped for row in rows):
                continue
            key = ("—", "—", "ERROR", stripped)
            if key not in seen:
                rows.append({
                    "Line": "—", "Column": "—", "Severity": "ERROR",
                    "Finding": stripped,
                    "Source": "Yosys log (tool emitted no source line)",
                })
                seen.add(key)
    return rows


GATE_TO_SKY = {"$_NOT_": "inv_1", "$_AND_": "and2_0", "$_OR_": "or2_0", "$_NAND_": "nand2_1", "$_NOR_": "nor2_1", "$_XOR_": "xor2_1",
               "$_XNOR_": "xnor2_1", "$_MUX_": "mux2_1", "$_ANDNOT_": "and2b_1", "$_ORNOT_": "or2b_1", "$_BUF_": "buf_1"}


def estimate_lib_area(log, lib_text):
    """Approximate library area when ABC cannot run: each generic gate is priced as the matching small cell in the
    Liberty file. Not ABC-optimized and not sign-off area. Returns (area or None, list of unpriced cell types)."""
    areas, current = {}, None
    for m in re.finditer(r'^\s*cell\s*\(\s*"?([\w$]+)"?\s*\)\s*\{|^\s*area\s*:\s*([0-9.]+)\s*;', lib_text, re.M):
        if m.group(1):
            current = m.group(1)
        elif current and current not in areas:
            areas[current] = float(m.group(2))
    inv = next((k for k in areas if k.endswith("__inv_1")), None)
    if not inv:
        return None, []
    prefix = inv[:-len("inv_1")]
    block = log.split("Printing statistics")[-1]
    total, missing = 0.0, []
    for count, ctype in re.findall(r"^\s*(\d+)\s+(\$_\w+_)\s*$", block, re.M):
        if re.match(r"\$_(?:S?DFF|DFFE|SDFFE|SDFFCE|ADFF|DLATCH)\w*_$", ctype):
            name = "dfxtp_1"
        else:
            name = GATE_TO_SKY.get(ctype)
        if name and prefix + name in areas:
            total += int(count) * areas[prefix + name]
        else:
            missing.append(ctype)
    return total, missing


def _as_cmd(c):
    return list(c) if isinstance(c, (list, tuple)) else [c]


def run_yosys(code, yosys_exe, liberty_path=None, top_override=None):
    """Run Yosys checks/synthesis. If Liberty is supplied, map to that library and return a mapped netlist."""
    if not code.strip():
        return {"ok": False, "log": "RTL editor is empty.", "stats": {}, "findings": [], "netlist": ""}
    if not yosys_exe:
        return {"ok": False, "log": "No working Yosys was found. Use 'Install built-in Yosys' in the sidebar, or set a working yosys.exe path.", "stats": {}, "findings": [], "netlist": ""}
    module_names = re.findall(r"\bmodule\s+([A-Za-z_]\w*)", strip_comments(code))
    if not module_names:
        return {"ok": False, "log": "No module declaration found in RTL.", "stats": {}, "findings": [], "netlist": ""}
    top = top_override if top_override in module_names else module_names[0]
    with tempfile.TemporaryDirectory(prefix="rtl_analyzer_") as td:
        work = Path(td)
        vf = work / "design.v"
        mapped = work / "mapped.v"
        vf.write_text(code, encoding="utf-8")
        # Relative file names (cwd = work dir) work for native Yosys and the built-in WASM Yosys alike.
        script = ['read_verilog -sv design.v', "hierarchy -check -top " + top, "proc", "check"]
        if liberty_path and Path(liberty_path).is_file():
            shutil.copy(liberty_path, work / "lib.lib")
            lib = "lib.lib"
            script += [f'synth -top {top} -noabc', f'dfflibmap -liberty {lib}', f'abc -liberty {lib}', "clean", f'stat -liberty {lib}', 'write_verilog -noattr -noexpr mapped.v', "check"]
        else:
            script += [f"synth -top {top}", "stat", "check"]
        try:
            def _run(scr):
                pr = subprocess.run([*_as_cmd(yosys_exe), "-p", "; ".join(scr)], cwd=str(work), capture_output=True, text=True, timeout=180, errors="replace")
                return pr, pr.stdout + "\n" + pr.stderr
            proc, log = _run(script)
            has_error = proc.returncode != 0 or bool(re.search(r"\bERROR:\s", log, re.I))
            finished = bool(re.search(r"End of script", log))
            note = ""
            lib_on = bool(liberty_path and Path(liberty_path).is_file())
            if not has_error and not finished:
                # Yosys exited without finishing (seen with some built-in/WASM builds when the ABC step cannot run).
                # Retry without ABC so parsing, hierarchy, process lowering, checks and cell counts are still real.
                if lib_on:
                    script2 = ['read_verilog -sv design.v', f"hierarchy -check -top {top}", "proc", "check", f"synth -top {top} -noabc", "stat", "check"]
                else:
                    script2 = [x.replace(f"synth -top {top}", f"synth -top {top} -noabc") for x in script]
                proc2, log2 = _run(script2)
                log = log + "\n\n===== Retried without ABC because the first run ended before 'End of script' =====\n" + log2
                proc = proc2
                has_error = proc.returncode != 0 or bool(re.search(r"\bERROR:\s", log2, re.I))
                finished = bool(re.search(r"End of script", log2))
                note = "The ABC optimization step could not run in this Yosys build, so synthesis was run with -noabc. Parsing, hierarchy, checks and cell counts are real, but counts are not ABC-optimized."
                if lib_on:
                    note += " Library mapping needs ABC, so Library area below is an ESTIMATE: each generic gate priced as a matching small cell from your Liberty file (not ABC-mapped, not sign-off)."
            if not has_error and not finished:
                has_error = True
                log += "\n\nERROR: Yosys exited before completing the script (no 'End of script' marker). Treating the run as failed."
            netlist = mapped.read_text(encoding="utf-8", errors="replace") if mapped.is_file() else ""
            _stats = parse_stats(log)
            if note and lib_on and not has_error and _stats.get("Library area") is None:
                try:
                    _est, _miss = estimate_lib_area(log, (work / "lib.lib").read_text(encoding="utf-8", errors="replace"))
                    if _est is not None:
                        _stats["Library area"] = _est
                        if _miss:
                            note += " Not priced: " + ", ".join(sorted(set(_miss))) + "."
                except Exception:
                    pass
            return {"ok": not has_error, "log": log, "stats": _stats, "findings": parse_yosys_error_lines(log), "returncode": proc.returncode, "netlist": netlist, "top": top, "note": note}
        except subprocess.TimeoutExpired as exc:
            return {"ok": False, "log": "Yosys timed out after 180 seconds.\n" + str(exc), "stats": {}, "findings": [], "netlist": "", "top": top}
        except Exception as exc:
            hint = ""
            if "4551" in str(exc) or "application control" in str(exc).lower() or isinstance(exc, PermissionError):
                hint = ("\n\nWindows blocked this executable (Code Integrity / App Control policy). "
                        "This is a Windows security setting, not an app bug. Try: unblock the file "
                        "(Properties > Unblock), reinstall OSS CAD Suite to a user folder such as "
                        "C:\\Users\\<you>\\tools, or run Yosys elsewhere and point the sidebar to it.")
            return {"ok": False, "log": f"Could not execute Yosys: {exc}{hint}", "stats": {}, "findings": [], "netlist": "", "top": top}


def run_opensta(sta_exe, liberty_bytes, sdc_bytes, netlist, top):
    """Run OpenSTA on a library-mapped gate-level netlist and user-provided constraints."""
    if not sta_exe:
        return {"ok": False, "log": "OpenSTA executable not found."}
    if not netlist.strip():
        return {"ok": False, "log": "No mapped netlist available. Run successful Liberty-based synthesis first."}
    with tempfile.TemporaryDirectory(prefix="rtl_sta_") as td:
        work = Path(td)
        lib = work / "target.lib"
        sdc = work / "design.sdc"
        v = work / "mapped.v"
        tcl = work / "run_sta.tcl"
        lib.write_bytes(liberty_bytes)
        sdc.write_bytes(sdc_bytes)
        v.write_text(netlist, encoding="utf-8")
        tcl.write_text("\n".join([
            f'read_liberty "{lib.as_posix()}"',
            f'read_verilog "{v.as_posix()}"',
            f'link_design {top}',
            f'read_sdc "{sdc.as_posix()}"',
            'report_checks -path_delay max -format full_clock_expanded',
            'report_checks -path_delay min -format full_clock_expanded',
            'report_design_area',
            'exit',
        ]), encoding="utf-8")
        try:
            run = subprocess.run([sta_exe, str(tcl)], cwd=str(work), capture_output=True, text=True, timeout=120, errors="replace")
            log = run.stdout + "\n" + run.stderr
            ok = run.returncode == 0 and not re.search(r"\b(error|can't read|failed)\b", log, re.I)
            slack = re.findall(r"slack\s+\((?:MET|VIOLATED)\)\s+([-+0-9.eE]+)", log, re.I)
            arrival = re.findall(r"data arrival time\s+([-+0-9.eE]+)", log, re.I)
            area = re.findall(r"Design area\s+([-+0-9.eE]+)", log, re.I)
            return {"ok": ok, "log": log, "worst_slack": float(slack[-1]) if slack else None, "arrival": float(arrival[-1]) if arrival else None, "area": float(area[-1]) if area else None}
        except subprocess.TimeoutExpired:
            return {"ok": False, "log": "OpenSTA timed out after 120 seconds."}
        except Exception as exc:
            return {"ok": False, "log": f"Could not run OpenSTA: {exc}"}


# Live quick diagnostics
st.subheader("2. Live Diagnostics")
quick = live_diagnostics(rtl_code)
q1, q2, q3 = st.columns(3)
q1.metric("Modules", len(re.findall(r"\bmodule\s+[A-Za-z_]\w*", strip_comments(rtl_code))))
q2.metric("Quick errors", sum(x["Severity"] == "ERROR" for x in quick))
q3.metric("Warnings / review", sum(x["Severity"] == "WARNING" for x in quick))
st.dataframe(pd.DataFrame(quick), use_container_width=True, hide_index=True)
st.caption("Quick diagnostics update on Streamlit reruns while editing. They are intentionally conservative. The Full Analysis button runs the actual HDL tool and is authoritative for tool-supported checks.")

# Library inputs for actual area and timing
st.subheader("3. Target Technology (optional, required for meaningful area/timing)")
lib_upload = st.file_uploader("Liberty timing library (.lib)", type=["lib"], key="liberty_upload")
sdc_upload = st.file_uploader("Timing constraints (.sdc, for external STA)", type=["sdc"], key="sdc_upload")
opensta_path = st.text_input("OpenSTA executable (optional; sta / opensta)", value=shutil.which("sta") or shutil.which("opensta") or "")
if not lib_upload:
    st.info("Without a target Liberty library, the tool can report synthesized cell counts but cannot truthfully report physical cell area or library-based delay.")
if lib_upload and not sdc_upload:
    st.warning("Liberty loaded. Library cell area can be reported if Yosys/ABC supports it, but meaningful timing analysis also needs clock/input/output constraints.")

st.subheader("4. One-Click Analysis")
run_clicked = st.button("🚀 Run Full Analysis: Parse + Check + Synthesize + Optimize Review", type="primary", use_container_width=True)
if run_clicked:
    yosys_exe = get_yosys(yosys_path)
    lib_path = None
    if lib_upload:
        # Persist only for this run; temporary files are removed after synthesis.
        temp_lib = tempfile.NamedTemporaryFile(delete=False, suffix=".lib")
        temp_lib.write(lib_upload.getvalue()); temp_lib.close(); lib_path = temp_lib.name
    with st.spinner("Running Yosys parser, hierarchy validation, process lowering, synthesis, structural checks and statistics..."):
        result = run_yosys(rtl_code, yosys_exe, lib_path, top_module)
    if result.get("ok") and lib_upload and sdc_upload:
        sta_exe = locate_tool(opensta_path, "sta") or locate_tool(opensta_path, "opensta")
        result["timing"] = run_opensta(sta_exe, lib_upload.getvalue(), sdc_upload.getvalue(), result.get("netlist", ""), result.get("top", ""))
    else:
        result["timing"] = None
    if lib_path:
        try: Path(lib_path).unlink(missing_ok=True)
        except Exception: pass
    result["rtl_snapshot"] = rtl_code
    result["optimization"] = optimization_suggestions(rtl_code, result.get("log", ""))
    st.session_state.analysis_result = result
    st.session_state.last_analyzed_rtl = rtl_code

result = st.session_state.analysis_result
if result:
    st.divider(); st.subheader("Full Analysis Results")
    if result["rtl_snapshot"] != rtl_code:
        st.warning("The editor has changed since this analysis. These results apply to the RTL snapshot that was analyzed. Run Full Analysis again to refresh them.")
    if result["ok"]:
        st.success("Yosys completed the validation and synthesis flow without reporting an ERROR.")
        if result.get("note"):
            st.warning(result["note"])
    else:
        st.error("Analysis failed or Yosys reported an error. Review all findings and the complete log below.")
    stats = result.get("stats", {})
    a,b,c,d = st.columns(4)
    a.metric("Synthesized cells", stats.get("Synthesized cells") if stats.get("Synthesized cells") is not None else "N/A")
    b.metric("Wires", stats.get("Wires") if stats.get("Wires") is not None else "N/A")
    c.metric("Wire bits", stats.get("Wire bits") if stats.get("Wire bits") is not None else "N/A")
    d.metric("Library area", f'{stats["Library area"]:.4g}' if stats.get("Library area") is not None else "N/A")
    if stats.get("Library area") is None:
        st.caption("Library area is N/A unless the synthesis log includes a target-library area report. Cell count is not a substitute for area.")
    timing = result.get("timing")
    if timing:
        st.markdown("#### OpenSTA static timing results")
        if timing.get("ok"):
            t1, t2, t3 = st.columns(3)
            t1.metric("Worst reported slack", f'{timing["worst_slack"]:.4g}' if timing.get("worst_slack") is not None else "N/A")
            t2.metric("Reported data arrival", f'{timing["arrival"]:.4g}' if timing.get("arrival") is not None else "N/A")
            t3.metric("STA design area", f'{timing["area"]:.4g}' if timing.get("area") is not None else "N/A")
        else:
            st.warning("OpenSTA could not complete timing analysis. Inspect its log and verify the Liberty/SDC/netlist are compatible.")
        with st.expander("OpenSTA timing log", expanded=not timing.get("ok")):
            st.code(timing.get("log", ""), language="text")
    # Unified diagnostics table: live source hints + actual Yosys findings in one place.
    tool_findings = result.get("findings", [])
    quick_snapshot = live_diagnostics(result.get("rtl_snapshot", ""))
    unified = quick_snapshot + tool_findings
    st.markdown("#### All diagnostics for the analyzed RTL")
    st.dataframe(pd.DataFrame(unified), use_container_width=True, hide_index=True)
    st.caption("Source-level findings are heuristic. Yosys findings are tool-generated. If Yosys does not emit a source location, the line is shown as '—' and the full log below remains authoritative.")
    st.markdown("#### Optimization suggestions")
    st.dataframe(pd.DataFrame(result.get("optimization", [])), use_container_width=True, hide_index=True)
    with st.expander("Complete Yosys log", expanded=not result["ok"]):
        st.code(result.get("log", ""), language="text")
    report_text = (
        "RTL ANALYZER PRO — FULL ANALYSIS REPORT\\n"
        f"Top module: {result.get('top', 'unknown')}\\n"
        f"Yosys status: {'PASS' if result.get('ok') else 'FAIL'}\\n"
        f"RTL snapshot unchanged: {result.get('rtl_snapshot') == rtl_code}\\n\\n"
        "OPTIMIZATION SUGGESTIONS\\n"
        + "\\n".join(f"- [{x.get('Priority', 'Info')}] {x.get('Suggestion', '')}" for x in result.get("optimization", []))
        + "\\n\\nDIAGNOSTICS\\n"
        + pd.DataFrame(result.get("findings", [])).to_string(index=False)
        + "\\n\\nFULL YOSYS LOG\\n"
        + result.get("log", "")
    )
    st.download_button("Download complete analysis report", data=report_text, file_name="rtl_analysis_report.txt", mime="text/plain", key="download_main_report")

# Before/after comparison: one active editor; baseline is loaded as a file, candidate is the active editor.
st.divider(); st.subheader("5. Before-and-After Comparison")
st.write("The current editor is the 'after' design. Upload the original/baseline RTL as a file; both versions are synthesized with the same flow. This avoids creating a second editable RTL workspace.")
baseline_upload = st.file_uploader("Original / baseline Verilog (.v / .sv)", type=["v", "sv"], key="baseline_upload")
compare_button = st.button("Compare baseline against current editor", key="compare_baseline")
if compare_button:
    if baseline_upload is None:
        st.error("Upload a baseline/original Verilog file first.")
    else:
        baseline = baseline_upload.getvalue().decode("utf-8", errors="replace")
        yosys_exe = get_yosys(yosys_path)
        # Optional library file is staged to disk for the duration of the comparison.
        lib_path = None
        if lib_upload:
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".lib")
            tf.write(lib_upload.getvalue()); tf.close(); lib_path = tf.name
        baseline_modules = re.findall(r"\bmodule\s+([A-Za-z_]\w*)", re.sub(r"/\*.*?\*/|//[^\n]*", "", baseline, flags=re.S))
        if top_module and top_module not in baseline_modules:
            st.warning(f"Selected top module '{top_module}' is not present in the baseline. The baseline run will use its first declared module instead.")
        with st.spinner("Synthesizing baseline and current design with the same settings..."):
            before = run_yosys(baseline, yosys_exe, lib_path, top_module)
            after = run_yosys(rtl_code, yosys_exe, lib_path, top_module)
            sta_exe = locate_tool(opensta_path, "sta") or locate_tool(opensta_path, "opensta")
            if lib_upload and sdc_upload and sta_exe:
                before["timing"] = run_opensta(sta_exe, lib_upload.getvalue(), sdc_upload.getvalue(), before.get("netlist", ""), before.get("top", "")) if before.get("ok") else None
                after["timing"] = run_opensta(sta_exe, lib_upload.getvalue(), sdc_upload.getvalue(), after.get("netlist", ""), after.get("top", "")) if after.get("ok") else None
        if lib_path:
            try: Path(lib_path).unlink(missing_ok=True)
            except Exception: pass
        if before["ok"] and after["ok"]:
            bs, aas = before["stats"], after["stats"]
            rows = []
            for metric, key in [("Synthesized cells", "Synthesized cells"), ("Library area", "Library area")]:
                bv, av = bs.get(key), aas.get(key)
                if bv is not None and av is not None:
                    delta = av - bv
                    pct = (delta / bv * 100) if bv else None
                    rows.append({"Metric": metric, "Before": bv, "After": av, "Change": delta, "Change (%)": round(pct, 2) if pct is not None else "N/A"})
            for label, key in [("Worst reported slack", "worst_slack"), ("Reported data arrival", "arrival"), ("STA design area", "area")]:
                bt = (before.get("timing") or {}).get(key)
                at = (after.get("timing") or {}).get(key)
                if bt is not None and at is not None:
                    delta = at - bt
                    pct = (delta / abs(bt) * 100) if bt else None
                    rows.append({"Metric": label, "Before": bt, "After": at, "Change": delta, "Change (%)": round(pct, 2) if pct is not None else "N/A"})
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.warning("Synthesis succeeded, but no comparable statistics were extracted. Load a Liberty library for area and Liberty + SDC + OpenSTA for timing.")
            st.caption("Cell count is only a synthesis proxy, not physical area. Area and timing values are shown only when the target-library flow and timing engine actually report them.")
        else:
            st.error("At least one version failed synthesis. Inspect logs below.")
        with st.expander("Baseline synthesis log"):
            st.code(before.get("log", ""), language="text")
        with st.expander("Current editor synthesis log"):
            st.code(after.get("log", ""), language="text")

# Timing support is deliberately explicit: never manufacture timing numbers.
st.divider(); st.subheader("6. Timing Analysis Requirements")
st.write("For actual timing, upload a Liberty library (.lib), an SDC constraints file, and configure OpenSTA. The Full Analysis and comparison flows then run STA on the Liberty-mapped netlist. The constraints and library must match your design/technology; results are only as valid as those inputs.")
if not lib_upload:
    st.info("No Liberty library loaded: only generic synthesis counts are available, not physical area or delay.")
elif not sdc_upload:
    st.info("Liberty is loaded but SDC is missing: area may be available; meaningful timing needs clock and I/O constraints.")
elif not (locate_tool(opensta_path, "sta") or locate_tool(opensta_path, "opensta")):
    st.warning("Liberty and SDC are loaded, but OpenSTA is not found. Configure its executable path to enable STA.")



# ---------------- LOCAL AI ASSISTANCE ----------------
AI_SYSTEM_PROMPT = """You are a senior RTL design and verification engineer reviewing Verilog/SystemVerilog.
Be precise and technically specific. Find real bugs: syntax errors, width mismatches, inferred latches, missing resets,
blocking vs non-blocking misuse, multiple drivers, incomplete case/if branches, unreachable or dead logic, CDC/reset hazards,
unsynthesizable constructs and anything a synthesis tool would warn about.
Never claim RTL compiles, is functionally correct, equivalent or PPA-optimal unless a supplied tool result proves it.
Preserve the designer's intent and the module name/ports unless a port is itself the bug. If unsure, say so."""


def ask_ai(prompt, code, cfg, context="", max_tokens=4096):
    """Send a request to the configured AI provider. Returns (text, error). AI output is never treated as proof."""
    compact = bool(cfg.get("compact"))
    code_lim, ctx_lim = (12000, 5000) if compact else (30000, 14000)
    if compact:
        max_tokens = min(max_tokens, 4000)   # keeps requests inside free-tier token limits
    user_msg = f"{prompt}\n\nCurrent RTL source:\n```verilog\n{code[:code_lim]}\n```"
    if context:
        user_msg += f"\n\nTool diagnostics supplied by the app (real tool output):\n{context[-ctx_lim:]}"
    timeout = cfg.get("timeout", 120)
    provider = cfg.get("provider")
    try:
        if provider == "claude":
            if not cfg.get("key"):
                return None, "Enter your Anthropic API key in the sidebar (console.anthropic.com), or switch provider."
            payload = {"model": cfg["model"], "max_tokens": max_tokens, "system": AI_SYSTEM_PROMPT, "messages": [{"role": "user", "content": user_msg}]}
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (compatible; RTLAnalyzerAI/1.0)", "x-api-key": cfg["key"], "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        elif provider == "openai":
            if not cfg.get("key"):
                return None, "Enter the API key for your OpenAI-compatible provider in the sidebar."
            payload = {"model": cfg["model"], "max_tokens": max_tokens, "messages": [{"role": "system", "content": AI_SYSTEM_PROMPT}, {"role": "user", "content": user_msg}]}
            req = urllib.request.Request(cfg["url"] + "/chat/completions", data=json.dumps(payload).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (compatible; RTLAnalyzerAI/1.0)", "Authorization": "Bearer " + cfg["key"]})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        if not text:
            return None, "The AI responded but returned no text. Check the model name."
        return text, None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            body = ""
        hints = {401: "The API key was rejected. Re-check it.", 403: "Access denied. Check the key and model; if the error code is 1010 the request was blocked by the provider firewall.", 404: "Model or URL not found. Check the model name and base URL.",
                 413: "Request too large for the free tier. Use a shorter design or a different model.", 429: "Rate limit or quota reached. Wait a minute, or switch provider/model.", 400: "Request rejected (often model name, or no credit balance)."}
        return None, f"AI request failed (HTTP {exc.code}). {hints.get(exc.code, '')} {body}"
    except urllib.error.URLError as exc:
        return None, f"Could not reach the AI service ({cfg.get('label')}). Check your internet/URL. Details: {exc}"
    except TimeoutError:
        return None, f"The AI did not respond within {timeout} seconds. Increase the timeout in the sidebar."
    except Exception as exc:
        return None, f"AI request failed: {exc}"


def extract_json(text):
    """Tolerant JSON extraction: handles code fences, stray backslashes, control characters and, as a last resort, field-by-field salvage."""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j > i:
            t = t[i:j + 1]
    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", t)   # double backslashes that are not valid JSON escapes
    for cand in (t, fixed):
        try:
            return json.loads(cand, strict=False)
        except Exception:
            pass
    # Salvage: pull the known fields out individually.
    def field(name):
        mm = re.search(r'"' + name + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', fixed, re.S)
        if not mm:
            return ""
        try:
            return json.loads('"' + mm.group(1) + '"', strict=False)
        except Exception:
            return mm.group(1).replace("\\n", "\n").replace('\\"', '"')
    issues = []
    for om in re.finditer(r"\{[^{}]*\}", fixed):
        try:
            d = json.loads(om.group(0), strict=False)
            if isinstance(d, dict) and "title" in d:
                issues.append(d)
        except Exception:
            pass
    if field("summary") or field("fixed_rtl") or issues:
        return {"summary": field("summary"), "issues": issues, "fixed_rtl": field("fixed_rtl")}
    return None


SMART_TASK = """Do a thorough error review of this RTL. Use the real tool output below (quick source check + Yosys result) as evidence, and also find problems the tools cannot see.
Respond with ONLY one JSON object, no prose outside it, in exactly this shape:
{"summary": "2-3 sentence overall assessment",
 "issues": [{"line": <int or null>, "severity": "ERROR|WARNING|INFO", "title": "short title", "explanation": "why it is a problem", "fix": "concrete fix"}],
 "fixed_rtl": "the COMPLETE corrected Verilog source (all modules), or an empty string if nothing needs fixing"}
Order issues by severity. Only report real, specific problems that cause wrong behavior, synthesis problems or likely bugs. Do NOT report style preferences such as default_nettype, timescale, explicit wire/logic types or naming unless they cause an actual bug. If the design is correct, return an empty issues list and an empty fixed_rtl string. Keep module names and port lists unless a port is itself the bug.\nJSON rules: inside JSON strings never use backslashes except \\n for newlines and \\" for quotes, and do not use backticks."""


def smart_debug(rtl, top, yosys_cmd, cfg):
    """AI-assisted error detection grounded in real tool output, with Yosys-verified self-repair of the proposed fix."""
    quick = live_diagnostics(rtl)
    quick_txt = "\n".join(f"line {r['Line']} [{r['Severity']}] {r['Finding']}" for r in quick)
    syn = run_yosys(rtl, yosys_cmd, None, top) if yosys_cmd else None
    if syn:
        ctx = f"QUICK SOURCE CHECK:\n{quick_txt}\n\nYOSYS RESULT: {'PASS' if syn['ok'] else 'FAIL'}\nYOSYS STATS: {syn.get('stats')}\nYOSYS LOG (tail):\n{syn['log'][-6000:]}"
    else:
        ctx = f"QUICK SOURCE CHECK:\n{quick_txt}\n\nYosys was not available, so no synthesis result exists."
    raw, err = ask_ai(SMART_TASK, rtl, cfg, context=ctx, max_tokens=8000)
    if err:
        return {"error": err}
    data = extract_json(raw)
    if not isinstance(data, dict):
        return {"raw": raw, "original_synthesis": syn}
    fixed = (data.get("fixed_rtl") or "").strip()
    fixed_syn, rounds = None, 0
    if fixed and yosys_cmd:
        for round_no in range(3):
            fixed_syn = run_yosys(fixed, yosys_cmd, None, top)
            if fixed_syn["ok"] or round_no == 2:
                break
            raw2, err2 = ask_ai("Your corrected RTL below FAILED Yosys. Fix every reported error and return the same JSON format.", fixed, cfg,
                                context="YOSYS ERRORS:\n" + fixed_syn["log"][-5000:], max_tokens=8000)
            if err2:
                break
            d2 = extract_json(raw2)
            new_fixed = ((d2 or {}).get("fixed_rtl") or "").strip()
            if not new_fixed:
                break
            fixed, rounds = new_fixed, rounds + 1
    return {"summary": data.get("summary", ""), "issues": data.get("issues") or [], "fixed_rtl": fixed,
            "fixed_synthesis": fixed_syn, "repair_rounds": rounds, "original_synthesis": syn, "raw": raw}


def run_equivalence(reference, candidate, yosys_exe, timeout=180):
    """Compare two single-top designs using Yosys equiv_* commands after separate validation."""
    if not reference.strip() or not candidate.strip():
        return {"status": "NOT RUN", "log": "Both reference and candidate RTL are required."}
    if not yosys_exe:
        return {"status": "NOT RUN", "log": "No working Yosys was found. Use the sidebar to install the built-in Yosys."}
    def module_names(src):
        return re.findall(r"\bmodule\s+([A-Za-z_]\w*)", strip_comments(src))
    rmods, cmods = module_names(reference), module_names(candidate)
    if len(rmods) != 1 or len(cmods) != 1:
        return {"status": "NOT RUN", "log": "This checker currently expects exactly one module in each design. Flatten or isolate the intended top module first."}
    with tempfile.TemporaryDirectory(prefix="rtl_equiv_") as td:
        work = Path(td); rf = work / "reference.v"; cf = work / "candidate.v"
        rf.write_text(reference, encoding="utf-8"); cf.write_text(candidate, encoding="utf-8")
        logs=[]
        try:
            for label, vf in [("REFERENCE", rf), ("CANDIDATE", cf)]:
                cmd = f'read_verilog -sv {vf.name}; hierarchy -check -top {rmods[0] if label == "REFERENCE" else cmods[0]}; proc; check'
                res = subprocess.run([*_as_cmd(yosys_exe), "-p", cmd], cwd=str(work), capture_output=True, text=True, timeout=timeout, errors="replace")
                log = res.stdout + "\n" + res.stderr
                logs.append(f"===== {label} VALIDATION (exit {res.returncode}) =====\n{log}")
                if res.returncode != 0 or re.search(r"\bERROR:\s", log, re.I):
                    return {"status": "INVALID INPUT", "log": "\n\n".join(logs) + "\n\nEquivalence was not run because validation failed."}
            # Lower behavioral RTL before building the equivalence miter. Without
            # proc/opt here, behavioral always blocks can leave processes in the
            # design and cause the proof flow to fail before comparing logic.
            cmd = (f'read_verilog -sv {rf.name}; proc; opt; rename {rmods[0]} gold; '
                   f'read_verilog -sv {cf.name}; proc; opt; rename {cmods[0]} gate; '
                   'equiv_make gold gate equiv; hierarchy -top equiv; equiv_simple; equiv_status -assert')
            res = subprocess.run([*_as_cmd(yosys_exe), "-p", cmd], cwd=str(work), capture_output=True, text=True, timeout=timeout, errors="replace")
            elog = res.stdout + "\n" + res.stderr
            logs.append("===== FORMAL EQUIVALENCE =====\n" + elog)
            if res.returncode == 0 and re.search(r"Equivalence successfully proven", elog, re.I):
                status = "PROVEN EQUIVALENT"
            elif re.search(r"unproven|not proven|Equivalence check failed", elog, re.I):
                status = "NOT PROVEN / DIFFERENT"
            else:
                status = "INCONCLUSIVE"
            return {"status": status, "log": "\n\n".join(logs)}
        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "log": "Yosys equivalence check timed out.\n\n" + "\n\n".join(logs)}
        except Exception as exc:
            return {"status": "ERROR", "log": f"Equivalence check failed to execute: {exc}\n\n" + "\n\n".join(logs)}


# ---------------- AI SMART DEBUG (rendered at top of page) ----------------
with ai_top:
    st.header("🧠 AI Smart Debug: analyze, explain and get the corrected version")
    if not ai_cfg.get("key"):
        st.warning("Add your free AI key in the sidebar to start. Easiest: open console.groq.com/keys, sign up with an email, click Create API Key, and paste it into the sidebar. No credit card needed.")
    st.write("The AI reads your RTL together with the real quick-check and Yosys output, lists every problem it finds, proposes a corrected design, and then Yosys re-checks that fix automatically (retrying if the fix still fails).")

    def send_fix_to_candidate():
        sd = st.session_state.get("smart_debug") or {}
        if sd.get("fixed_rtl"):
            st.session_state["ai_candidate_rtl"] = sd["fixed_rtl"] + "\n"
            st.session_state["ai_candidate_verification"] = None

    def apply_fix_to_editor():
        sd = st.session_state.get("smart_debug") or {}
        if sd.get("fixed_rtl"):
            st.session_state["rtl_editor_value"] = sd["fixed_rtl"] + "\n"
            st.session_state["analysis_result"] = None
            st.session_state["last_analyzed_rtl"] = None

    if st.button("🧠 Smart Debug: find and fix errors with AI", type="primary", use_container_width=True, key="run_smart_debug"):
        with st.spinner(f"Running Yosys, then asking {ai_cfg['label']} to review and fix the design..."):
            sd = smart_debug(rtl_code, top_module, get_yosys(yosys_path), ai_cfg)
        sd["snapshot"] = rtl_code
        st.session_state["smart_debug"] = sd

    sd = st.session_state.get("smart_debug")
    if sd:
        if sd.get("error"):
            st.error(sd["error"])
        else:
            if sd.get("snapshot") != rtl_code:
                st.warning("The editor changed since this review. Run Smart Debug again for the current RTL.")
            osyn = sd.get("original_synthesis")
            if osyn is not None:
                st.caption("Original design under Yosys: " + ("PASS" if osyn.get("ok") else "FAIL"))
            if "issues" not in sd:
                st.warning("The AI did not return structured JSON. Raw response:")
                st.markdown(sd.get("raw", ""))
            else:
                st.info(sd.get("summary") or "No summary returned.")
                issues = sd.get("issues", [])
                if issues:
                    df_issues = pd.DataFrame(issues).reindex(columns=["line", "severity", "title", "explanation", "fix"]).fillna("")
                    df_issues["line"] = df_issues["line"].astype(str)
                    st.dataframe(df_issues, use_container_width=True, hide_index=True)
                else:
                    st.success("The AI found no specific problems. This is an opinion, not proof; rely on Yosys and equivalence results.")
                if sd.get("fixed_rtl"):
                    fs = sd.get("fixed_synthesis")
                    if fs is not None and fs.get("ok"):
                        st.success("Proposed fix passes Yosys parse, hierarchy check, synthesis and structural checks" + (f" (after {sd['repair_rounds']} automatic repair round(s))." if sd.get("repair_rounds") else "."))
                    elif fs is not None:
                        st.error("The proposed fix still fails Yosys after automatic repair attempts. Review the log before using it.")
                    else:
                        st.warning("Yosys was unavailable, so the proposed fix could not be machine-checked.")
                    st.code(sd["fixed_rtl"], language="verilog")
                    st.download_button("Download corrected Verilog (.v)", data=sd["fixed_rtl"] + "\n", file_name="corrected.v", mime="text/plain", key="dl_fixed_rtl")
                    st.caption("Bug fixes intentionally change behavior, so a formal equivalence check against the original is expected to report a difference. Judge the fix by the Yosys result and by your design intent.")
                    f1, f2 = st.columns(2)
                    f1.button("Apply fix to main RTL editor", on_click=apply_fix_to_editor, use_container_width=True, key="apply_smart_fix")
                    f2.button("Send fix to candidate box (section 8)", on_click=send_fix_to_candidate, use_container_width=True, key="send_smart_fix")
                    if fs is not None:
                        with st.expander("Yosys log for the proposed fix"):
                            st.code(fs.get("log", ""), language="text")
                with st.expander("Raw AI response"):
                    st.code(sd.get("raw", ""), language="json")

    st.divider()

# ---------------- AI ASSISTANT PANEL ----------------
st.divider()
st.header("7. AI RTL Assistant (chat)")
st.write("Ask questions about the active editor, request a walkthrough, or ask for candidate improvements. The model runs through the provider chosen in the sidebar; AI advice is not a compiler or a proof.")
ai_question = st.text_area("Ask about this RTL", value="Review this RTL for readability, likely bugs, and safe optimization opportunities. Explain each point and do not claim correctness without tool evidence.", height=100, key="ai_question")
ai_col1, ai_col2 = st.columns([1, 2])
with ai_col1:
    ask_ai_clicked = st.button("Ask AI about current RTL", type="primary", use_container_width=True)
with ai_col2:
    st.caption(f"Configured AI: `{ai_cfg['label']}` (change in the sidebar).")
if ask_ai_clicked:
    with st.spinner(f"Waiting for {ai_cfg['label']}..."):
        answer, ai_error = ask_ai(ai_question, rtl_code, ai_cfg)
    if ai_error:
        st.error(ai_error)
    else:
        st.session_state["rtl_ai_answer"] = answer
        st.session_state["rtl_ai_source"] = rtl_code
if st.session_state.get("rtl_ai_answer"):
    if st.session_state.get("rtl_ai_source") != rtl_code:
        st.warning("The RTL editor has changed since this AI response. Ask again to review the current version.")
    st.markdown(st.session_state["rtl_ai_answer"])
    st.download_button("Download AI review", data=st.session_state["rtl_ai_answer"], file_name="rtl_ai_review.md", mime="text/markdown", key="download_ai_review")

# ---------------- AI-GENERATED OPTIMIZATION CANDIDATE ----------------
st.divider()
st.header("8. AI Optimization Candidate — Generate, Validate, Compare")
st.write("Ask the AI to propose a complete candidate RTL implementation. The candidate is kept separate from the active editor until you review it. Yosys validation, synthesis, and formal equivalence are run separately; AI output is never treated as proof.")

if "ai_candidate_rtl" not in st.session_state:
    st.session_state["ai_candidate_rtl"] = ""
if "ai_candidate_explanation" not in st.session_state:
    st.session_state["ai_candidate_explanation"] = ""
if "ai_candidate_verification" not in st.session_state:
    st.session_state["ai_candidate_verification"] = None

opt_goal = st.text_input(
    "Optimization goal",
    value="Improve clarity and synthesis efficiency without changing the design's behavior. Avoid speculative micro-optimizations.",
    key="ai_opt_goal",
)
if st.button("Generate AI Optimization Candidate", type="primary", use_container_width=True, key="generate_ai_candidate"):
    strict_prompt = (
        "Propose a conservative Verilog RTL optimization candidate. "
        "Return exactly one complete synthesizable module in a single ```verilog code block, "
        "then a short explanation outside the code block. Preserve module name, ports, widths, "
        "reset behavior, latency, and cycle-by-cycle behavior. Do not invent constraints or claim "
        "PPA improvement without measured tool results. If no safe improvement is evident, return "
        "the original RTL unchanged and say why. Optimization goal: " + opt_goal
    )
    with st.spinner(f"Generating candidate with {ai_cfg['label']}…"):
        ai_text, ai_err = ask_ai(strict_prompt, rtl_code, ai_cfg, max_tokens=8000)
    if ai_err:
        st.error(ai_err)
    else:
        code_blocks = re.findall(r"```(?:verilog|systemverilog|sv)?\s*\n(.*?)```", ai_text, flags=re.I | re.S)
        candidate = code_blocks[0].strip() if code_blocks else ""
        if not candidate or not re.search(r"\bmodule\s+[A-Za-z_]\w*", strip_comments(candidate)):
            st.error("The AI response did not contain a complete fenced Verilog module. No candidate was applied. Review the raw response below and retry with a clearer prompt.")
            st.session_state["ai_candidate_explanation"] = ai_text
        else:
            st.session_state["ai_candidate_rtl"] = candidate + "\n"
            st.session_state["ai_candidate_explanation"] = ai_text
            st.session_state["ai_candidate_verification"] = None

if st.session_state.get("ai_candidate_explanation"):
    with st.expander("AI candidate explanation / raw response", expanded=False):
        st.markdown(st.session_state["ai_candidate_explanation"])

candidate_rtl = st.text_area(
    "AI candidate RTL (review/edit before checking)",
    key="ai_candidate_rtl",
    height=260,
    help="This is a review candidate, not the active design. It is not accepted as correct until tool checks finish.",
)
opt_col1, opt_col2 = st.columns(2)
with opt_col1:
    verify_candidate = st.button("Validate + Synthesize + Prove Equivalence", use_container_width=True, key="verify_ai_candidate")
def apply_ai_candidate_to_editor():
    candidate = st.session_state.get("ai_candidate_rtl", "")
    if candidate.strip():
        # Streamlit callbacks execute before the next script run, so the keyed editor can be updated safely.
        st.session_state["rtl_editor_value"] = candidate
        st.session_state["analysis_result"] = None
        st.session_state["last_analyzed_rtl"] = None

with opt_col2:
    st.button("Apply candidate to main RTL editor", on_click=apply_ai_candidate_to_editor, use_container_width=True, key="apply_ai_candidate")

if verify_candidate:
    if not candidate_rtl.strip():
        st.error("Generate or paste a candidate first.")
    else:
        yexe = get_yosys(yosys_path)
        with st.spinner("Running independent Yosys validation, synthesis and formal comparison…"):
            cand_synth = run_yosys(candidate_rtl, yexe, None, None)
            eq_result = run_equivalence(rtl_code, candidate_rtl, yexe)
        st.session_state["ai_candidate_verification"] = {
            "candidate_synthesis": cand_synth,
            "equivalence": eq_result,
            "reference_snapshot": rtl_code,
            "candidate_snapshot": candidate_rtl,
        }

verification = st.session_state.get("ai_candidate_verification")
if verification:
    if verification.get("reference_snapshot") != rtl_code or verification.get("candidate_snapshot") != candidate_rtl:
        st.warning("One of the designs changed since verification. Re-run validation and equivalence before relying on these results.")
    cs = verification["candidate_synthesis"]
    eq = verification["equivalence"]
    vc1, vc2, vc3 = st.columns(3)
    vc1.metric("Candidate Yosys", "PASS" if cs.get("ok") else "FAIL")
    vc2.metric("Equivalence", eq.get("status", "UNKNOWN"))
    old_result = st.session_state.get("analysis_result")
    old_cells = (old_result or {}).get("stats", {}).get("Synthesized cells")
    new_cells = cs.get("stats", {}).get("Synthesized cells")
    vc3.metric("Cells: analyzed original → candidate", f"{old_cells} → {new_cells}" if old_cells is not None and new_cells is not None else "N/A")
    if eq.get("status") == "PROVEN EQUIVALENT" and cs.get("ok"):
        st.success("Candidate passed Yosys synthesis and the configured formal equivalence flow. Review metrics and logs before adopting it.")
    elif eq.get("status") == "NOT PROVEN / DIFFERENT":
        st.error("Equivalence was not proven. Do not accept this candidate as a behavior-preserving optimization.")
    else:
        st.warning("Candidate is not fully verified. A successful parse/synthesis alone does not prove equivalence.")
    if old_cells is not None and new_cells is not None:
        st.metric("Generic synthesized cell-count change", f"{new_cells - old_cells:+d}", delta=f"{((new_cells-old_cells)/old_cells*100):+.2f}%" if old_cells else None, delta_color="inverse")
        st.caption("This compares generic synthesized cell counts only. It is not a physical-area or timing measurement. Run the target-library flow for comparable PPA metrics.")
    with st.expander("Candidate Yosys synthesis log"):
        st.code(cs.get("log", ""), language="text")
    with st.expander("Candidate formal equivalence log"):
        st.code(eq.get("log", ""), language="text")
    st.download_button("Download candidate verification bundle", data=("CANDIDATE RTL\n" + verification.get("candidate_snapshot", "") + "\n\nSYNTHESIS LOG\n" + cs.get("log", "") + "\n\nEQUIVALENCE STATUS: " + eq.get("status", "UNKNOWN") + "\n\nEQUIVALENCE LOG\n" + eq.get("log", "")), file_name="ai_candidate_verification.txt", mime="text/plain", key="download_candidate_verification")

# ---------------- FORMAL EQUIVALENCE PANEL ----------------
st.divider()
st.header("9. Formal Equivalence Verification")
st.write("Upload the original/reference design. The active editor is the candidate. Yosys performs the comparison; the AI model is not involved in the proof.")
reference_upload = st.file_uploader("Reference/original RTL for equivalence (.v / .sv)", type=["v", "sv"], key="formal_reference_upload")
if reference_upload:
    reference_code = reference_upload.getvalue().decode("utf-8", errors="replace")
else:
    reference_code = ""
if st.button("Run Formal Equivalence Check", type="primary", use_container_width=True, key="run_formal_equiv"):
    with st.spinner("Validating both designs and running Yosys equivalence commands..."):
        eq = run_equivalence(reference_code, rtl_code, get_yosys(yosys_path))
    st.session_state["formal_equiv_result"] = eq
    st.session_state["formal_equiv_reference"] = reference_code
    st.session_state["formal_equiv_candidate"] = rtl_code
if st.session_state.get("formal_equiv_result"):
    eq = st.session_state["formal_equiv_result"]
    if st.session_state.get("formal_equiv_candidate") != rtl_code:
        st.warning("Candidate RTL has changed since this equivalence result. Re-run the proof before relying on it.")
    if eq["status"] == "PROVEN EQUIVALENT":
        st.success("Yosys reports that equivalence was successfully proven for the compared designs.")
    elif eq["status"] in ("NOT PROVEN / DIFFERENT", "INVALID INPUT"):
        st.error(f"Equivalence status: {eq['status']}")
    else:
        st.warning(f"Equivalence status: {eq['status']}")
    st.code(eq["log"], language="text")
    st.download_button("Download formal verification log", data=eq["log"], file_name="formal_equivalence_report.txt", mime="text/plain", key="download_formal_equiv")

# ---------------- CONSOLIDATED ENGINEERING REPORT ----------------
st.divider()
st.header("10. Consolidated Engineering Report")
st.write("Create one report with the current RTL, quick diagnostics, latest Yosys analysis, AI review if available, and formal-equivalence status if run.")
if st.button("Generate Consolidated Report", use_container_width=True, key="generate_consolidated_report"):
    report = [
        "RTL ANALYZER PRO — CONSOLIDATED ENGINEERING REPORT",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Selected top module: {top_module or 'Not detected'}",
        "", "=== RTL SOURCE ===", rtl_code,
        "", "=== QUICK DIAGNOSTICS ===", pd.DataFrame(live_diagnostics(rtl_code)).to_string(index=False),
    ]
    latest = st.session_state.get("analysis_result")
    if latest:
        report += ["", "=== YOSYS ANALYSIS ===", f"Status: {'PASS' if latest.get('ok') else 'FAIL'}", f"Top: {latest.get('top', 'unknown')}", str(latest.get('stats', {})), "", latest.get('log', '')]
        report += ["", "=== OPTIMIZATION SUGGESTIONS ===", "\n".join(f"[{x.get('Priority')}] {x.get('Suggestion')}" for x in latest.get('optimization', []))]
        if latest.get("timing"):
            report += ["", "=== OPENSTA TIMING ===", str({k:v for k,v in latest['timing'].items() if k != 'log'}), latest['timing'].get('log', '')]
    if st.session_state.get("rtl_ai_answer"):
        report += ["", "=== AI REVIEW (ADVISORY ONLY) ===", st.session_state["rtl_ai_answer"]]
    if st.session_state.get("formal_equiv_result"):
        eq = st.session_state["formal_equiv_result"]
        report += ["", "=== FORMAL EQUIVALENCE ===", f"Status: {eq.get('status')}", eq.get("log", "")]
    if st.session_state.get("ai_candidate_verification"):
        cv = st.session_state["ai_candidate_verification"]
        report += ["", "=== AI CANDIDATE VERIFICATION ===", f"Candidate Yosys status: {'PASS' if cv['candidate_synthesis'].get('ok') else 'FAIL'}", f"Equivalence status: {cv['equivalence'].get('status')}", "Candidate RTL:", cv.get("candidate_snapshot", ""), "Candidate synthesis log:", cv["candidate_synthesis"].get("log", ""), "Equivalence log:", cv["equivalence"].get("log", "")]
    report += ["", "=== LIMITATIONS ===", "Quick diagnostics and AI comments are advisory. Yosys/OpenSTA results depend on tool version, design, target library, and constraints. A result marked inconclusive is not a proof of equivalence."]
    st.session_state["consolidated_report"] = "\n".join(report)
    st.success("Consolidated report prepared.")
if st.session_state.get("consolidated_report"):
    st.download_button("Download consolidated report (.txt)", data=st.session_state["consolidated_report"], file_name="rtl_analyzer_consolidated_report.txt", mime="text/plain", key="download_consolidated_report")
    with st.expander("Preview consolidated report"):
        st.text(st.session_state["consolidated_report"][:20000])


st.divider()
st.caption("Correctness authority: Yosys tool results and logs, not the AI assistant. Quick diagnostics and optimization suggestions are rule-based hints. Physical area and timing depend on the target library, constraints, synthesis flow, and timing engine.")
