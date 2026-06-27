"""
Unit tests for the Policy Engine and Authorization framework.
"""
from dataclasses import dataclass, replace
import threading
import unittest
from typing import Any, Dict, Optional

from jarvis_os.core.domain.value_objects import UserIdentity, PathPermission, CommandDefinition
from jarvis_os.core.domain.exceptions import UnauthorizedError, PathValidationError, CommandValidationError
from jarvis_os.infrastructure.policy.policy_engine import (
    PolicyEngine,
    PolicyRule,
    PolicyDecision,
    RoleBasedRule,
    PermissionBasedRule,
    AndRule,
    OrRule,
    NotRule,
    PolicyEvaluationError,
)


# ═══════════════════════════════════════════════════════════════════════ #
#  Mock rules for testing                                                 #
# ═══════════════════════════════════════════════════════════════════════ #

class DenyRule(PolicyRule):
    """Explicitly denies if matching a specific action."""

    def __init__(self, name: str, deny_action: str, priority: int = 0) -> None:
        super().__init__(name, priority)
        self.deny_action = deny_action

    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        if action == self.deny_action:
            return False
        return None


class ContextEvaluatingRule(PolicyRule):
    """Evaluates context variables to determine permission."""

    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        if context and context.get("ip_address") == "127.0.0.1":
            return True
        return None


class ExceptionRaisingRule(PolicyRule):
    """Simulates a rule execution runtime error."""

    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        raise RuntimeError("DB lookup failure during policy rule check")


# ═══════════════════════════════════════════════════════════════════════ #
#  Test Suite                                                             #
# ═══════════════════════════════════════════════════════════════════════ #

