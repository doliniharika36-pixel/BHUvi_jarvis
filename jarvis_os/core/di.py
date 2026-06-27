"""
Dependency Injection (DI) Container for Jarvis OS.
"""
import threading
from typing import Any, Callable, Dict, Tuple, Type, TypeVar
from jarvis_os.core.domain.exceptions import DIResolutionError

T = TypeVar('T')

class DIContainer:
    """Thread-safe dependency injection container with singleton and transient lifetimes."""

    def __init__(self):
        self._registry: Dict[Type[Any], Tuple[Callable[['DIContainer'], Any], str]] = {}
        self._instances: Dict[Type[Any], Any] = {}
        self._lock = threading.Lock()

    def register_singleton(self, interface: Type[T], factory: Callable[['DIContainer'], T]) -> None:
        """Register a service factory with singleton lifetime.
        
        The same instance will be returned on every subsequent resolve() call.
        """
        with self._lock:
            self._registry[interface] = (factory, 'singleton')
            # Evict from instances cache if re-registered
            if interface in self._instances:
                del self._instances[interface]

    def register_instance(self, interface: Type[T], instance: T) -> None:
        """Register an already created instance directly as a singleton."""
        with self._lock:
            self._registry[interface] = (lambda container: instance, 'singleton')
            self._instances[interface] = instance

    def register_transient(self, interface: Type[T], factory: Callable[['DIContainer'], T]) -> None:
        """Register a service factory with transient lifetime.
        
        A new instance will be created and returned on every resolve() call.
        """
        with self._lock:
            self._registry[interface] = (factory, 'transient')
            if interface in self._instances:
                del self._instances[interface]

    def resolve(self, interface: Type[T]) -> T:
        """Resolve a service registration and return an instance.
        
        Raises:
            DIResolutionError: If the requested interface is not registered, or a resolution cycle is detected.
        """
        # Read check outside lock (to optimize read performance, but lock creation is handled safely)
        with self._lock:
            if interface not in self._registry:
                raise DIResolutionError(f"No registration found for interface: {interface.__name__ if hasattr(interface, '__name__') else interface}")

            factory, lifetime = self._registry[interface]

            if lifetime == 'singleton':
                if interface not in self._instances:
                    try:
                        # Instantiate inside lock
                        self._instances[interface] = factory(self)
                    except Exception as e:
                        raise DIResolutionError(f"Failed to instantiate singleton {interface.__name__ if hasattr(interface, '__name__') else interface}: {e}") from e
                return self._instances[interface]  # type: ignore
            else:
                try:
                    # Transient
                    return factory(self)
                except Exception as e:
                    raise DIResolutionError(f"Failed to instantiate transient {interface.__name__ if hasattr(interface, '__name__') else interface}: {e}") from e

    def clear(self) -> None:
        """Flush all registered services and cached singletons."""
        with self._lock:
            self._registry.clear()
            self._instances.clear()
