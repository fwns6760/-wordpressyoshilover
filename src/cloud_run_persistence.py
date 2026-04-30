"""GCS-backed state persistence helpers for Cloud Run jobs."""

from __future__ import annotations

import argparse
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from typing import Iterator, Sequence
from zoneinfo import ZoneInfo


DEFAULT_PROJECT_ID = "baseballsite"
DEFAULT_BUCKET_NAME = "baseballsite-yoshilover-state"
DEFAULT_PREFIX = "publish_notice"
DEFAULT_RUNNER_MODULE = "src.tools.run_publish_notice_email_dry_run"
DEFAULT_CURSOR_PATH = "/tmp/publish_notice_cursor.txt"
DEFAULT_HISTORY_PATH = "/tmp/publish_notice_history.json"
DEFAULT_QUEUE_PATH = "/tmp/publish_notice_queue.jsonl"
DEFAULT_GUARDED_PUBLISH_PREFIX = "guarded_publish"
DEFAULT_GUARDED_HISTORY_PATH = "/tmp/pub004d/guarded_publish_history.jsonl"
DEFAULT_GUARDED_HISTORY_CURSOR_PATH = "/tmp/pub004d/guarded_publish_history_cursor.txt"
DEFAULT_ARTIFACT_BUCKET_NAME = "yoshilover-history"
DEFAULT_ARTIFACT_PREFIX = "repair_artifacts"
JST = ZoneInfo("Asia/Tokyo")
_KEYWORD_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}|[一-龯ぁ-んァ-ヴー]{2,}")
_MISSING_OBJECT_MARKERS = (
    "No URLs matched",
    "NotFoundException",
    "One or more URLs matched no objects",
    "matched no objects or files",
    "404",
)


