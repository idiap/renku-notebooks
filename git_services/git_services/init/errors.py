import sys
import traceback


class GitCloneGenericError(Exception):
    """A generic error class that is the parent class of all API errors raised
    by the git clone module."""

    default_exit_code = 200

    def __init__(
        self,
        exit_code=default_exit_code,
    ):
        self.exit_code = exit_code


class GitServerUnavailableError(GitCloneGenericError):
    default_exit_code = 201


class UnexpectedAutosaveFormatError(GitCloneGenericError):
    default_exit_code = 202


class NoDiskSpaceError(GitCloneGenericError):
    default_exit_code = 203


class BranchDoesNotExistError(GitCloneGenericError):
    default_code = 204


class GitSubmoduleError(GitCloneGenericError):
    default_code = 205


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, GitCloneGenericError):
        # INFO: The process failed in a specific way that should be distinguished to the user.
        # The user can take action to correct the failure.
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        sys.exit(exc_value.exit_code)
    else:
        # INFO: A git command failed in a way that does not need to be distinguished to the user.
        # Indicates that something failed in the Git commands but knowing how or what is not
        # useful to the end user of the session and the user cannot correct this.
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        sys.exit(200)