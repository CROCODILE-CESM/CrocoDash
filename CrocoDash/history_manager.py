from abc import ABC, abstractmethod

class EditHistory(ABC):
    def __init__(self, domain_id, snapshot_dir="snapshots"):
        self._undo_history = []
        self._redo_history = []
        self.snapshot_dir = snapshot_dir
        self.domain_id = domain_id

    @abstractmethod
    def get_domain_id(self):
        """Return a unique identifier for the domain/context."""
        pass

    @abstractmethod
    def push(self, command):
        """Add a command to the history."""
        pass

    @abstractmethod
    def undo(self, obj):
        """Undo the last command."""
        pass

    @abstractmethod
    def redo(self, obj):
        """Redo the last undone command."""
        pass

    @abstractmethod
    def save_histories(self):
        """Save the current undo/redo history to disk."""
        pass

    @abstractmethod
    def load_histories(self, command_registry):
        """Load the undo/redo history from disk."""
        pass

    @abstractmethod
    def save_commit(self, name):
        """Save a named snapshot/commit."""
        pass

    @abstractmethod
    def load_commit(self, name, command_registry):
        """Load a named snapshot/commit."""
        pass

    @abstractmethod
    def replay(self, obj):
        """Replay all commands in the undo history to the object."""
        pass