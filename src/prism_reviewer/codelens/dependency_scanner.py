import os
import json
import re
from typing import Dict, Any, List
from ..core.logger import get_logger

logger = get_logger("prism_reviewer.codelens.dependency_scanner")


def parse_requirements_txt(file_path: str) -> Dict[str, Any]:
    """Parses requirements.txt file and identifies basic info/issues."""
    dependencies = []
    issues = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Match package name and version specifier
                # e.g., flask>=2.0.0 or requests==2.26.0
                match = re.match(r"^([a-zA-Z0-9_\-\[\]]+)(.*)$", line)
                if match:
                    pkg_name = match.group(1)
                    spec = match.group(2).strip()
                    dependencies.append({"name": pkg_name, "specifier": spec})
                    
                    if not spec or not ("==" in spec):
                        issues.append({
                            "severity": "warning",
                            "message": f"Dependency '{pkg_name}' is not pinned to a specific version (specifier: '{spec}')."
                        })
                else:
                    dependencies.append({"name": line, "specifier": ""})
    except Exception as e:
        logger.error(f"Error parsing requirements.txt: {e}")
        issues.append({"severity": "error", "message": f"Failed to parse requirements.txt: {str(e)}"})
        
    return {"file": file_path, "dependencies": dependencies, "issues": issues}


def parse_package_json(file_path: str) -> Dict[str, Any]:
    """Parses package.json and identifies basic info/issues."""
    dependencies = []
    issues = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
            
        for deptype in ["dependencies", "devDependencies"]:
            if deptype in data and isinstance(data[deptype], dict):
                for pkg_name, spec in data[deptype].items():
                    dependencies.append({"name": pkg_name, "specifier": spec, "type": deptype})
                    # Warn about open ranges like * or ^ or ~ which are common but good to report
                    if spec == "*":
                        issues.append({
                            "severity": "warning",
                            "message": f"Dependency '{pkg_name}' in {deptype} has version set to '*'"
                        })
    except Exception as e:
        logger.error(f"Error parsing package.json: {e}")
        issues.append({"severity": "error", "message": f"Failed to parse package.json: {str(e)}"})
        
    return {"file": file_path, "dependencies": dependencies, "issues": issues}


def parse_pyproject_toml(file_path: str) -> Dict[str, Any]:
    """Parses pyproject.toml using standard library tomllib (Python 3.11+) or basic regex fallback."""
    dependencies = []
    issues = []
    content = ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        # Try to use standard tomllib or toml or tomli
        parsed = None
        try:
            import tomllib  # type: ignore
            parsed = tomllib.loads(content)
        except ImportError:
            try:
                import toml  # type: ignore
                parsed = toml.loads(content)
            except ImportError:
                try:
                    import tomli  # type: ignore
                    parsed = tomli.loads(content)
                except ImportError:
                    pass
                    
        if parsed is not None:
            # Poetry support
            poetry_deps = parsed.get("tool", {}).get("poetry", {}).get("dependencies", {})
            for pkg, spec in poetry_deps.items():
                if pkg != "python":
                    dependencies.append({"name": pkg, "specifier": str(spec)})
            # PEP 621 support
            project_deps = parsed.get("project", {}).get("dependencies", [])
            for dep in project_deps:
                match = re.match(r"^([a-zA-Z0-9_\-\[\]]+)(.*)$", dep)
                if match:
                    dependencies.append({"name": match.group(1), "specifier": match.group(2).strip()})
        else:
            # Fallback regex parser for basic pyproject.toml parsing
            # Matches lines like: requests = "^2.26.0" or requests = { version = "^2.26.0" }
            in_dependencies = False
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    in_dependencies = ("poetry.dependencies" in line or "project.dependencies" in line)
                    continue
                if in_dependencies and line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        pkg = parts[0].strip().strip('"').strip("'")
                        spec = parts[1].strip()
                        dependencies.append({"name": pkg, "specifier": spec})
    except Exception as e:
        logger.error(f"Error parsing pyproject.toml: {e}")
        issues.append({"severity": "error", "message": f"Failed to parse pyproject.toml: {str(e)}"})
        
    return {"file": file_path, "dependencies": dependencies, "issues": issues}


def scan_dependencies(repo_path: str) -> List[Dict[str, Any]]:
    """Scans all manifest files in the checkout folder and returns results."""
    results = []
    try:
        req_txt = os.path.join(repo_path, "requirements.txt")
        if os.path.isfile(req_txt):
            results.append(parse_requirements_txt(req_txt))
            
        pkg_json = os.path.join(repo_path, "package.json")
        if os.path.isfile(pkg_json):
            results.append(parse_package_json(pkg_json))
            
        pyproject = os.path.join(repo_path, "pyproject.toml")
        if os.path.isfile(pyproject):
            results.append(parse_pyproject_toml(pyproject))
    except Exception as e:
        logger.warning(f"Failed to scan dependencies in {repo_path}: {e}")
        
    return results
