"""
Unit tests for DIContainer.
"""
import unittest
import threading
import time
from typing import Any
from jarvis_os.core.di import DIContainer
from jarvis_os.core.domain.exceptions import DIResolutionError

class TestDIContainer(unittest.TestCase):
    """Verifies that the DIContainer behaves correctly and is thread-safe."""

    def setUp(self):
        self.container = DIContainer()

    def test_singleton_lifetime(self):
        """Asserts that singletons are instantiated only once and return the same instance."""
        class DummyService:
            pass

        self.container.register_singleton(DummyService, lambda c: DummyService())
        
        inst1 = self.container.resolve(DummyService)
        inst2 = self.container.resolve(DummyService)

        self.assertIsInstance(inst1, DummyService)
        self.assertIs(inst1, inst2)

    def test_transient_lifetime(self):
        """Asserts that transients return a fresh instance on every resolution."""
        class DummyService:
            pass

        self.container.register_transient(DummyService, lambda c: DummyService())

        inst1 = self.container.resolve(DummyService)
        inst2 = self.container.resolve(DummyService)

        self.assertIsInstance(inst1, DummyService)
        self.assertIsNot(inst1, inst2)

    def test_transitive_dependency_resolution(self):
        """Asserts that nested dependencies are successfully resolved through the container."""
        class DepB:
            pass

        class DepA:
            def __init__(self, dep_b: DepB):
                self.dep_b = dep_b

        self.container.register_singleton(DepB, lambda c: DepB())
        self.container.register_singleton(DepA, lambda c: DepA(dep_b=c.resolve(DepB)))

        inst_a = self.container.resolve(DepA)
        inst_b = self.container.resolve(DepB)

        self.assertIsInstance(inst_a, DepA)
        self.assertIsInstance(inst_a.dep_b, DepB)
        self.assertIs(inst_a.dep_b, inst_b)

    def test_register_instance(self):
        """Asserts that already created instances are correctly registered and returned."""
        class DummyService:
            pass

        instance = DummyService()
        self.container.register_instance(DummyService, instance)

        resolved = self.container.resolve(DummyService)
        self.assertIs(resolved, instance)

    def test_unregistered_resolution_failure(self):
        """Asserts that resolving unregistered services raises DIResolutionError."""
        class UnregisteredService:
            pass

        with self.assertRaises(DIResolutionError):
            self.container.resolve(UnregisteredService)

    def test_clear_flushes_all_registrations(self):
        """Asserts that clear() removes all registrations and cached singletons."""
        class DummyService:
            pass

        self.container.register_singleton(DummyService, lambda c: DummyService())
        self.container.resolve(DummyService)

        self.container.clear()

        with self.assertRaises(DIResolutionError):
            self.container.resolve(DummyService)

    def test_factory_error_propagation(self):
        """Asserts that exceptions raised inside factories are wrapped in DIResolutionError."""
        class FaultyService:
            pass

        def faulty_factory(c):
            raise ValueError("Error in factory")

        self.container.register_transient(FaultyService, faulty_factory)

        with self.assertRaises(DIResolutionError) as ctx:
            self.container.resolve(FaultyService)
        self.assertTrue("Error in factory" in str(ctx.exception))

    def test_thread_safe_singleton_resolution(self):
        """Asserts that singletons are thread-safe and only instantiated once by parallel threads."""
        class SlowService:
            instantiation_count = 0
            count_lock = threading.Lock()

            def __init__(self):
                with SlowService.count_lock:
                    SlowService.instantiation_count += 1
                time.sleep(0.001)  # Force context switch to test race conditions

        self.container.register_singleton(SlowService, lambda c: SlowService())

        resolved_instances = []
        threads = []

        def worker():
            inst = self.container.resolve(SlowService)
            resolved_instances.append(inst)

        # Run 5 threads concurrently resolving the same singleton
        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)  # Guard: never hang for more than 5 s

        # All threads must have resolved the same instance
        self.assertEqual(len(resolved_instances), 5)
        first_instance = resolved_instances[0]
        for inst in resolved_instances:
            self.assertIs(inst, first_instance)

        # Constructor must have run exactly once
        self.assertEqual(SlowService.instantiation_count, 1)

if __name__ == "__main__":
    unittest.main()
