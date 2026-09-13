import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Component:
    id: str
    name: str
    component_type: str  # database, cache, queue, storage, auth, api, service, external
    technology: str
    evidence_file: str
    evidence_line: int | None = None
    detail: str = ""


@dataclass
class Connection:
    source_id: str
    target_id: str
    connection_type: str
    label: str
    evidence_file: str
    evidence_line: int | None = None


@dataclass
class InfraScanResult:
    components: list[Component] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)


# technology_key -> (display_name, component_type, patterns)
TECH_SIGNATURES: dict[str, tuple[str, str, dict[str, list[str]]]] = {
    "postgresql": ("PostgreSQL", "database", {
        "imports": ["psycopg2", "asyncpg", "psycopg", "pg8000"],
        "packages": ["psycopg2-binary", "asyncpg", "psycopg"],
        "urls": [r"postgresql://", r"postgres://"],
        "keywords": ["postgresql", "postgres"],
    }),
    "mysql": ("MySQL", "database", {
        "imports": ["pymysql", "mysql.connector", "MySQLdb", "aiomysql"],
        "packages": ["pymysql", "mysql-connector-python", "aiomysql"],
        "urls": [r"mysql://", r"mysql\+"],
        "keywords": ["mysql", "mariadb"],
    }),
    "mongodb": ("MongoDB", "database", {
        "imports": ["pymongo", "motor", "mongoengine"],
        "packages": ["pymongo", "motor", "mongoengine"],
        "urls": [r"mongodb://", r"mongodb\+srv://"],
        "keywords": ["mongodb", "mongo"],
    }),
    "sqlite": ("SQLite", "database", {
        "imports": ["sqlite3"],
        "packages": [],
        "urls": [r"sqlite://"],
        "keywords": ["sqlite"],
    }),
    "redis": ("Redis", "cache", {
        "imports": ["redis", "aioredis", "aredis"],
        "packages": ["redis", "aioredis"],
        "urls": [r"redis://", r"rediss://"],
        "keywords": ["redis"],
    }),
    "elasticsearch": ("Elasticsearch", "search", {
        "imports": ["elasticsearch", "opensearchpy"],
        "packages": ["elasticsearch", "opensearch-py"],
        "urls": [r"elasticsearch://", r"https?://.*:9200"],
        "keywords": ["elasticsearch", "opensearch"],
    }),
    "kafka": ("Apache Kafka", "queue", {
        "imports": ["kafka", "confluent_kafka", "aiokafka"],
        "packages": ["kafka-python", "confluent-kafka", "aiokafka"],
        "urls": [r"kafka://"],
        "keywords": ["kafka"],
    }),
    "rabbitmq": ("RabbitMQ", "queue", {
        "imports": ["pika", "aio_pika", "amqp"],
        "packages": ["pika", "aio-pika", "celery"],
        "urls": [r"amqp://", r"amqps://"],
        "keywords": ["rabbitmq", "amqp"],
    }),
    "celery": ("Celery", "queue", {
        "imports": ["celery"],
        "packages": ["celery"],
        "urls": [],
        "keywords": ["celery", "broker_url"],
    }),
    "s3": ("AWS S3", "storage", {
        "imports": ["boto3", "botocore", "aioboto3"],
        "packages": ["boto3", "aioboto3"],
        "urls": [r"s3://"],
        "keywords": ["s3", "aws_access_key"],
    }),
    "sqlalchemy": ("SQLAlchemy ORM", "orm", {
        "imports": ["sqlalchemy"],
        "packages": ["sqlalchemy"],
        "urls": [],
        "keywords": ["sqlalchemy", "create_engine", "sessionmaker"],
    }),
    "django_orm": ("Django ORM", "orm", {
        "imports": ["django.db"],
        "packages": ["django"],
        "urls": [],
        "keywords": ["django.db.models", "DATABASES"],
    }),
    "prisma": ("Prisma ORM", "orm", {
        "imports": ["@prisma/client"],
        "packages": ["@prisma/client", "prisma"],
        "urls": [],
        "keywords": ["prisma"],
    }),
    "jwt": ("JWT Auth", "auth", {
        "imports": ["jwt", "jose", "PyJWT", "python-jose"],
        "packages": ["pyjwt", "python-jose", "jose"],
        "urls": [],
        "keywords": ["jwt", "bearer", "oauth2", "openid"],
    }),
    "keycloak": ("Keycloak", "auth", {
        "imports": ["keycloak"],
        "packages": ["python-keycloak"],
        "urls": [],
        "keywords": ["keycloak"],
    }),
    "graphql": ("GraphQL", "api", {
        "imports": ["graphene", "strawberry", "ariadne"],
        "packages": ["graphene", "strawberry-graphql", "ariadne"],
        "urls": [],
        "keywords": ["graphql"],
    }),
    "grpc": ("gRPC", "api", {
        "imports": ["grpc"],
        "packages": ["grpcio", "grpc"],
        "urls": [],
        "keywords": ["grpc"],
    }),
}

