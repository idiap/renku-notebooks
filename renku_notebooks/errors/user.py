from dataclasses import dataclass

from .common import GenericError


@dataclass
class UserInputError(GenericError):
    """
    *Error codes: from 1000 to 1999*

    This category includes all the errors generated by user input. There is no unexpected
    error nor bugs here. The user should be able to address these issues.
    An example could be a wrong parameter (E.G. trying to access a non-existing repository,
    or a private repository without proper permissions).
    """

    message: str = "Invalid user input."
    code: int = 1000
    status_code: int = 422


@dataclass
class MissingResourceError(UserInputError):
    """Raised when any type of resource (either in k8s or outside of the cluster) does not
    exist but it is expected that it does exist. This is also raised when the user
    is trying to access resources that they do not have access to and an API that was called
    by the notebook service is responding simply with a 404 because the resource is private."""

    message: str
    code: int = UserInputError.code + 404
    status_code: int = 404


@dataclass
class AuthenticationError(UserInputError):
    """Raised when the user needs to be authenticated to access a specific resource. In some
    cases the notebook service can determine that a resource (possibly exists) but the user
    requires to be authenticated to reach it. That is when this error is called."""

    message: str = (
        "Accessing the requested resource requires authentication, please log in."
    )
    code: int = UserInputError.code + 401
    status_code: int = 401


@dataclass
class DuplicateS3BucketNamesError(UserInputError):
    """Raised when two or more buckets that are mounted in a session have duplicate names. This
    is not allowed because the bucket names are used as the mount points in the session."""

    message: str = "The names of all mounted S3 buckets should be unique."
    code: int = UserInputError.code + 1


@dataclass
class ImageParseError(UserInputError):
    """Raised when an invalid docker image name is provided. If the image name is valid
    but the image cannot be found a MissingResourceError is raised."""

    message: str = "The provided image name cannot be parsed."
    code: int = UserInputError.code + 2