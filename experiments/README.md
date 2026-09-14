# FlowRoute paper benchmark

This directory reproduces every empirical number in the FlowRoute paper. The
benchmark downloads the official CLINC150 and BANKING77 files, verifies their
SHA-256 digests, and evaluates the pinned `all-MiniLM-L6-v2` model revision.

The public test splits are never used to select the description/example mixing
weight or abstention thresholds. CLINC150 uses its official validation split
and combines its official out-of-scope training and validation sets for
threshold selection. Both calibration constraints use the upper endpoints of
two-sided 95% Wilson intervals rather than point estimates.
Because BANKING77 has no official validation split, the script deterministically
reserves 20 training examples per intent before selecting workflow examples.

## Run

Python 3.12 was used for the paper. Create an environment and install the pinned
dependencies:

```bash
python -m venv .venv
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0
.venv/bin/pip install -r requirements.txt
HF_HOME=cache .venv/bin/python run_benchmark.py
```

The script writes:

- `results/benchmark_results.json`: complete per-seed metrics, thresholds,
  environment, model revision, source URLs, and checksums.
- `results/ranking_summary.csv`: compact ranking table.
- `environment-lock.txt`: the complete package-version record from the
  reported run. It is an environment record, not a cross-platform installer.

Downloaded dataset files and model cache files are intentionally excluded from
the source bundle. The original licenses apply: CC BY 3.0 for CLINC150, CC BY
4.0 for BANKING77, and Apache 2.0 for `all-MiniLM-L6-v2`.