ORM_TO_DB = {
    "sqlalchemy": ["postgresql", "mysql", "sqlite"],
    "django_orm": ["postgresql", "mysql", "sqlite"],
    "prisma": ["postgresql", "mysql", "mongodb", "sqlite"],
}

SKIP_SCAN_FILES = {
    "server/indexer/infra_scanner.py",
    "infra_scanner.py",
}

CONFIG_FILES = {
    ".env",
    ".env.example",
    ".env.local",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "settings.py",
    "config.py",
    "application.yml",
    "application.yaml",
    "application.properties",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
}


def scan_infrastructure(root: Path, file_paths: list[Path]) -> InfraScanResult:
    result = InfraScanResult()
    detected_tech: dict[str, Component] = {}

    all_paths = list(file_paths)
    for name in CONFIG_FILES:
        p = root / name
        if p.exists() and p not in all_paths:
            all_paths.append(p)

    for file_path in all_paths:
        if not file_path.exists() or file_path.is_dir():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        try:
            rel = str(file_path.relative_to(root))
        except ValueError:
            rel = file_path.name
        if rel in SKIP_SCAN_FILES or rel.endswith("infra_scanner.py"):
            continue
        is_config = file_path.name in CONFIG_FILES or rel in CONFIG_FILES
        _scan_content(content, rel, detected_tech, is_config=is_config)

    # Always add application server if we found routes or entry points
    if not any(c.component_type == "api" for c in detected_tech.values()):
        detected_tech["app_server"] = Component(
            id="app_server",
            name="Application Server",
            component_type="api",
            technology="Application",
            evidence_file="",
            detail="Main application runtime",
        )

    # Client node
    result.components.append(
        Component(
            id="client",
            name="Client / User",
            component_type="external",
            technology="HTTP Client",
            evidence_file="",
            detail="External users or API consumers",
        )
    )

    for comp in detected_tech.values():
        result.components.append(comp)

    _infer_connections(result)
    return result


