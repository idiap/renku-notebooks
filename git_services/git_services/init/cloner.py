import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from shutil import disk_usage
from time import sleep
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests

from git_services.cli import GitCLI, GitCommandError
from git_services.init import errors
from git_services.init.config import User


@dataclass
class Repository:
    """Information required to clone a repository."""

    namespace: str
    project: str
    branch: str
    commit_sha: str
    url: str
    absolute_path: Path
    _git_cli: Optional[GitCLI] = None

    @classmethod
    def from_dict(cls, data: Dict[str, str], workspace_mount_path: Path) -> "Repository":
        return cls(
            namespace=data["namespace"],
            project=data["project"],
            branch=data["branch"],
            commit_sha=data["commit_sha"],
            url=data["url"],
            absolute_path=workspace_mount_path / data["project"],
        )

    @property
    def git_cli(self) -> GitCLI:
        if not self._git_cli:
            if not self.absolute_path.exists():
                logging.info(f"{self.absolute_path} does not exist, creating it.")
                self.absolute_path.mkdir(parents=True, exist_ok=True)

            self._git_cli = GitCLI(self.absolute_path)

        return self._git_cli

    def exists(self) -> bool:
        try:
            is_inside = self.git_cli.git_rev_parse("--is-inside-work-tree")
        except GitCommandError:
            return False
        return is_inside.lower().strip() == "true"


