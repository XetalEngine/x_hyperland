#!/usr/bin/env python3
"""Prepare portable icon overlays when installing or updating this profile."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from icon_themes import model
if __name__=='__main__':model.ensure()