def _scan_content(content: str, file_path: str, detected: dict[str, Component], is_config: bool = False) -> None:
    content_lower = content.lower()

    for tech_key, (display_name, comp_type, patterns) in TECH_SIGNATURES.items():
        if tech_key in detected:
            continue

        matched = False
        evidence_line = None
        match_strength = 0

        for imp in patterns.get("imports", []):
            if re.search(rf"(?:import|from)\s+{re.escape(imp)}\b", content):
                matched = True
                match_strength = 3
                evidence_line = _find_line(content, imp)
                break
            if re.search(rf"require\(['\"]{re.escape(imp)}['\"]\)", content):
                matched = True
                match_strength = 3
                evidence_line = _find_line(content, imp)
                break

        if not matched:
            for url_pat in patterns.get("urls", []):
                if re.search(url_pat, content, re.IGNORECASE):
                    matched = True
                    match_strength = 3
                    evidence_line = _find_line_regex(content, url_pat)
                    break

        if not matched and is_config:
            for pkg in patterns.get("packages", []):
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    matched = True
                    match_strength = 2
                    evidence_line = _find_line(content, pkg)
                    break

        if not matched and is_config:
            for kw in patterns.get("keywords", []):
                if re.search(rf"\b{re.escape(kw)}\b", content_lower):
                    matched = True
                    match_strength = 1
                    evidence_line = _find_line(content, kw)
                    break

        # Source files: only strong signals (imports, urls), skip weak keyword-only matches
        if matched and not is_config and match_strength < 2:
            matched = False

        if matched:
            detected[tech_key] = Component(
                id=tech_key,
                name=display_name,
                component_type=comp_type,
                technology=display_name,
                evidence_file=file_path,
                evidence_line=evidence_line,
                detail=f"Detected from {file_path}",
            )


def _find_line(content: str, needle: str) -> int | None:
    for i, line in enumerate(content.splitlines(), start=1):
        if needle.lower() in line.lower():
            return i
    return None


def _find_line_regex(content: str, pattern: str) -> int | None:
    for i, line in enumerate(content.splitlines(), start=1):
        if re.search(pattern, line, re.IGNORECASE):
            return i
    return None


def _infer_connections(result: InfraScanResult) -> None:
    by_id = {c.id: c for c in result.components}

    api = next((c for c in result.components if c.component_type == "api"), None)
    if not api:
        api = Component(
            id="app_server",
            name="Application Server",
            component_type="api",
            technology="Application",
            evidence_file="",
        )
        result.components.append(api)
        by_id[api.id] = api

    # Client -> API
    result.connections.append(
        Connection("client", api.id, "http", "HTTP/REST requests", "")
    )

    auth = next((c for c in result.components if c.component_type == "auth"), None)
    if auth:
        result.connections.append(
            Connection(api.id, auth.id, "auth", "authenticates via", auth.evidence_file, auth.evidence_line)
        )
        result.connections.append(
            Connection("client", auth.id, "auth", "login / token", auth.evidence_file, auth.evidence_line)
        )

    databases = [c for c in result.components if c.component_type == "database"]
    caches = [c for c in result.components if c.component_type == "cache"]
    queues = [c for c in result.components if c.component_type == "queue"]
    orms = [c for c in result.components if c.component_type == "orm"]
    storage = [c for c in result.components if c.component_type == "storage"]
    search = [c for c in result.components if c.component_type == "search"]

    # ORM -> Database links
    for orm in orms:
        result.connections.append(
            Connection(api.id, orm.id, "orm", "uses ORM", orm.evidence_file, orm.evidence_line)
        )
        for db_key in ORM_TO_DB.get(orm.id, []):
            db = by_id.get(db_key)
            if db:
                result.connections.append(
                    Connection(orm.id, db.id, "sql", "queries / persists", db.evidence_file, db.evidence_line)
                )

    # Direct API -> Database if no ORM
    if not orms:
        for db in databases:
            result.connections.append(
                Connection(api.id, db.id, "sql", "reads / writes data", db.evidence_file, db.evidence_line)
            )

    for cache in caches:
        result.connections.append(
            Connection(api.id, cache.id, "cache", "caching / sessions", cache.evidence_file, cache.evidence_line)
        )

    for queue in queues:
        result.connections.append(
            Connection(api.id, queue.id, "async", "async tasks / events", queue.evidence_file, queue.evidence_line)
        )

    for store in storage:
        result.connections.append(
            Connection(api.id, store.id, "storage", "file / object storage", store.evidence_file, store.evidence_line)
        )

    for svc in search:
        result.connections.append(
            Connection(api.id, svc.id, "search", "full-text / log search", svc.evidence_file, svc.evidence_line)
        )
