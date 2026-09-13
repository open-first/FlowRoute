# Installation

FlowRoute requires Python 3.10 or newer.

## Core router

Create an isolated environment and install the published package:

```bash
python -m venv .venv
source .venv/bin/activate
pip install flowroute
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

The core install provides:

- the `flowroute` Python package;
- the `flowroute route` and `flowroute evaluate` commands;
- the local TF-IDF retriever and lexical verifier; and
- YAML catalog validation.

It does **not** include the demo catalog, fixtures, or training scripts. Those live in the
repository; see [From source](#from-source) if you need them.

## Optional extras

=== "HTTP API"

    ```bash
    pip install "flowroute[api]"
    ```

    Adds FastAPI and Uvicorn for `flowroute serve`.

=== "Hugging Face"

    ```bash
    pip install "flowroute[hf]"
    ```

    Adds the learned inference backends. This install is significantly larger because it includes
    Torch.

=== "Model training"

    ```bash
    pip install "flowroute[training]"
    ```

    Adds Datasets and Accelerate to the learned-backend dependencies. The training scripts
    themselves ship only in the repository.

=== "Development"

    ```bash
    pip install -e ".[dev]"
    ```

    Adds pytest, Ruff, mypy, build, and HTTPX. Run this from a clone, not against the published
    package.

=== "Documentation"

    ```bash
    pip install -r requirements-docs.txt
    ```

    Adds MkDocs and Material for MkDocs. Requires a clone.

## From source

Work from a clone when you need the demo catalog, the fixture suite, the training scripts, or a
development install:

```bash
git clone https://github.com/open-first/FlowRoute.git
cd FlowRoute
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

An editable install points the `flowroute` command at your working tree, so source edits take
effect without reinstalling.

## Verify the install

```bash
flowroute --help
python -c "import flowroute; print(flowroute.__version__)"
```

From a clone, also run the test suite:

```bash
pytest -q
```

## Dependency groups

| Install | Main dependencies | Intended use |
| --- | --- | --- |
| `pip install flowroute` | NumPy, Pydantic, PyYAML, regex, scikit-learn | Local baseline and library |
| `pip install "flowroute[api]"` | FastAPI, Uvicorn | HTTP service |
| `pip install "flowroute[hf]"` | Torch, Transformers, Sentence Transformers | Learned inference backends |
| `pip install "flowroute[training]"` | Datasets, Accelerate, and learned-backend dependencies | Dataset processing and training |
| `pip install -e ".[dev]"` | pytest, Ruff, mypy, build, HTTPX | Development and tests (clone only) |

Next: [route the first request](quickstart.md).
