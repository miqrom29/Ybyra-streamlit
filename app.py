
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

# â”€â”€ Page config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.set_page_config(
    page_title="ybyra GUI",
    page_icon="ðŸ§¬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# â”€â”€ Custom CSS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown("""
<style>
@import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap');

:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #22263a;
  --border: #2e3354;
  --primary: #4f8ef7;
  --primary-dark: #3a72d4;
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

# â”€â”€ State init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
for key, default in {
    "log_lines": [],
    "run_status": "idle",   # idle | running | done | error
    "process": None,
    "results": [],
    "workdir": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def snakemake_installed():
    return shutil.which("snakemake") is not None

def conda_installed():
    return shutil.which("conda") is not None or shutil.which("mamba") is not None

def ybyra_cloned():
    return Path("ybyra/Snakefile").exists()

def status_badge(status):
    labels = {"idle": "â¬¤ Idle", "running": "â¬¤ Running", "done": "â¬¤ Done", "error": "â¬¤ Error"}
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
    """Try to read any *haplogroup*.tsv or results*.tsv from output dir."""
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

# â”€â”€ Sidebar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
with st.sidebar:
    st.markdown("## ðŸ§¬ ybyra GUI")
    st.caption("Y-chromosome haplogroup calling Â· Snakemake workflow")
    st.divider()

    # Environment check
    st.markdown("**Environment**")
    sm_ok  = snakemake_installed()
    cnd_ok = conda_installed()
    yby_ok = ybyra_cloned()

    col1, col2 = st.columns(2)
    col1.metric("Snakemake", "âœ…" if sm_ok  else "âŒ")
    col2.metric("Conda",     "âœ…" if cnd_ok else "âŒ")
    st.metric("ybyra repo", "âœ… Found" if yby_ok else "âŒ Not found", label_visibility="visible")

        if not yby_ok:
        st.info("""Clone ybyra:
```bash
git clone https://github.com/tpinotti/ybyra
```""")
```
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

# â”€â”€ Main layout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown("# ðŸ§¬ ybyra Â· Graphical Interface")
st.markdown(
    "Automated **Y-chromosome haplogroup assignment** using a tree-based scoring method. "
    "[GitHub â†’](https://github.com/tpinotti/ybyra){target='_blank'}",
    unsafe_allow_html=False,
)

tab_config, tab_run, tab_results = st.tabs(["âš™ï¸ Configuration", "â–¶ï¸ Run", "ðŸ“Š Results"])

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• TAB 1 â€” CONFIG â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
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
            value="sample_A\tdata/sample_A.bam\nsample_B\tdata/sample_B.bam",
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
                if ub.name.endswith(".bam"):
                    samples_dict[Path(ub.name).stem] = saved
            st.success(f"{len(samples_dict)} BAM file(s) ready.")

    else:  # TSV
        tsv_file = st.file_uploader("Upload sample TSV (sample_name \t path_to_bam)", type=["tsv", "txt"])
        if tsv_file:
            import csv, io as _io
            content = tsv_file.read().decode()
            for row in csv.reader(_io.StringIO(content), delimiter="\t"):
                if len(row) >= 2:
                    samples_dict[row[0]] = row[1]
            st.success(f"{len(samples_dict)} sample(s) parsed.")

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="card-title">Parameters</div>', unsafe_allow_html=True)
    col_p1, col_p2, col_p3 = st.columns(3)
    min_snps = col_p1.number_input("Min. SNPs for calling", min_value=1, max_value=500, value=10)
    outdir   = col_p2.text_input("Output directory", value="results/ybyra")
    col_p3.markdown("<br>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Preview config YAML
    if st.toggle("Preview config.yaml", value=False):
        cfg = build_config(samples_dict, ref_path, phylotree_path, min_snps, outdir)
        st.code(yaml.dump(cfg, default_flow_style=False), language="yaml")

    # Save config button
    if st.button("ðŸ’¾ Save config.yaml", use_container_width=True, type="primary"):
        cfg = build_config(samples_dict, ref_path, phylotree_path, min_snps, outdir)
        cfg_path = Path("ybyra/config/config.yaml")
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg_path, "w") as fh:
            yaml.dump(cfg, fh, default_flow_style=False)
        st.session_state["workdir"] = str(Path("ybyra").resolve())
        st.success(f"Saved â†’ `{cfg_path}`")

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• TAB 2 â€” RUN â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab_run:
    col_stat, col_btn = st.columns([2, 1])
    with col_stat:
        st.markdown(
            f"**Status:** {status_badge(st.session_state['run_status'])}",
            unsafe_allow_html=True,
        )
    with col_btn:
        run_btn  = st.button("â–¶ Run ybyra",  type="primary",   use_container_width=True,
                             disabled=(st.session_state["run_status"] == "running"))
        stop_btn = st.button("â¹ Stop",       type="secondary", use_container_width=True,
                             disabled=(st.session_state["run_status"] != "running"))

    st.divider()

    # Build command preview
    workdir = st.session_state.get("workdir") or "ybyra"
    cmd_parts = ["snakemake", "--cores", str(cores)]
    if use_conda:  cmd_parts.append("--use-conda")
    if dry_run:    cmd_parts.append("-n")
    if forceall:   cmd_parts.append("--forceall")
    cmd_parts += ["--snakefile", "Snakefile", "--configfile", "config/config.yaml"]

    st.code(" ".join(cmd_parts), language="bash")

    # RUN logic
    if run_btn:
        if not ybyra_cloned():
            st.error("âŒ ybyra repository not found. Clone it first:
```
git clone https://github.com/tpinotti/ybyra
```")
        else:
            st.session_state["log_lines"] = []
            st.session_state["run_status"] = "running"
            try:
                proc = subprocess.Popen(
                    cmd_parts,
                    cwd=workdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                st.session_state["process"] = proc
                t = threading.Thread(
                    target=stream_process,
                    args=(proc, st.session_state["log_lines"]),
                    daemon=True,
                )
                t.start()
            except FileNotFoundError:
                st.session_state["run_status"] = "error"
                st.session_state["log_lines"].append("ERROR: snakemake not found in PATH.")

    if stop_btn and st.session_state["process"]:
        st.session_state["process"].terminate()
        st.session_state["run_status"] = "error"
        st.session_state["log_lines"].append("â¹ Process terminated by user.")

    # Update status from process
    proc = st.session_state.get("process")
    if proc and st.session_state["run_status"] == "running":
        ret = proc.poll()
        if ret is not None:
            st.session_state["run_status"] = "done" if ret == 0 else "error"
            if ret == 0:
                st.session_state["results"] = parse_results_tsv(outdir)

    # Live log display
    st.markdown("**Live log**")
    log_text = "\n".join(st.session_state["log_lines"][-200:]) or "(No output yet â€” press â–¶ Run ybyra)"
    st.markdown(f'<div class="log-box">{log_text}</div>', unsafe_allow_html=True)

    if st.session_state["run_status"] == "running":
        st.info("â³ Workflow runningâ€¦ refresh to update log.")
        time.sleep(0.5)
        st.rerun()

    # Download results ZIP
    if st.session_state["run_status"] == "done":
        st.success("âœ… Workflow completed successfully!")
        if Path(outdir).exists():
            zip_buf = zip_results(outdir)
            st.download_button(
                "â¬‡ï¸ Download results (ZIP)",
                data=zip_buf,
                file_name=f"ybyra_results_{datetime.now():%Y%m%d_%H%M%S}.zip",
                mime="application/zip",
                use_container_width=True,
            )

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• TAB 3 â€” RESULTS â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab_results:
    st.markdown("### Haplogroup assignments")

    # Try to load results from outdir
    results = st.session_state.get("results", [])

    if not results and Path(outdir).exists():
        results = parse_results_tsv(outdir)
        st.session_state["results"] = results

    if results:
        import pandas as pd
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True, height=360)

        # Haplogroup pills
        hap_col = next((c for c in df.columns if "haplo" in c.lower()), None)
        if hap_col:
            st.markdown("**Detected haplogroups:**")
            pills = " ".join(
                f'<span class="hap-pill">{h}</span>'
                for h in df[hap_col].unique()
            )
            st.markdown(pills, unsafe_allow_html=True)

        # Download TSV
        csv_data = df.to_csv(index=False, sep="\t")
        st.download_button(
            "â¬‡ï¸ Download results TSV",
            data=csv_data,
            file_name="ybyra_haplogroups.tsv",
            mime="text/tab-separated-values",
        )

    else:
        st.markdown("""
        <div style="text-align:center; padding: 3rem; color: #8b90ab;">
            <div style="font-size: 3rem; margin-bottom: 1rem;">ðŸ“‹</div>
            <div style="font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem;">No results yet</div>
            <div style="font-size: 0.9rem;">Run the workflow first, then results will appear here automatically.</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Manual TSV upload for inspection
    with st.expander("ðŸ“‚ Inspect an existing results file"):
        manual_tsv = st.file_uploader("Upload a haplogroup TSV/CSV", type=["tsv", "csv", "txt"])
        if manual_tsv:
            import pandas as pd
            sep = "\t" if manual_tsv.name.endswith(".tsv") else ","
            df2 = pd.read_csv(manual_tsv, sep=sep)
            st.dataframe(df2, use_container_width=True)
