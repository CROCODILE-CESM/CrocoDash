from abc import ABC, abstractmethod

class CommandManager(ABC):
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
    def execute(self, cmd):
        """Execute a command, push it onto the undo stack, and clear the redo stack."""
        pass

    @abstractmethod
    def push(self, command):
        """Add a command to the history."""
        pass

    @abstractmethod
    def undo(self):
        """Undo the last command."""
        pass

    @abstractmethod
    def redo(self):
        """Redo the last undone command."""
        pass

    @abstractmethod
    def save_histories(self):
        """Save the current undo/redo history to disk."""
        pass

    @abstractmethod
    def load_histories(self, command_registry, *args, **kwargs):
        """Load the undo/redo history from disk.
        *args, **kwargs :
            Additional context needed for deserialization (if any)."""
        pass

    @abstractmethod
    def save_commit(self, name):
        """Save a named snapshot/commit."""
        pass

    @abstractmethod
    def load_commit(self, name, command_registry, *args, **kwargs):
        """Load a named snapshot/commit.
        *args, **kwargs :
            Additional context needed for deserialization (if any)."""
        pass

    @abstractmethod
    def initialize(self, command_registry, *args, **kwargs):
        """Initialize with a given registry and context."""
        pass

    @abstractmethod
    def replay(self):
        """Replay all commands in the undo history."""
        pass