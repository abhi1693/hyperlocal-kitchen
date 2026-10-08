"""Run migrations and tests using explicit test services or disposable Docker containers."""

import os
import subprocess
import sys
import time
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def command(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, env=env, check=True)


def docker_port(container: str, port: int) -> str:
    output = subprocess.check_output(
        ["docker", "port", container, f"{port}/tcp"], text=True
    ).strip()
    return output.rsplit(":", 1)[1]


def test_environment(database: str, redis: str) -> dict[str, str]:
    # Tests drop application tables and clear Redis: reject accidental production URLs.
    db_url = make_url(database)
    redis_url = make_url(redis)
    if db_url.drivername != "postgresql+psycopg" or not (db_url.database or "").endswith("_test"):
        raise ValueError("KITCHEN_TEST_DATABASE_URL must use PostgreSQL and a *_test database")
    if redis_url.drivername not in {"redis", "rediss"} or redis_url.database != "15":
        raise ValueError("KITCHEN_TEST_REDIS_URL must use a dedicated Redis database 15")
    return {
        **os.environ,
        "KITCHEN_ENVIRONMENT": "test",
        "KITCHEN_DATABASE_URL": database,
        "KITCHEN_TEST_DATABASE_URL": database,
        "KITCHEN_REDIS_URL": redis,
        "KITCHEN_COOKIE_SECURE": "true",
        "KITCHEN_OIDC_ISSUER_URL": "https://identity.example.test",
        "KITCHEN_OIDC_ORGANIZATION_ID": "test-org",
        "KITCHEN_ADMIN_OIDC_CLIENT_ID": "test-admin",
        "KITCHEN_USER_OIDC_CLIENT_ID": "test-resident",
        "KITCHEN_USER_BASE_URL": "https://user.example.test",
        "KITCHEN_ADMIN_BASE_URL": "https://admin.example.test",
        "KITCHEN_ADMIN_REQUIRED_ROLE": "platform_admin",
    }


def main() -> None:
    database = os.environ.get("KITCHEN_TEST_DATABASE_URL")
    redis = os.environ.get("KITCHEN_TEST_REDIS_URL")
    if bool(database) != bool(redis):
        raise ValueError(
            "Set both KITCHEN_TEST_DATABASE_URL and KITCHEN_TEST_REDIS_URL, or neither"
        )
    containers: list[str] = []
    try:
        if not database:
            # Random names and ports isolate simultaneous checks and developer services.
            prefix = "kitchen-check-" + uuid4().hex
            postgres, redis_container = prefix + "-postgres", prefix + "-redis"
            containers.append(postgres)
            command(
                "docker",
                "run",
                "--detach",
                "--name",
                postgres,
                "--publish",
                "127.0.0.1::5432",
                "--env",
                "POSTGRES_USER=ci",
                "--env",
                "POSTGRES_PASSWORD=ci",
                "--env",
                "POSTGRES_DB=kitchen_test",
                "--env",
                "TZ=UTC",
                "--env",
                "PGTZ=UTC",
                "--health-cmd",
                "pg_isready -U ci -d kitchen_test",
                "--health-interval",
                "1s",
                "--health-timeout",
                "5s",
                "--health-retries",
                "60",
                "postgres:17-alpine",
            )
            containers.append(redis_container)
            command(
                "docker",
                "run",
                "--detach",
                "--name",
                redis_container,
                "--publish",
                "127.0.0.1::6379",
                "--health-cmd",
                "redis-cli ping",
                "--health-interval",
                "1s",
                "--health-timeout",
                "5s",
                "--health-retries",
                "60",
                "redis:8-alpine",
            )
            for container in containers:
                # Poll health without a shell; stop after a bounded wait.
                for _ in range(90):
                    health = subprocess.check_output(
                        ["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
                        text=True,
                    ).strip()
                    if health == "healthy":
                        break
                    if health == "unhealthy":
                        raise RuntimeError(f"Test container {container} is unhealthy")
                    time.sleep(1)
                else:
                    raise RuntimeError(f"Timed out waiting for test container {container}")
            database = (
                "postgresql+psycopg://ci:ci@127.0.0.1:"
                + docker_port(postgres, 5432)
                + "/kitchen_test"
            )
            redis = "redis://127.0.0.1:" + docker_port(redis_container, 6379) + "/15"
        assert database is not None and redis is not None
        test_environment(database, redis)  # Validate destinations before any database mutation.
        schema = "commit_check_" + uuid4().hex
        engine = create_engine(database)
        try:
            with engine.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            url = make_url(database)
            options = str(url.query.get("options", "")) + f" -csearch_path={schema}"
            isolated_database = url.update_query_dict({"options": options.strip()})
            env = test_environment(isolated_database.render_as_string(hide_password=False), redis)
            for args in (("upgrade", "head"), ("upgrade", "head"), ("check",)):
                command(sys.executable, "-m", "alembic", *args, env=env)
            command(sys.executable, "-m", "pytest", "-q", *sys.argv[1:], env=env)
        finally:
            try:
                with engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            finally:
                engine.dispose()
    finally:
        for container in reversed(containers):
            subprocess.run(["docker", "rm", "--force", "--volumes", container], check=False)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        print(
            f"Backend checks failed: {error}. Docker must be available or supply test URLs.",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
