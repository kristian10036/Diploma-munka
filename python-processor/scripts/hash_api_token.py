#!/usr/bin/env python3
from __future__ import annotations

import getpass
import hashlib

token = getpass.getpass("API token (will not be echoed): ")
if len(token) < 24:
    raise SystemExit("Use a randomly generated token of at least 24 characters.")
print(hashlib.sha256(token.encode("utf-8")).hexdigest())
