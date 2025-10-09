import json
import platform

from . import _version

__version__ = _version.pyslim_version


def slim_provenance_version(provenance):
    """
    Parses a provenance record, returning whether the record is a SLiM
    provenance entry, and version is the file format version, or "unknown" if
    it is not a SLiM entry.

    :param Provenance provenance: The provenance entry, as for instance obtained
        from ts.provenance(0).
    :return: A (bool, string) tuple (is_slim, version).
    """
    record = json.loads(provenance.record)
    software = record.get("software", {})
    software_name = software.get("name", record.get("program", "unknown"))
    file_version = "unknown"

    if software_name == "SLiM":
        slim_info = record.get("slim", {})
        file_version = slim_info.get("file_version", file_version)
    else:
        file_version = record.get("file_version", file_version)
    is_slim = software_name == "SLiM"
    return is_slim, file_version


def get_environment():
    """
    Returns a dictionary describing the environment in which we are
    currently running.
    """
    env = {
        "libraries": {},
        "parameters": {"command": []},
        "os": {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version_tuple(),
        },
    }
    return env


def make_pyslim_provenance_dict():
    """
    Returns a dictionary encoding the information about this version of pyslim.
    """
    document = {
        "schema_version": "1.0.0",
        "software": {
            "name": "pyslim",
            "version": __version__,
        },
        "parameters": {"command": {}},
        "environment": get_environment(),
    }
    return document
