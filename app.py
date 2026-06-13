import streamlit as st
import subprocess
import threading
import queue
import os
import yaml
import time
import shutil
import zipfile
import io
from pathlib import Path
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ybyra GUI",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap');

:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #22263a;
  --border: #2e3354;
  --primary: #4f8ef7;
  --success: #3ecf8e;
  --warning: #f5a623;
  --error: #e05c5c;
  --text: #e8eaf2;
  --muted: #8b90ab;
  --font: 'Satoshi', 'Inter', sans-serif;
}

* { font-family: var(--font) !important; }

.stApp { background: var(--bg); }

[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border);
}

.block-container { padding-top: 1.5rem !important; max-width: 1100px; }

/* Cards */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1rem;
}
.card-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 0.6rem;
}

/* Status badges */
.badge {
  display: inline-block;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
}
.badge-idle    { background: #2e3354; color: var(--muted); }
.badge-running { background: #1a3a5c; color: #5ab5ff; }
.badge-done    { background: #0f3324; color: var(--success); }
.badge-error   { background: #3a1515; color: var(--error); }

/* Log box */
.log-box {
  background: #0a0c12;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
  font-size: 0.78rem;
  color: #c8d0e8;
  height: 320px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.55;
}

/* Haplogroup result pill */
.hap-pill {
  display: inline-block;
  background: linear-gradient(135deg, #1a3a5c, #0f2040);
  border: 1px solid #3a72d4;
  border-radius: 8px;
  padding: 0.5rem 1.1rem;
  font-size: 1rem;
  font-weight: 700;
  color: #7ec8ff;
  margin: 0.25rem;
}

/* Divider */
hr { border-color: var(--border) !important; margin: 1.25rem 0; }

/* Metric overrides */
[data-testid="metric-container"] {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem 1rem;
}
</style>
""", unsafe_allow_html=True)

# ── State init ────────────────────────────────────────────────────────────────
for key, default in {
    "log_lines": [],
    "run_status": "idle",   # idle | running | done | error
    "process": None,
    "results": [],
    "workdir": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Helpers ───────────────────────────────────────────────────────────────────
def snakemake_installed():
    return shutil.which("snakemake") is not None

def conda_installed():
    return shutil.which("conda") is not None or shutil.which("mamba") is not None

def ybyra_cloned():
    return Path("ybyra/Snakefile").exists()

def status_badge(status):
    labels = {"idle": "⬤ Idle", "running": "⬤ Running", "done": "⬤ Done", "error": "⬤ Error"}
    css    = {"idle": "badge-idle", "running": "badge-running", "done": "badge-done", "error": "badge-error"}
    return f'<span class="badge {css[status]}">{labels[status]}</span>'

def save_uploaded_file(uploaded, dest_dir):
    dest = Path(dest_dir) / uploaded.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(uploaded.read())
    return str(dest)

def build_config(samples_dict, reference, phylotree, min_snps, outdir):
    return {
        "samples": samples_dict,
        "reference": reference,
        "phylotree": phylotree,
        "min_snps": min_snps,
        "outdir": outdir,
    }

def stream_process(proc, log_list):
    for line in iter(proc.stdout.readline, ""):
        log_list.append(line.rstrip())
    proc.stdout.close()
    proc.wait()

def zip_results(outdir):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in Path(outdir).rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(outdir))
    buf.seek(0)
    return buf

def parse_results_tsv(outdir):
    rows = []
    for tsv in Path(outdir).rglob("*.tsv"):
        try:
            import csv
            with open(tsv) as fh:
                reader = csv.DictReader(fh, delimiter="\t")
                for row in reader:
                    rows.append(dict(row))
        except Exception:
            pass
    return rows

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧬 ybyra GUI")
    st.caption("Y-chromosome haplogroup calling · Snakemake workflow")
    st.divider()

    # Environment check
    st.markdown("**Environment**")
    sm_ok  = snakemake_installed()
    cnd_ok = conda_installed()
    yby_ok = ybyra_cloned()

    col1, col2 = st.columns(2)
    col1.metric("Snakemake", "✅" if sm_ok  else "❌")
    col2.metric("Conda",     "✅" if cnd_ok else "❌")
    st.metric("ybyra repo", "✅ Found" if yby_ok else "❌ Not found", label_visibility="visible")

    if not yby_ok:
        st.info("Clone ybyra:
```bash
git clone https://github.com/tpinotti/ybyra
```")

    st.divider()

    # Snakemake options
    st.markdown("**Snakemake options**")
    cores      = st.slider("Cores (--cores)", 1, 32, 4)
    use_conda  = st.toggle("--use-conda", value=True)
    dry_run    = st.toggle("Dry-run (-n)", value=False)
    forceall   = st.toggle("Force re-run (--forceall)", value=False)

    st.divider()
    st.caption(f"Session: {datetime.now():%Y-%m-%d %H:%M}")

# ── Main layout ───────────────────────────────────────────────────────────────
st.markdown("# 🧬 ybyra · Graphical Interface")
st.markdown(
    "Automated **Y-chromosome haplogroup assignment** using a tree-based scoring method. "
    "[GitHub →](https://github.com/tpinotti/ybyra){target='_blank'}",
    unsafe_allow_html=False,
)

tab_config, tab_run, tab_results = st.tabs(["⚙️ Configuration", "▶️ Run", "📊 Results"])

# ═══════════════════════════════ TAB 1 — CONFIG ═══════════════════════════════
with tab_config:
    st.markdown('<div class="card"><div class="card-title">Reference & Phylotree</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        ref_path = st.text_input(
            "Reference genome (FASTA)",
            value="resources/hs37d5.fa",
            help="Path to the indexed reference FASTA file.",
        )
    with col_b:
        phylotree_path = st.text_input(
            "Phylotree (Newick/TSV)",
            value="resources/phylotree.nwk",
            help="Phylogenetic tree file used for SNP scoring.",
        )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="card-title">Samples</div>', unsafe_allow_html=True)

    method = st.radio("Input method", ["Manual entry", "Upload BAM files", "Upload sample TSV"], horizontal=True)

    samples_dict = {}

    if method == "Manual entry":
        st.caption("Enter one sample per line: `sample_name  /path/to/file.bam`")
        raw_text = st.text_area(
            "Samples",
            value="sample_A\tdata/sample_A.bam
sample_B\tdata/sample_B.bam",
            height=140,
            label_visibility="collapsed",
        )
        for line in raw_text.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                samples_dict[parts[0]] = parts[1]

    elif method == "Upload BAM files":
        uploaded_bams = st.file_uploader(
            "Upload BAM files (+ .bai indices)",
            type=["bam", "bai", "cram"],
            accept_multiple_files=True,
        )
        if uploaded_bams:
            upload_dir = Path("ybyra_uploads")
            for ub in uploaded_bams:
                saved = save_uploaded_file(ub, upload_dir)
                if ub.