class TestPolicyEngine(unittest.TestCase):
    """Tests evaluating deterministic allow, deny, composition, and validation safety."""

    def setUp(self) -> None:
        self.user = UserIdentity(
            identity_id="u1",
            roles=["user", "admin"],
            permissions=["read:all", "write:limited"],
        )
        self.engine = PolicyEngine()

    # ------------------------------------------------------------------ #
    # Rule Evaluation: Allow, Deny, and Default Deny                        #
    # ------------------------------------------------------------------ #

    def test_default_deny_behavior(self) -> None:
        """If no rules match or exist, the policy decision defaults to denied."""
        decision = self.engine.evaluate_policy(self.user, "write", "sys:config")
        self.assertFalse(decision.authorized)
        self.assertIn("Default Deny", decision.reason)
        self.assertIsNone(decision.rule_name)

    def test_explicit_allow_rule(self) -> None:
        """Explicit allow rule grants access."""
        rule = RoleBasedRule("Allow Admin", required_role="admin", allow=True)
        self.engine.add_rule(rule)

        decision = self.engine.evaluate_policy(self.user, "write", "sys:config")
        self.assertTrue(decision.authorized)
        self.assertEqual(decision.rule_name, "Allow Admin")
        self.assertIn("Explicitly allowed", decision.reason)

    def test_explicit_deny_rule(self) -> None:
        """Explicit deny rule rejects access."""
        rule = DenyRule("Block Write", deny_action="write")
        self.engine.add_rule(rule)

        decision = self.engine.evaluate_policy(self.user, "write", "sys:config")
        self.assertFalse(decision.authorized)
        self.assertEqual(decision.rule_name, "Block Write")
        self.assertIn("Explicitly denied", decision.reason)

    # ------------------------------------------------------------------ #
    # Rule Priority and Ordering                                            #
    # ------------------------------------------------------------------ #

    def test_rule_priority_sorting(self) -> None:
        """Rules are sorted and executed by descending priority order."""
        # Lower priority allows, higher priority denies
        allow_rule = RoleBasedRule("Allow User", required_role="user", allow=True, priority=10)
        deny_rule = DenyRule("Block Action", deny_action="write", priority=20)

        self.engine.add_rule(allow_rule)
        self.engine.add_rule(deny_rule)

        # Deny rule runs first because it has priority 20 vs 10
        decision = self.engine.evaluate_policy(self.user, "write", "sys:config")
        self.assertFalse(decision.authorized)
        self.assertEqual(decision.rule_name, "Block Action")

    def test_deterministic_name_sorting_for_identical_priorities(self) -> None:
        """If priorities match, sorting falls back alphabetically to ensure determinism."""
        # Both rule A and rule B match, but rule A should be evaluated first
        rule_b = RoleBasedRule("Rule B", required_role="admin", allow=True, priority=10)
        rule_a = DenyRule("Rule A", deny_action="write", priority=10)

        # Add in reverse alphabetical order
        self.engine.add_rule(rule_b)
        self.engine.add_rule(rule_a)

        decision = self.engine.evaluate_policy(self.user, "write", "sys:config")
        # Rule A (deny) should run before Rule B (allow) because "Rule A" < "Rule B"
        self.assertFalse(decision.authorized)
        self.assertEqual(decision.rule_name, "Rule A")

    # ------------------------------------------------------------------ #
    # Rule Composition (AND, OR, NOT)                                      #
    # ------------------------------------------------------------------ #

    def test_and_rule_composition(self) -> None:
        """AndRule composition yields True only if all sub-rules allow."""
        r1 = RoleBasedRule("r1", required_role="admin")
        r2 = PermissionBasedRule("r2", required_permission="write:limited")
        composed = AndRule("Composed", [r1, r2])

        self.engine.add_rule(composed)
        self.assertTrue(self.engine.is_authorized(self.user, "write", "sys:config"))

        # Fail one rule conditions
        bad_user = UserIdentity("u2", roles=["admin"])  # Admin but no permissions
        self.assertFalse(self.engine.is_authorized(bad_user, "write", "sys:config"))

    def test_or_rule_composition(self) -> None:
        """OrRule composition yields True if any sub-rule allows."""
        r1 = RoleBasedRule("r1", required_role="superadmin")  # User does not have this
        r2 = PermissionBasedRule("r2", required_permission="read:all")   # User has this
        composed = OrRule("Composed Or", [r1, r2])

        self.engine.add_rule(composed)
        self.assertTrue(self.engine.is_authorized(self.user, "read", "sys:config"))

    def test_not_rule_composition(self) -> None:
        """NotRule composition inverts the child rule output."""
        r1 = RoleBasedRule("r1", required_role="admin", allow=True)  # Returns True for this user
        not_r1 = NotRule("Not Admin", r1)

        self.engine.add_rule(not_r1)
        decision = self.engine.evaluate_policy(self.user, "write", "sys:config")
        self.assertFalse(decision.authorized)

    # ------------------------------------------------------------------ #
    # Context-Based Evaluation                                              #
    # ------------------------------------------------------------------ #

    def test_context_rule_evaluation(self) -> None:
        """Context details are evaluated during rule checks."""
        self.engine.add_rule(ContextEvaluatingRule("IP Check"))

        # Missing context or non-matching IP fails
        self.assertFalse(self.engine.is_authorized(self.user, "read", "resource"))
        self.assertFalse(self.engine.is_authorized(self.user, "read", "resource", {"ip_address": "8.8.8.8"}))

        # Correct IP context allows
        self.assertTrue(self.engine.is_authorized(self.user, "read", "resource", {"ip_address": "127.0.0.1"}))

    # ------------------------------------------------------------------ #
    # Exception Handling                                                   #
    # ------------------------------------------------------------------ #

    def test_rule_error_raises_policy_evaluation_error(self) -> None:
        """Errors in user-defined rules are wrapped in PolicyEvaluationError."""
        self.engine.add_rule(ExceptionRaisingRule("Failing Rule"))
        with self.assertRaises(PolicyEvaluationError):
            self.engine.evaluate_policy(self.user, "read", "resource")

    # ------------------------------------------------------------------ #
    # Immutability                                                          #
    # ------------------------------------------------------------------ #

    def test_policy_decision_is_frozen(self) -> None:
        """PolicyDecision dataclass is frozen and cannot be modified."""
        decision = PolicyDecision(authorized=True, reason="Allowed")
        with self.assertRaises(Exception):
            decision.authorized = False  # type: ignore[misc]

    # ------------------------------------------------------------------ #
    # Path Sandboxing (validate_path)                                      #
    # ------------------------------------------------------------------ #

    def test_validate_path_checks_sandbox_correctly(self) -> None:
        """validate_path ensures path is within sandbox limits with no traversal."""
        sandbox = [
            PathPermission(allowed_root_path="/app/sandbox", can_read=True, can_write=True),
            PathPermission(allowed_root_path="/etc/configs", can_read=True, can_write=False),
        ]
        engine = PolicyEngine(path_permissions=sandbox)

        # Valid paths
        self.assertTrue(engine.validate_path("/app/sandbox/user_data.txt"))
        self.assertTrue(engine.validate_path("/etc/configs/settings.json"))

        # Outside sandbox boundary
        with self.assertRaises(PathValidationError):
            engine.validate_path("/app/hacker/malicious.sh")

        # Traversal attempts
        with self.assertRaises(PathValidationError):
            engine.validate_path("/app/sandbox/../escape.txt")

    # ------------------------------------------------------------------ #
    # Command Validation (validate_command)                                #
    # ------------------------------------------------------------------ #

    def test_validate_command_rejects_injections_and_invalid_commands(self) -> None:
        """validate_command rejects dangerous characters and unauthorized tools."""
        commands = [
            CommandDefinition(executable="git", allowed_arguments_patterns=[r"^clone$", r"^status$"]),
            CommandDefinition(executable="python", allowed_arguments_patterns=[r"^--version$"]),
        ]
        engine = PolicyEngine(command_definitions=commands)

        # Safe commands matching patterns
        self.assertTrue(engine.validate_command("git status"))
        self.assertTrue(engine.validate_command("python --version"))

        # Unauthorized executable
        with self.assertRaises(CommandValidationError):
            engine.validate_command("bash hack.sh")

        # Command argument validation violation
        with self.assertRaises(CommandValidationError):
            engine.validate_command("git commit")

        # Metacharacter shell injections
        with self.assertRaises(CommandValidationError):
            engine.validate_command("git status; rm -rf /")

        with self.assertRaises(CommandValidationError):
            engine.validate_command("git status && cat /etc/passwd")

    # ------------------------------------------------------------------ #
    # Thread Safety                                                         #
    # ------------------------------------------------------------------ #

    def test_policy_evaluation_is_thread_safe(self) -> None:
        """Evaluation logic can run concurrently on multiple threads without corruption."""
        rule = RoleBasedRule("Allow Admin", required_role="admin", allow=True)
        self.engine.add_rule(rule)

        errors = []

        def worker():
            try:
                for _ in range(50):
                    res = self.engine.is_authorized(self.user, "write", "resource")
                    assert res is True
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
