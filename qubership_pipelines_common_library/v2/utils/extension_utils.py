import importlib
from typing import Type, Any, Optional


class ExtensionLoader:
    """Utility methods to create instance of a class by its classpath and validate its expected base class"""

    @staticmethod
    def load_class(class_path: str) -> Type[Any]:
        try:
            module_path, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except (ImportError, AttributeError, ValueError) as e:
            raise ImportError(f"Failed to load class {class_path}: {e}")

    @staticmethod
    def create_instance(class_path: str, expected_base_class: Optional[Type] = None, **kwargs) -> Any:
        klass = ExtensionLoader.load_class(class_path)
        if expected_base_class and not issubclass(klass, expected_base_class):
            raise TypeError(f"Class {class_path} must inherit from {expected_base_class.__name__}")
        return klass(**kwargs)
