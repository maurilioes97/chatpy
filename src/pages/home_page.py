from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from views.home import render_home


render_home()
