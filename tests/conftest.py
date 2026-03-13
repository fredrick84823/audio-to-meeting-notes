import sys
from pathlib import Path

# 讓測試能直接 import skill/scripts 下的模組
sys.path.insert(0, str(Path(__file__).parent.parent / "skill" / "scripts"))
