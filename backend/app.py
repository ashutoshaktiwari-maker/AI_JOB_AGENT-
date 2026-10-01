"""
Streamlit Dashboard Launcher for backend directory.
"""
from pathlib import Path
import runpy

root_app = Path(__file__).resolve().parent.parent / "app.py"
runpy.run_path(str(root_app), run_name="__main__")
