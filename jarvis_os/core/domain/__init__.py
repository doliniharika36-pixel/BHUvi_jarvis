"""
Domain Layer for Jarvis OS Core.
"""
from jarvis_os.core.domain.exceptions import (
    JarvisException,
    DIResolutionError,
    ConfigurationError,
    SecurityException,
    UnauthorizedError,
    PathValidationError,
    CommandValidationError,
    RepositoryException,
    LLMException,
    EventBusException,
    SubsystemError,
    PerformanceThresholdExceeded,
)

from jarvis_os.core.domain.entities import (
    ConfigEntry,
    LogRecord,
    SubsystemStatus,
    MetricSample,
    LLMMessage,
    LLMResponse,
)

from jarvis_os.core.domain.value_objects import (
    SystemResourceUsage,
    PathPermission,
    CommandDefinition,
    UserIdentity,
)

from jarvis_os.core.domain.events import (
    DomainEvent,
    SystemBootstrappedEvent,
    SystemShutdownEvent,
    ConfigurationChangedEvent,
    SubsystemHealthChangedEvent,
    SecurityViolationEvent,
    PerformanceAlertEvent,
    LLMQueryExecutedEvent,
)
