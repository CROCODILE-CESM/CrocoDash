from datetime import datetime

class CaseRecord:
    # List all fields here for maintainability
    FIELDS = (
        "grid_file", "vgrid_file", "topo_file", "date", "message",
        "cesmroot", "caseroot", "inputdir", "inittime", "datm_mode",
        "datm_grid_name", "ninst", "machine", "project", "override",
        "forcing_config", "restored_from"
    )

    def __init__(self, **kwargs):
        self.data = {}
        for field in self.FIELDS:
            if field == "date":
                self.data[field] = kwargs.get(field) or datetime.now().isoformat()
            elif field == "forcing_config":
                self.data[field] = kwargs.get(field) or {}
            else:
                self.data[field] = kwargs.get(field)
        # For convenience, allow attribute access
        for field in self.FIELDS:
            setattr(self, field, self.data[field])

    def to_dict(self):
        def stringify(obj):
            try:
                from pathlib import Path
                if isinstance(obj, Path):
                    return str(obj)
                elif isinstance(obj, dict):
                    return {k: stringify(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return type(obj)(stringify(v) for v in obj)
                else:
                    return obj
            except ImportError:
                return obj
        return {field: stringify(self.data[field]) for field in self.FIELDS}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def summary_line(self, idx=None):
        idx_str = f"{idx}: " if idx is not None else ""
        msg = f" | {self.data.get('message','')}" if self.data.get("message") else ""
        restored = f" | restored_from: {self.data.get('restored_from')}" if self.data.get("restored_from") is not None else ""
        return (
            f"{idx_str}Grid: {self.data.get('grid_file')}, "
            f"VGrid: {self.data.get('vgrid_file')}, "
            f"Topo: {self.data.get('topo_file')}, "
            f"Date: {self.data.get('date')}{msg}{restored}"
        )