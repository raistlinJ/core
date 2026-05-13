import logging
from core.services.base import CoreService, ServiceMode

logger = logging.getLogger(__name__)


class UserDefined(CoreService):
    """Service that allows the GUI to supply arbitrary files, private directories,
    and startup commands.

    The GUI populates:
        - ``files`` and ``custom_templates`` for file creation
        - ``directories`` for directory creation
        - ``startup`` for commands to run on node start
        - ``validate`` for commands to run during validation
        - ``shutdown`` for commands to run on stop
    """

    name = "UserDefined"
    group = "custom"
    # Default empty lists - GUI will populate these at runtime
    directories: list[str] = []
    files: list[str] = []
    startup: list[str] = []
    validate: list[str] = []
    shutdown: list[str] = []
    validation_mode = ServiceMode.NON_BLOCKING
