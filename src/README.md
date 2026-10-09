# Source layout note

The executed Python scripts are intentionally kept at the repository root rather than moved into this directory. Their file-relative paths were part of the executed proof-of-concept package, so the public reproducibility release preserves that layout instead of refactoring code after the experiment.

The main entry point is `run_all.py`. Core implementation is in `poc_experiment.py`.