class GCSAccessError(RuntimeError):
    """Raised when Cloud Storage CLI access fails."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"gcloud storage access failed: {detail}")


def _decode_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _build_error_detail(stderr: str | bytes | None, stdout: str | bytes | None = None) -> str:
    detail = _decode_text(stderr).strip() or _decode_text(stdout).strip()
    return detail or "no stderr"


def _default_project_id() -> str:
    for key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "PROJECT_ID"):
        value = str(os.environ.get(key, "")).strip()
        if value:
            return value
    return DEFAULT_PROJECT_ID


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _path(value: str | os.PathLike[str]) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _extract_keywords(text: str) -> set[str]:
    return {
        token
        for token in _KEYWORD_PATTERN.findall(str(text or ""))
        if len(token.strip()) >= 2
    }


class GCSStateManager:
    """Persist local state files to a GCS bucket via gcloud storage."""

    def __init__(self, bucket_name: str, prefix: str, project_id: str = DEFAULT_PROJECT_ID) -> None:
        self.bucket_name = str(bucket_name).strip()
        self.prefix = str(prefix).strip().strip("/")
        self.project_id = str(project_id).strip()
        if not self.bucket_name:
            raise ValueError("bucket_name must not be empty")

    def _storage_base(self) -> list[str]:
        command = ["gcloud"]
        if self.project_id:
            command.extend(["--project", self.project_id])
        command.append("storage")
        return command

    def _remote_uri(self, remote_name: str) -> str:
        leaf = str(remote_name).strip().lstrip("/")
        if not leaf:
            raise ValueError("remote_name must not be empty")
        if self.prefix:
            return f"gs://{self.bucket_name}/{self.prefix}/{leaf}"
        return f"gs://{self.bucket_name}/{leaf}"

    def download(self, remote_name: str, local_path: str | os.PathLike[str]) -> bool:
        target = _path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [*self._storage_base(), "cp", self._remote_uri(remote_name), str(target), "--quiet"],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise GCSAccessError("gcloud CLI not found") from exc
        except subprocess.CalledProcessError as exc:
            detail = _build_error_detail(exc.stderr, exc.stdout)
            if any(marker in detail for marker in _MISSING_OBJECT_MARKERS):
                return False
            raise GCSAccessError(detail) from exc
        return True

    def upload(self, local_path: str | os.PathLike[str], remote_name: str) -> None:
        source = _path(local_path)
        if not source.exists():
            raise FileNotFoundError(f"local state file does not exist: {source}")
        temp_remote_name = f"{remote_name}.uploading-{uuid.uuid4().hex}"
        temp_uri = self._remote_uri(temp_remote_name)
        final_uri = self._remote_uri(remote_name)
        try:
            subprocess.run(
                [*self._storage_base(), "cp", str(source), temp_uri, "--quiet"],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                [*self._storage_base(), "mv", temp_uri, final_uri, "--quiet"],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise GCSAccessError("gcloud CLI not found") from exc
        except subprocess.CalledProcessError as exc:
            raise GCSAccessError(_build_error_detail(exc.stderr, exc.stdout)) from exc

    @contextmanager
    def with_state(
        self,
        remote_name: str,
        local_path: str | os.PathLike[str],
        *,
        upload_on_exit: bool = True,
    ) -> Iterator[bool]:
        downloaded = self.download(remote_name, local_path)
        try:
            yield downloaded
        finally:
            source = _path(local_path)
            if upload_on_exit and source.exists():
                self.upload(source, remote_name)


class ArtifactUploader:
    """Upload repair before/after artifacts to a dedicated GCS prefix."""

    def __init__(
        self,
        bucket_name: str = DEFAULT_ARTIFACT_BUCKET_NAME,
        prefix: str = DEFAULT_ARTIFACT_PREFIX,
        project_id: str | None = None,
    ) -> None:
        self.bucket_name = str(bucket_name).strip()
        self.prefix = str(prefix).strip().strip("/")
        self.project_id = str(project_id or _default_project_id()).strip()
        self.manager = GCSStateManager(
            bucket_name=self.bucket_name,
            prefix=self.prefix,
            project_id=self.project_id,
        )

    @staticmethod
    def compute_diff_summary(before: str, after: str) -> dict[str, object]:
        before_text = str(before or "")
        after_text = str(after or "")
        before_lines = [line for line in before_text.splitlines() if line.strip()]
        after_lines = [line for line in after_text.splitlines() if line.strip()]
        before_keywords = _extract_keywords(before_text)
        after_keywords = _extract_keywords(after_text)
        return {
            "line_count_before": len(before_lines),
            "line_count_after": len(after_lines),
            "line_count_delta": len(after_lines) - len(before_lines),
            "char_count_before": len(before_text),
            "char_count_after": len(after_text),
            "char_delta": len(after_text) - len(before_text),
            "added_keywords": sorted(after_keywords - before_keywords),
            "removed_keywords": sorted(before_keywords - after_keywords),
        }

    def upload(
        self,
        post_id: int | str,
        provider: str,
        run_id: str,
        before_body: str,
        after_body: str,
        extra_meta: dict[str, object] | None = None,
    ) -> str:
        current_date = _now_jst().date().isoformat()
        remote_name = f"{current_date}/{post_id}_{provider}_{run_id}.json"
        payload = {
            "post_id": post_id,
            "provider": provider,
            "run_id": run_id,
            "before_body": before_body,
            "after_body": after_body,
            "diff_summary": self.compute_diff_summary(before_body, after_body),
        }
        if extra_meta is not None:
            payload["extra_meta"] = dict(extra_meta)

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                suffix=".json",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                temp_path = Path(handle.name)
            self.manager.upload(temp_path, remote_name)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        return self.manager._remote_uri(remote_name)


def _parse_entrypoint_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore publish-notice state from GCS, run the job, then upload updated state.",
    )
    parser.add_argument("--bucket-name", default=os.environ.get("GCS_STATE_BUCKET", DEFAULT_BUCKET_NAME))
    parser.add_argument("--prefix", default=os.environ.get("GCS_STATE_PREFIX", DEFAULT_PREFIX))
    parser.add_argument("--project-id", default=_default_project_id())
    parser.add_argument("--runner-module", default=os.environ.get("PUBLISH_NOTICE_RUNNER_MODULE", DEFAULT_RUNNER_MODULE))
    parser.add_argument("--cursor-path", default=os.environ.get("PUBLISH_NOTICE_CURSOR_PATH", DEFAULT_CURSOR_PATH))
    parser.add_argument("--history-path", default=os.environ.get("PUBLISH_NOTICE_HISTORY_PATH", DEFAULT_HISTORY_PATH))
    parser.add_argument("--queue-path", default=os.environ.get("PUBLISH_NOTICE_QUEUE_PATH", DEFAULT_QUEUE_PATH))
    parser.add_argument(
        "--guarded-history-path",
        default=os.environ.get("PUBLISH_NOTICE_GUARDED_PUBLISH_HISTORY_PATH", DEFAULT_GUARDED_HISTORY_PATH),
    )
    parser.add_argument(
        "--guarded-history-cursor-path",
        default=os.environ.get(
            "PUBLISH_NOTICE_GUARDED_HISTORY_CURSOR_PATH",
            DEFAULT_GUARDED_HISTORY_CURSOR_PATH,
        ),
    )
    parser.add_argument("runner_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.runner_args and args.runner_args[0] == "--":
        args.runner_args = args.runner_args[1:]
    return args


def build_publish_notice_command(
    *,
    runner_module: str,
    cursor_path: str,
    history_path: str,
    queue_path: str,
    runner_args: Sequence[str] | None = None,
    python_executable: str | None = None,
) -> list[str]:
    command = [
        python_executable or sys.executable,
        "-m",
        runner_module,
        "--scan",
        "--send",
        "--cursor-path",
        cursor_path,
        "--history-path",
        history_path,
        "--queue-path",
        queue_path,
    ]
    if runner_args:
        command.extend(str(part) for part in runner_args)
    return command


def run_publish_notice_entrypoint(argv: Sequence[str] | None = None) -> int:
    args = _parse_entrypoint_args(argv)
    manager = GCSStateManager(
        bucket_name=args.bucket_name,
        prefix=args.prefix,
        project_id=args.project_id,
    )
    guarded_history_manager = GCSStateManager(
        bucket_name=args.bucket_name,
        prefix=DEFAULT_GUARDED_PUBLISH_PREFIX,
        project_id=args.project_id,
    )
    command = build_publish_notice_command(
        runner_module=args.runner_module,
        cursor_path=str(args.cursor_path),
        history_path=str(args.history_path),
        queue_path=str(args.queue_path),
        runner_args=args.runner_args,
    )
    with (
        manager.with_state("cursor.txt", args.cursor_path),
        manager.with_state("history.json", args.history_path),
        manager.with_state("queue.jsonl", args.queue_path),
        manager.with_state("guarded_publish_history_cursor.txt", args.guarded_history_cursor_path),
        guarded_history_manager.with_state(
            "guarded_publish_history.jsonl",
            args.guarded_history_path,
            upload_on_exit=False,
        ),
    ):
        completed = subprocess.run(command, check=False)
    return int(completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "entrypoint":
        print(
            "usage: python -m src.cloud_run_persistence entrypoint [entrypoint args...]",
            file=sys.stderr,
        )
        return 2

    try:
        return run_publish_notice_entrypoint(args[1:])
    except (GCSAccessError, subprocess.SubprocessError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
