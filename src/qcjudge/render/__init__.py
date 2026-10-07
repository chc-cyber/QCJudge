"""Rendering an audit report for humans or machines."""

from qcjudge.render.json_report import SCHEMA, report_to_dict, to_json
from qcjudge.render.text import report_to_text

__all__ = ["SCHEMA", "report_to_dict", "report_to_text", "to_json"]
