"""Insecure deserialization sample."""
import pickle
import yaml


def load_session(data: bytes):
    return pickle.loads(data)


def load_config(yaml_str: str):
    return yaml.load(yaml_str, Loader=yaml.Loader)


def restore_cache(serialized: bytes):
    obj = pickle.loads(serialized)
    return obj