class GitCloner:
    remote_name = "origin"
    remote_origin_prefix = f"remotes/{remote_name}"
    proxy_url = "http://localhost:8080"

    def __init__(
        self,
        repositories: List[Dict[str, str]],
        workspace_mount_path: str,
        user: User,
        repository_url: str,
        lfs_auto_fetch=False,
    ):
        base_path = Path(workspace_mount_path)
        logging.basicConfig(level=logging.INFO)
        self.repositories: List[Repository] = [
            Repository.from_dict(r, workspace_mount_path=base_path) for r in repositories
        ]
        self.workspace_mount_path = Path(workspace_mount_path)
        self.user = user
        self.repository_url = repository_url
        self.lfs_auto_fetch = lfs_auto_fetch
        self._wait_for_server()

    def _wait_for_server(self, timeout_minutes=None):
        if not self.repositories:
            return
        start = datetime.now()

        while True:
            logging.info(
                f"Waiting for git to become available with timeout minutes {timeout_minutes}..."
            )
            res = requests.get(self.repository_url)
            if 200 <= res.status_code < 400:
                logging.info("Git is available")
                return
            if timeout_minutes is not None:
                timeout_delta = timedelta(minutes=timeout_minutes)
                if datetime.now() - start > timeout_delta:
                    raise errors.GitServerUnavailableError
            sleep(5)

    def _initialize_repo(self, repository: Repository):
        logging.info("Initializing repo")

        repository.git_cli.git_init()

        # NOTE: For anonymous sessions email and name are not known for the user
        if self.user.email is not None:
            logging.info(f"Setting email {self.user.email} in git config")
            repository.git_cli.git_config("user.email", self.user.email)
        if self.user.full_name is not None:
            logging.info(f"Setting name {self.user.full_name} in git config")
            repository.git_cli.git_config("user.name", self.user.full_name)
        repository.git_cli.git_config("push.default", "simple")

    @staticmethod
    def _exclude_storages_from_git(repository: Repository, storages: List[str]):
        """Git ignore cloud storage mount folders."""
        if not storages:
            return

        with open(repository.absolute_path / ".git" / "info" / "exclude", "a") as exclude_file:
            exclude_file.write("\n")

            for storage in storages:
                storage_path = Path(storage)
                if repository.absolute_path not in storage_path.parents:
                    # The storage path is not inside the repo, no need to gitignore
                    continue
                exclude_path = storage_path.relative_to(repository.absolute_path).as_posix()
                exclude_file.write(f"{exclude_path}\n")

    @contextmanager
    def _temp_plaintext_credentials(self, repository: Repository):
        # NOTE: If "lfs." is included in urljoin it does not work properly
        lfs_auth_setting = "lfs." + urljoin(f"{repository.url}/", "info/lfs.access")
        credential_loc = Path("/tmp/git-credentials")
        try:
            with open(credential_loc, "w") as f:
                git_host = urlparse(repository.url).netloc
                f.write(f"https://oauth2:{self.user.oauth_token}@{git_host}")
            # NOTE: This is required to let LFS know that it should use basic auth to pull data.
            # If not set LFS will try to pull data without any auth and will then set this field
            # automatically but the password and username will be required for every git
            # operation. Setting this option when basic auth is used to clone with the context
            # manager and then unsetting it prevents getting in trouble when the user is in the
            # session by having this setting left over in the session after initialization.
            repository.git_cli.git_config(lfs_auth_setting, "basic")
            yield repository.git_cli.git_config(
                "credential.helper", f"store --file={credential_loc}"
            )
        finally:
            # NOTE: Temp credentials MUST be cleaned up on context manager exit
            logging.info("Cleaning up git credentials after cloning.")
            credential_loc.unlink(missing_ok=True)
            try:
                repository.git_cli.git_config("--unset", "credential.helper")
                repository.git_cli.git_config("--unset", lfs_auth_setting)
            except GitCommandError as err:
                # INFO: The repo is fully deleted when an error occurs so when the context
                # manager exits then this results in an unnecessary error that masks the true
                # error, that is why this is ignored.
                logging.warning(
                    "Git plaintext credentials were deleted but could not be "
                    "unset in the repository's config, most likely because the repository has "
                    f"been deleted. Detailed error: {err}"
                )

    @staticmethod
    def _get_lfs_total_size_bytes(repository) -> int:
        """Get the total size of all LFS files in bytes."""
        try:
            res = repository.git_cli.git_lfs("ls-files", "--json")
        except GitCommandError:
            return 0
        res_json = json.loads(res)
        size_bytes = 0
        files = res_json.get("files", [])
        if not files:
            return 0
        for f in files:
            size_bytes += f.get("size", 0)
        return size_bytes

    def _clone(self, repository: Repository):
        logging.info(f"Cloning branch {repository.branch}")
        if self.lfs_auto_fetch:
            repository.git_cli.git_lfs("install", "--local")
        else:
            repository.git_cli.git_lfs("install", "--skip-smudge", "--local")
        repository.git_cli.git_remote("add", self.remote_name, repository.url)
        repository.git_cli.git_fetch(self.remote_name)
        try:
            repository.git_cli.git_checkout(repository.branch)
        except GitCommandError as err:
            if err.returncode != 0 or len(err.stderr) != 0:
                if "no space left on device" in str(err.stderr).lower():
                    # INFO: not enough disk space
                    raise errors.NoDiskSpaceError from err
                else:
                    raise errors.BranchDoesNotExistError from err
        if self.lfs_auto_fetch:
            total_lfs_size_bytes = self._get_lfs_total_size_bytes(repository)
            _, _, free_space_bytes = disk_usage(repository.absolute_path.as_posix())
            if free_space_bytes < total_lfs_size_bytes:
                raise errors.NoDiskSpaceError
            repository.git_cli.git_lfs("install", "--local")
            repository.git_cli.git_lfs("pull")
        try:
            logging.info("Dealing with submodules")
            repository.git_cli.git_submodule("init")
            repository.git_cli.git_submodule("update")
        except GitCommandError as err:
            logging.error(msg="Couldn't initialize submodules", exc_info=err)

    def run(self, storage_mounts: List[str]):
        for repository in self.repositories:
            self.run_helper(repository, storage_mounts=storage_mounts)

    def run_helper(self, repository: Repository, *, storage_mounts: List[str]):
        logging.info("Checking if the repo already exists.")
        if repository.exists():
            # NOTE: This will run when a session is resumed, removing the repo here
            # will result in lost work if there is uncommitted work.
            logging.info("The repo already exists - exiting.")
            return
        self._initialize_repo(repository)
        if self.user.is_anonymous:
            self._clone(repository)
            repository.git_cli.git_reset("--hard", repository.commit_sha)
        else:
            with self._temp_plaintext_credentials(repository):
                self._clone(repository)

        # NOTE: If the storage mount location already exists it means that the repo folder/file
        # or another existing file will be overwritten, so raise an error here and crash.
        for a_mount in storage_mounts:
            if Path(a_mount).exists():
                raise errors.CloudStorageOverwritesExistingFilesError

        logging.info(f"Excluding cloud storage from git: {storage_mounts} for {repository}")
        if storage_mounts:
            self._exclude_storages_from_git(repository, storage_mounts)

        self._setup_proxy(repository)

    def _setup_proxy(self, repository: Repository):
        logging.info(f"Setting up git proxy to {self.proxy_url}")
        repository.git_cli.git_config("http.proxy", self.proxy_url)
        repository.git_cli.git_config("http.sslVerify", "false")
