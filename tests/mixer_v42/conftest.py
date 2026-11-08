"""Ejecuta las pruebas ORIGINALES del Mezclador V4.2 contra los módulos integrados en AllForOne.

Los archivos de prueba se copiaron sin cambios. Las que importan `app` (la interfaz Gradio
original) solo se ejecutan si Gradio está instalado; AllForOne no lo necesita.
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIXER = ROOT / "app" / "allforone" / "mixer_v42"
os.environ.setdefault("MEZCLADOR_DATA_DIR", tempfile.mkdtemp(prefix="afo_mezclador_tests_"))
sys.path.insert(0, str(MIXER))

collect_ignore = []
if importlib.util.find_spec("gradio") is not None:
    spec = importlib.util.spec_from_file_location("app", Path(__file__).with_name("app_original_gradio.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["app"] = module
    spec.loader.exec_module(module)
else:
    for f in Path(__file__).parent.glob("test_*.py"):
        if "import app" in f.read_text(encoding="utf-8"):
            collect_ignore.append(f.name)
