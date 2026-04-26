"""Cloud Run Secret Manager-backed Codex auth lifecycle helpers."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


_AUTH_JSON_MASK = "[auth.json masked]"
_AUTH_CONTENT_MASK = "[REDACTED auth.json content]"
_AUTH_JSON_PATH_PATTERN = re.compile(r"(?:(?:~|/)[^\s\"']*auth\.json)|\bauth\.json\b")
_SECRET_FIELD_PATTERN = re.compile(
    r'"(?:refresh_token|access_token|id_token|token|tokens|auth_mode)"',
    re.IGNORECASE,
)

DEFAULT_SECRET_NAME = "codex-auth-json"
DEFAULT_PROJECT_ID = "baseballsite"
DEFAULT_CODEX_HOME = "/tmp/.codex"
DEFAULT_RUNNER_MODULE = "src.tools.run_draft_body_editor_lane"
DEFAULT_PROVIDER = "codex"
DEFAULT_MAX_POSTS = 3


class SecretAccessError(RuntimeError):
    """Raised when Secret Manager access fails."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"gcloud secret access failed: {detail}")


class SecretWritebackError(RuntimeError):
    """Raised when Secret Manager writeback fails."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"gcloud secret writeback failed: {detail}")


def _decode_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _sanitize_auth_text(text: str | bytes | None) -> str:
    decoded = _decode_text(text)
    if not decoded:
        return ""
    sanitized = _AUTH_JSON_PATH_PATTERN.sub(_AUTH_JSON_MASK, decoded)
    sanitized = sanitized.replace(str(Path("~/.codex/auth.json").expanduser().resolve()), _AUTH_JSON_MASK)
    sanitized = sanitized.replace("/tmp/.codex/auth.json", _AUTH_JSON_MASK)
    normalized = sanitized.strip()
    if not normalized:
        return ""
    if _SECRET_FIELD_PATTERN.search(normalized) or ("{" in normalized and "}" in normalized):
        return _AUTH_CONTENT_MASK
    return normalized


def _build_error_detail(text: str | bytes | None) -> str:
    detail = _sanitize_auth_text(text)
    return detail or "no stderr"


def _default_project_id() -> str:
    for key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "PROJECT_ID"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return DEFAULT_PROJECT_ID


def _default_max_posts() -> int:
    raw = os.environ.get("CODEX_SHADOW_MAX_POSTS", "").strip()
    if not raw:
        return DEFAULT_MAX_POSTS
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_MAX_POSTS
    return parsed if parsed > 0 else DEFAULT_MAX_POSTS


class SecretAuthManager:
    """Restore and write back Codex ChatGPT auth.json via Secret Manager."""

    def __init__(
        self,
        secret_name: str = DEFAULT_SECRET_NAME,
        project_id: str = DEFAULT_PROJECT_ID,
        codex_home: str | os.PathLike[str] = DEFAULT_CODEX_HOME,
    ) -> None:
        self.secret_name = secret_name
        self.project_id = project_id
        self.codex_home = Path(codex_home).expanduser().resolve()
        self.auth_path = self.codex_home / "auth.json"

    def _gcloud_base(self) -> list[str]:
        return ["gcloud", "--project", self.project_id]

    def restore(self) -> Path:
        self.codex_home.mkdir(parents=True, exist_ok=True)
        self.codex_home.chmod(0o700)
        try:
            completed = subprocess.run(
                [
                    *self._gcloud_base(),
                    "secrets",
                    "versions",
                    "access",
                    "latest",
                    "--secret",
                    self.secret_name,
                ],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise SecretAccessError("gcloud CLI not found") from exc
        except subprocess.CalledProcessError as exc:
            raise SecretAccessError(_build_error_detail(exc.stderr)) from exc

        stdout = completed.stdout
        payload = stdout if isinstance(stdout, bytes) else _decode_text(stdout).encode("utf-8")
        if not payload:
            raise SecretAccessError("gcloud secret access returned empty payload")

        fd, temp_name = tempfile.mkstemp(dir=self.codex_home, prefix=".auth.", suffix=".json")
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            temp_path.chmod(0o600)
            os.replace(temp_path, self.auth_path)
            self.auth_path.chmod(0o600)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return self.auth_path

    def compute_sha(self) -> str:
        return hashlib.sha256(self.auth_path.read_bytes()).hexdigest()

    def writeback_if_changed(self, sha_before: str) -> bool:
        try:
            current_sha = self.compute_sha()
        except FileNotFoundError as exc:
            raise SecretWritebackError("auth.json missing before writeback") from exc

        if current_sha == sha_before:
            return False

        try:
            subprocess.run(
                [
                    *self._gcloud_base(),
                    "secrets",
                    "versions",
                    "add",
                    self.secret_name,
                    "--data-file",
                    str(self.auth_path),
                ],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise SecretWritebackError("gcloud CLI not found") from exc
        except subprocess.CalledProcessError as exc:
            raise SecretWritebackError(_build_error_detail(exc.stderr)) from exc
        return True

    def cleanup(self) -> None:
        shutil.rmtree(self.codex_home, ignore_errors=True)


def _parse_entrypoint_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore Codex auth.json from Secret Manager, run the shadow lane, then write back refreshed auth.json.",
    )
    parser.add_argument("--secret-name", default=os.environ.get("CODEX_AUTH_SECRET_NAME", DEFAULT_SECRET_NAME))
    parser.add_argument("--project-id", default=_default_project_id())
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", DEFAULT_CODEX_HOME))
    parser.add_argument(
        "--runner-module",
        default=os.environ.get("CODEX_SHADOW_RUNNER_MODULE", DEFAULT_RUNNER_MODULE),
    )
    parser.add_argument("--provider", default=os.environ.get("CODEX_SHADOW_PROVIDER", DEFAULT_PROVIDER))
    parser.add_argument("--max-posts", type=int, default=_default_max_posts())
    parser.add_argument("runner_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.max_posts < 1:
        parser.error("--max-posts must be > 0")
    if args.runner_args and args.runner_args[0] == "--":
        args.runner_args = args.runner_args[1:]
    return args


def build_shadow_command(
    *,
    runner_module: str,
    provider: str,
    max_posts: int,
    runner_args: Sequence[str] | None = None,
    python_executable: str | None = None,
) -> list[str]:
    command = [
        python_executable or sys.executable,
        "-m",
        runner_module,
        "--provider",
        provider,
        "--max-posts",
        str(max_posts),
    ]
    if runner_args:
        command.extend(str(part) for part in runner_args)
    return command


def run_codex_shadow_entrypoint(argv: Sequence[str] | None = None) -> int:
    args = _parse_entrypoint_args(argv)
    manager = SecretAuthManager(
        secret_name=args.secret_name,
        project_id=args.project_id,
        codex_home=args.codex_home,
    )
    try:
        auth_path = manager.restore()
        sha_before = manager.compute_sha()
    except Exception:
        manager.cleanup()
        raise

    runner_env = os.environ.copy()
    runner_env["CODEX_HOME"] = str(auth_path.parent)
    command = build_shadow_command(
        runner_module=args.runner_module,
        provider=args.provider,
        max_posts=args.max_posts,
        runner_args=args.runner_args,
    )

    runner_error: BaseException | None = None
    runner_returncode = 1
    try:
        completed = subprocess.run(command, check=False, env=runner_env)
        runner_returncode = int(completed.returncode)
    except BaseException as exc:
        runner_error = exc

    try:
        manager.writeback_if_changed(sha_before)
    finally:
        manager.cleanup()

    if runner_error is not None:
        raise runner_error
    return runner_returncode


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "entrypoint":
        print(
            "usage: python -m src.cloud_run_secret_auth entrypoint [entrypoint args...]",
            file=sys.stderr,
        )
        return 2

    try:
        return run_codex_shadow_entrypoint(args[1:])
    except (SecretAccessError, SecretWritebackError, subprocess.SubprocessError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
