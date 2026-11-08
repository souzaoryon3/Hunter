"""Segredos operacionais locais protegidos por DPAPI, nunca registrados em logs."""

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def protect(data, *, decrypt=False, machine=False):
    if os.name != "nt":
        raise RuntimeError(
            "Este cofre local exige Windows/DPAPI; containers recebem ambiente externo."
        )
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    function = getattr(
        ctypes.windll.crypt32, "CryptUnprotectData" if decrypt else "CryptProtectData"
    )
    if not function(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        1 | (4 if machine and not decrypt else 0),
        ctypes.byref(target),
    ):
        raise RuntimeError("Nao foi possivel acessar o cofre DPAPI deste usuario.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def read(name):
    return json.loads(protect((ROOT / ".secrets" / name).read_bytes(), decrypt=True))


def write(name, values, *, replace=False):
    directory = ROOT / ".secrets"
    directory.mkdir(exist_ok=True)
    path = directory / name
    encrypted = protect(json.dumps(values).encode())
    if replace:
        pending = path.with_suffix(".pending")
        with pending.open("xb") as stream:
            stream.write(encrypted)
        os.replace(pending, path)
    else:
        with path.open("xb") as stream:
            stream.write(encrypted)
    return path
