from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ng_autopilot.miit_monitor import monitor
print(monitor(ROOT))
