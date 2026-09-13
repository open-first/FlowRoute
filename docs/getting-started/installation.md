# Installation

FlowRoute requires Python 3.10 or newer.

## Core router

Create an isolated environment and install the package in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
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

## Optional extras

=== "HTTP API"

    ```bash
    pip install -e ".[api]"
    ```

    Adds FastAPI and Uvicorn for `flowroute serve`.

=== "Hugging Face"

    ```bash
    pip install -e ".[hf]"
    ```

    Adds the learned inference backends. This install is significantly larger because it includes
    Torch.

=== "Model training"

    ```bash
    pip install -e ".[training]"
    ```

    Adds Datasets and Accelerate to the learned-backend dependencies.

=== "Development"

    ```bash
    pip install -e ".[dev]"
    ```

    Adds pytest, Ruff, mypy, build, and HTTPX.

=== "Documentation"

    ```bash
    pip install -r requirements-docs.txt
    ```

    Adds MkDocs and Material for MkDocs.

## Verify the install

```bash
flowroute --help
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Dependency groups

| Install | Main dependencies | Intended use |
| --- | --- | --- |
| `pip install -e .` | NumPy, Pydantic, PyYAML, regex, scikit-learn | Local baseline and library |
| `pip install -e ".[api]"` | FastAPI, Uvicorn | HTTP service |
| `pip install -e ".[hf]"` | Torch, Transformers, Sentence Transformers | Learned inference backends |
| `pip install -e ".[training]"` | Datasets, Accelerate, and learned-backend dependencies | Dataset processing and training |
| `pip install -e ".[dev]"` | pytest, Ruff, mypy, build, HTTPX | Development and tests |

Next: [route the first request](quickstart.md).
