"""
Contract Test for PolicyPort.
"""
import unittest
from jarvis_os.core.ports.policy import PolicyPort
from jarvis_os.core.domain.value_objects import UserIdentity
from jarvis_os.core.domain.exceptions import CommandValidationError, PathValidationError

class TestPolicyPortContract(unittest.TestCase):
    """Verifies that the PolicyPort interface conforms to design specifications."""

    def test_interface_is_abstract(self):
        """Asserts that the PolicyPort cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            PolicyPort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompletePolicy(PolicyPort):
            pass

        with self.assertRaises(TypeError):
            IncompletePolicy()  # type: ignore

    def test_valid_implementation_signatures(self):
        """Asserts that a fully-conforming mock subclass can be instantiated."""
        class MockPolicy(PolicyPort):
            def is_authorized(self, user: UserIdentity, action: str, resource: str) -> bool:
                if "admin" in user.roles:
                    return True
                return action == "read" and resource == "public"

            def validate_command(self, command_line: str) -> bool:
                if ";" in command_line or "rm " in command_line:
                    raise CommandValidationError("Dangerous command rejected")
                return True

            def validate_path(self, target_path: str) -> bool:
                if ".." in target_path or target_path.startswith("/etc"):
                    raise PathValidationError("Path traversal/boundary violation")
                return True

        policy = MockPolicy()
        self.assertIsInstance(policy, PolicyPort)
        
        user_user = UserIdentity(identity_id="user1", roles=["user"])
        user_admin = UserIdentity(identity_id="admin1", roles=["admin"])
        
        # Test auth checks
        self.assertTrue(policy.is_authorized(user_admin, "write", "private"))
        self.assertTrue(policy.is_authorized(user_user, "read", "public"))
        self.assertFalse(policy.is_authorized(user_user, "write", "private"))
        
        # Test command checks
        self.assertTrue(policy.validate_command("echo hello"))
        with self.assertRaises(CommandValidationError):
            policy.validate_command("echo hello; rm -rf /")
            
        # Test path checks
        self.assertTrue(policy.validate_path("/workspace/file.txt"))
        with self.assertRaises(PathValidationError):
            policy.validate_path("/workspace/../etc/passwd")

if __name__ == "__main__":
    unittest.main()
