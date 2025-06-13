from abc import ABC, abstractmethod

class EditCommand(ABC):
    @abstractmethod
    def execute(self, obj):
        pass

    @abstractmethod
    def undo(self, obj):
        pass

    @abstractmethod
    def serialize(self) -> dict:
        pass

    @classmethod
    @abstractmethod
    def deserialize(cls, data: dict):
        pass

# Registry for type <-> class mapping
COMMAND_REGISTRY = {}
def register_command(cls):
    COMMAND_REGISTRY[cls.__name__] = cls
    return cls