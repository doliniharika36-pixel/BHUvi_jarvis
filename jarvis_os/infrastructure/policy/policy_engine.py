"""
Deterministic, thread-safe Policy Engine implementation for Jarvis OS.

Features:
- Generic rule abstractions (PolicyRule) with explicit priorities.
- Default Deny posture.
- Logical rule composition (AndRule, OrRule, NotRule).
- Safe, purely logical command and path validation (no OS/LLM/tool calls).
- Thread-safe evaluations using RLock.
- Immutable policy decisions.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
import re
import threading
from typing import Any, Dict, List, Optional

from jarvis_os.core.ports.policy import PolicyPort
from jarvis_os.core.domain.value_objects import UserIdentity, PathPermission, CommandDefinition
from jarvis_os.core.domain.exceptions import SecurityException, UnauthorizedError, PathValidationError, CommandValidationError


# ═══════════════════════════════════════════════════════════════════════ #
#  Exceptions                                                             #
# ═══════════════════════════════════════════════════════════════════════ #

class PolicyException(SecurityException):
    """Base exception for policy engine issues."""
    pass


class PolicyEvaluationError(PolicyException):
    """Raised when policy rule evaluation encounters an unhandled runtime error."""
    pass


# ═══════════════════════════════════════════════════════════════════════ #
#  Value Objects                                                          #
# ═══════════════════════════════════════════════════════════════════════ #

@dataclass(frozen=True)
class PolicyDecision:
    """Immutable representation of a policy check result."""
    authorized: bool
    reason: str
    rule_name: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════ #
#  Policy Rule Abstractions                                               #
# ═══════════════════════════════════════════════════════════════════════ #

class PolicyRule(ABC):
    """Base abstraction for security and safety rules."""

    def __init__(self, name: str, priority: int = 0) -> None:
        """
        Args:
            name: Human-readable name of the rule.
            priority: Higher numbers evaluate first.
        """
        self.name = name
        self.priority = priority

    @abstractmethod
    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        """Evaluate the request.

        Returns:
            True: Explicit Allow.
            False: Explicit Deny (Overrides allow at lower/equal priority).
            None: Abstain / Not applicable (let next rules decide).
        """
        pass


# ═══════════════════════════════════════════════════════════════════════ #
#  Concrete Rules                                                         #
# ═══════════════════════════════════════════════════════════════════════ #

class RoleBasedRule(PolicyRule):
    """Allows or denies based on whether the user has a specific role."""

    def __init__(self, name: str, required_role: str, allow: bool = True, priority: int = 0) -> None:
        super().__init__(name, priority)
        self.required_role = required_role
        self._allow = allow

    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        if self.required_role in user.roles:
            return self._allow
        return None


class PermissionBasedRule(PolicyRule):
    """Allows or denies based on whether the user has a specific permission string."""

    def __init__(self, name: str, required_permission: str, allow: bool = True, priority: int = 0) -> None:
        super().__init__(name, priority)
        self.required_permission = required_permission
        self._allow = allow

    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        if self.required_permission in user.permissions:
            return self._allow
        return None


# ═══════════════════════════════════════════════════════════════════════ #
#  Logical Rule Composition                                               #
# ═══════════════════════════════════════════════════════════════════════ #

class AndRule(PolicyRule):
    """Composes rules using logical AND.

    If any rule denies, returns Explicit Deny (False).
    If all rules allow, returns Explicit Allow (True).
    Otherwise, abstains (None).
    """

    def __init__(self, name: str, rules: List[PolicyRule], priority: int = 0) -> None:
        super().__init__(name, priority)
        self.rules = rules

    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        all_allow = True
        for rule in self.rules:
            res = rule.evaluate(user, action, resource, context)
            if res is False:
                return False  # Explicit deny wins
            if res is not True:
                all_allow = False
        return True if all_allow else None


class OrRule(PolicyRule):
    """Composes rules using logical OR.

    If any rule allows, returns Explicit Allow (True).
    If all rules deny, returns Explicit Deny (False).
    Otherwise, abstains (None).
    """

    def __init__(self, name: str, rules: List[PolicyRule], priority: int = 0) -> None:
        super().__init__(name, priority)
        self.rules = rules

    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        any_allow = False
        all_deny = True
        for rule in self.rules:
            res = rule.evaluate(user, action, resource, context)
            if res is True:
                any_allow = True
            if res is not False:
                all_deny = False
        if any_allow:
            return True
        if all_deny and self.rules:
            return False
        return None


class NotRule(PolicyRule):
    """Inverts the decision of a single nested rule.

    None/Abstain remains None/Abstain.
    """

    def __init__(self, name: str, rule: PolicyRule, priority: int = 0) -> None:
        super().__init__(name, priority)
        self.rule = rule

    def evaluate(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        res = self.rule.evaluate(user, action, resource, context)
        if res is True:
            return False
        if res is False:
            return True
        return None


# ═══════════════════════════════════════════════════════════════════════ #
#  Policy Engine implementation                                           #
# ═══════════════════════════════════════════════════════════════════════ #

class PolicyEngine(PolicyPort):
    """Thread-safe engine for evaluating security policies, commands, and paths."""

    def __init__(
        self,
        rules: Optional[List[PolicyRule]] = None,
        path_permissions: Optional[List[PathPermission]] = None,
        command_definitions: Optional[List[CommandDefinition]] = None,
    ) -> None:
        """
        Args:
            rules: The rules database sorted by priority.
            path_permissions: Sandboxed root directories config.
            command_definitions: Safe command specifications.
        """
        self._rules = list(rules) if rules else []
        self._path_permissions = list(path_permissions) if path_permissions else []
        self._command_definitions = list(command_definitions) if command_definitions else []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Rule Management                                                      #
    # ------------------------------------------------------------------ #

    def add_rule(self, rule: PolicyRule) -> None:
        """Register a new policy rule."""
        with self._lock:
            self._rules.append(rule)

    # ------------------------------------------------------------------ #
    # PolicyPort Implementation                                            #
    # ------------------------------------------------------------------ #

    def evaluate_policy(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecision:
        """Evaluate request deterministically and return a detailed PolicyDecision."""
        with self._lock:
            # Sort: 1) Priority Descending, 2) Rule Name Alphabetically (Deterministic secondary sort)
            sorted_rules = sorted(self._rules, key=lambda r: (-r.priority, r.name))

            for rule in sorted_rules:
                try:
                    res = rule.evaluate(user, action, resource, context)
                except Exception as exc:
                    raise PolicyEvaluationError(
                        f"Unhandled exception while evaluating rule '{rule.name}': {exc}"
                    ) from exc

                if res is True:
                    return PolicyDecision(
                        authorized=True,
                        reason=f"Explicitly allowed by rule '{rule.name}'",
                        rule_name=rule.name,
                    )
                if res is False:
                    return PolicyDecision(
                        authorized=False,
                        reason=f"Explicitly denied by rule '{rule.name}'",
                        rule_name=rule.name,
                    )

            # Default Deny
            return PolicyDecision(
                authorized=False,
                reason="Default Deny: No matching rules allowed the request",
                rule_name=None,
            )

    def is_authorized(
        self,
        user: UserIdentity,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check user access (returns Boolean to satisfy port contract)."""
        decision = self.evaluate_policy(user, action, resource, context)
        return decision.authorized

    def validate_path(self, target_path: str) -> bool:
        """Verify the path is completely contained inside sandbox boundaries.

        Raises:
            PathValidationError: If path escapes or escapes allowed sandbox roots.
        """
        if not target_path:
            raise PathValidationError("Target path is empty.")

        with self._lock:
            # Normalize purely logically (strictly string manipulation)
            normalized = os.path.normpath(target_path).replace("\\", "/")

            # Detect directory traversal
            if normalized.startswith("..") or "/../" in normalized:
                raise PathValidationError(f"Path traversal attempt detected: {target_path}")

            # If permissions are configured, check against sandbox roots
            if self._path_permissions:
                is_allowed = False
                for perm in self._path_permissions:
                    allowed_norm = os.path.normpath(perm.allowed_root_path).replace("\\", "/")

                    # Simple prefix check
                    if normalized.startswith(allowed_norm):
                        # Ensure we match boundaries (e.g. /tmp/foo matches /tmp/foo/bar but not /tmp/foobar)
                        if len(normalized) == len(allowed_norm) or normalized[len(allowed_norm)] == "/":
                            is_allowed = True
                            break

                if not is_allowed:
                    raise PathValidationError(f"Path '{target_path}' is outside sandboxed roots.")

            return True

    def validate_command(self, command_line: str) -> bool:
        """Verify command arguments and structure to prevent shell injections.

        Raises:
            CommandValidationError: If invalid arguments or injects detected.
        """
        if not command_line or not command_line.strip():
            raise CommandValidationError("Empty command line.")

        with self._lock:
            # Shell metacharacter detection
            injections = [";", "&&", "||", "|", "`", "$(", ">", "<", "\n"]
            for inj in injections:
                if inj in command_line:
                    raise CommandValidationError(f"Shell injection metacharacter '{inj}' detected.")

            parts = command_line.split()
            executable = parts[0]

            if self._command_definitions:
                matched = False
                for cmd in self._command_definitions:
                    if cmd.executable == executable:
                        # Check argument regex constraints if specified
                        if cmd.allowed_arguments_patterns:
                            args = parts[1:]
                            for arg in args:
                                arg_allowed = False
                                for pattern in cmd.allowed_arguments_patterns:
                                    if re.match(pattern, arg):
                                        arg_allowed = True
                                        break
                                if not arg_allowed:
                                    raise CommandValidationError(
                                        f"Argument '{arg}' violates safety patterns for '{executable}'."
                                    )
                        matched = True
                        break

                if not matched:
                    raise CommandValidationError(f"Executable '{executable}' is not authorized.")

            return True
