import logging
from core.services.base import CoreService, ServiceMode

logger = logging.getLogger(__name__)


class UserDefined(CoreService):
    """Service that allows the GUI to supply arbitrary files, private directories, and startup commands.
    The GUI populates:
        - ``files`` and ``custom_templates`` for file creation
        - ``private_dirs`` for directory creation (handled by ``create_dirs``)
        - ``startup`` for commands to run on node start
    """

    name = "UserDefined"
    group = "custom"
    # Filled by the GUI at runtime
    files: list[str] = []
    private_dirs: list[str] = []
    startup: list[str] = []
    # validation can be left empty or populated by the GUI if desired
    validate: list[str] = []
    shutdown: list[str] = []
    validation_mode = ServiceMode.NON_BLOCKING
