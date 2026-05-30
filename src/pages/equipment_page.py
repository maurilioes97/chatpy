from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from views.equipment_page import render_equipment_page


render_equipment_page()
