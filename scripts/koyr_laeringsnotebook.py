"""Execute and save the default learning notebook with the project Python."""
import os
import sys
import argparse
from pathlib import Path
import nbformat
from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output

root = Path(__file__).resolve().parents[1]
os.environ['IPYTHONDIR'] = str(root / 'models/.ipython')
os.environ['JUPYTER_RUNTIME_DIR'] = str(root / 'models/.jupyter_runtime')
parser = argparse.ArgumentParser()
parser.add_argument('notebook', nargs='?', default='notebooks/skred_ml_laering.ipynb')
args = parser.parse_args()
path = root / args.notebook
nb = nbformat.read(path, as_version=4)
nbformat.validate(nb)
os.chdir(root)
shell = InteractiveShell.instance()
count = 0
for cell in nb.cells:
    if cell.cell_type != 'code':
        continue
    count += 1
    print(f'Kodecelle {count}', flush=True)
    with capture_output() as captured:
        result = shell.run_cell(cell.source, store_history=True)
    if result.error_before_exec or result.error_in_exec:
        print(captured.stdout)
        print(captured.stderr)
        raise RuntimeError(f'Feil i kodecelle {count}') from (result.error_before_exec or result.error_in_exec)
    cell.execution_count = count
    cell.outputs = []
    for stream, content in [('stdout', captured.stdout), ('stderr', captured.stderr)]:
        if content:
            cell.outputs.append(nbformat.v4.new_output('stream', name=stream, text=content))
    for output in captured.outputs:
        cell.outputs.append(nbformat.v4.new_output('display_data', data=output.data, metadata=output.metadata))
nbformat.validate(nb)
nbformat.write(nb, path)
print(f'Kontrollert og lagra: {sum(c.cell_type == "code" for c in nb.cells)} kodeceller')
