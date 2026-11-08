"""Temporales y registro locales al proyecto, antes de importar Gradio."""
import os,tempfile,logging,shutil
from pathlib import Path
from logging.handlers import RotatingFileHandler

ROOT=Path(os.environ.get('MEZCLADOR_DATA_DIR',Path(__file__).resolve().parent)).resolve()
CACHE=ROOT/'cache_gradio'
TEMP=ROOT/'temporales'
LOGS=ROOT/'logs'
for folder in (CACHE,TEMP,LOGS):folder.mkdir(parents=True,exist_ok=True)
os.environ['GRADIO_TEMP_DIR']=str(CACHE)
os.environ['TEMP']=os.environ['TMP']=str(TEMP)
os.environ['GRADIO_ANALYTICS_ENABLED']='False'
tempfile.tempdir=str(TEMP)
handler=RotatingFileHandler(LOGS/'errores.log',maxBytes=3_000_000,backupCount=2,encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger=logging.getLogger('mezclador')
logger.setLevel(logging.INFO)
if not logger.handlers:logger.addHandler(handler)

def check_space(paths,destination):
    required=sum(Path(p).stat().st_size for p in paths)*7+150_000_000
    parent=Path(destination).resolve()
    while not parent.exists():parent=parent.parent
    free=shutil.disk_usage(parent).free
    if free<required:
        raise OSError(f'Espacio insuficiente en {parent.drive or parent}: disponibles {free/1e9:.1f} GB; se estiman {required/1e9:.1f} GB para esta sesion y exportaciones.')
