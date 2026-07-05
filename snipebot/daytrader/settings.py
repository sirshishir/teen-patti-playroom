"""settings.py — load daytrader/config.yaml once, expose CONFIG + timezone."""

import os

import pytz
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_HERE, "config.yaml")) as _f:
    CONFIG = yaml.safe_load(_f)

ET = pytz.timezone(CONFIG.get("timezone", "US/Eastern"))
