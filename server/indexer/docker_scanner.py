import re
from pathlib import Path

import yaml

from server.indexer.infra_scanner import Component, Connection, InfraScanResult

COMPOSE_NAMES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

IMAGE_TO_TECH: dict[str, tuple[str, str, str]] = {
    "postgres": ("postgresql", "PostgreSQL", "database"),
    "mysql": ("mysql", "MySQL", "database"),
    "mariadb": ("mysql", "MariaDB", "database"),
    "mongo": ("mongodb", "MongoDB", "database"),
    "redis": ("redis", "Redis", "cache"),
    "rabbitmq": ("rabbitmq", "RabbitMQ", "queue"),
    "kafka": ("kafka", "Apache Kafka", "queue"),
    "elasticsearch": ("elasticsearch", "Elasticsearch", "search"),
    "nginx": ("nginx", "Nginx", "proxy"),
}


def scan_docker(root: Path) -> InfraScanResult:
    result = InfraScanResult()
    dockerfiles = _find_dockerfiles(root)
    compose_files = _find_compose_files(root)

    app_container_id = "docker_app"
    has_app = False

    for df in dockerfiles:
        rel = str(df.relative_to(root))
        info = _parse_dockerfile(df)
        if not has_app:
            result.components.append(
                Component(
                    id=app_container_id,
                    name="App Container",
                    component_type="container",
                    technology=info.get("base_image", "Docker"),
                    evidence_file=rel,
                    evidence_line=info.get("from_line"),
                    detail=f"Built from {info.get('base_image', 'Dockerfile')}",
                )
            )
            has_app = True
        for port in info.get("ports", []):
            result.connections.append(
                Connection(
                    "client",
                    app_container_id,
                    "http",
                    f"port {port}",
                    rel,
                    info.get("from_line"),
                )
            )

    compose_services: dict[str, dict] = {}
    for cf in compose_files:
        rel = str(cf.relative_to(root))
        services = _parse_compose(cf)
        for svc_name, svc in services.items():
            compose_services[svc_name] = {**svc, "evidence_file": rel}
            svc_id = f"docker_svc_{svc_name}"
            image = svc.get("image", "")
            tech_key, display, ctype = _classify_image(image)

            if svc_name in {"app", "api", "web", "backend", "server"} or "build" in svc:
                if not has_app:
                    result.components.append(
                        Component(
                            id=app_container_id,
                            name=svc_name,
                            component_type="container",
                            technology=image or "Docker build",
                            evidence_file=rel,
                            detail=f"Compose service: {svc_name}",
                        )
                    )
                    has_app = True
                else:
                    result.components.append(
                        Component(
                            id=svc_id,
                            name=svc_name,
                            component_type="container",
                            technology=image or "Docker build",
                            evidence_file=rel,
                            detail=f"Compose service: {svc_name}",
                        )
                    )
            elif tech_key:
                existing = next((c for c in result.components if c.id == tech_key), None)
                if not existing:
                    result.components.append(
                        Component(
                            id=tech_key,
                            name=display,
                            component_type=ctype,
                            technology=display,
                            evidence_file=rel,
                            detail=f"Docker image: {image}",
                        )
                    )
                result.components.append(
                    Component(
                        id=svc_id,
                        name=svc_name,
                        component_type="container",
                        technology=image,
                        evidence_file=rel,
                        detail=f"Compose service → {display}",
                    )
                )
            else:
                result.components.append(
                    Component(
                        id=svc_id,
                        name=svc_name,
                        component_type="container",
                        technology=image or svc_name,
                        evidence_file=rel,
                        detail="Docker Compose service",
                    )
                )

            for port in svc.get("ports", []):
                host_port = str(port).split(":")[0] if ":" in str(port) else str(port)
                result.connections.append(
                    Connection(
                        "client",
                        svc_id,
                        "network",
                        f"port {host_port}",
                        rel,
                        None,
                    )
                )

    # depends_on connections
    for svc_name, svc in compose_services.items():
        svc_id = f"docker_svc_{svc_name}"
        if svc_name in {"app", "api", "web", "backend", "server"}:
            svc_id = app_container_id if has_app else svc_id
        for dep in svc.get("depends_on", []):
            dep_id = f"docker_svc_{dep}"
            image = compose_services.get(dep, {}).get("image", "")
            tech_key, _, _ = _classify_image(image)
            target = tech_key or dep_id
            result.connections.append(
                Connection(
                    svc_id,
                    target,
                    "depends_on",
                    "depends on",
                    svc.get("evidence_file", ""),
                    None,
                )
            )

    if has_app:
        for comp in result.components:
            if comp.component_type == "database" and comp.id != app_container_id:
                result.connections.append(
                    Connection(
                        app_container_id,
                        comp.id,
                        "sql",
                        "connects to",
                        comp.evidence_file,
                        comp.evidence_line,
                    )
                )
            if comp.component_type == "cache" and comp.id != app_container_id:
                result.connections.append(
                    Connection(
                        app_container_id,
                        comp.id,
                        "cache",
                        "caching",
                        comp.evidence_file,
                        comp.evidence_line,
                    )
                )

    return result


def _find_dockerfiles(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("Dockerfile*"):
        if any(skip in path.parts for skip in {".git", "node_modules", "vendor"}):
            continue
        if path.is_file() and (path.name == "Dockerfile" or path.name.startswith("Dockerfile.")):
            found.append(path)
    return found[:10]


def _find_compose_files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in COMPOSE_NAMES:
            if not any(skip in path.parts for skip in {".git", "node_modules"}):
                found.append(path)
    return found[:5]


def _parse_dockerfile(path: Path) -> dict:
    info: dict = {"ports": [], "base_image": "", "from_line": None}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return info
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("FROM ") and not info["base_image"]:
            info["base_image"] = stripped[5:].split()[0]
            info["from_line"] = i
        if upper.startswith("EXPOSE "):
            for p in stripped[7:].split():
                if p.isdigit() or ":" in p:
                    info["ports"].append(p.split("/")[0].split(":")[-1])
    return info


def _parse_compose(path: Path) -> dict[str, dict]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    services = data.get("services", {})
    if not isinstance(services, dict):
        return {}
    result = {}
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        depends = svc.get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        ports = svc.get("ports", []) or []
        if isinstance(ports, list):
            ports = [str(p) for p in ports]
        result[name] = {
            "image": str(svc.get("image", "")),
            "build": svc.get("build"),
            "ports": ports,
            "depends_on": depends if isinstance(depends, list) else [],
        }
    return result


def _classify_image(image: str) -> tuple[str, str, str]:
    img = image.lower()
    for key, (tech_id, display, ctype) in IMAGE_TO_TECH.items():
        if key in img:
            return tech_id, display, ctype
    return "", image.split(":")[0] if image else "", "container"
