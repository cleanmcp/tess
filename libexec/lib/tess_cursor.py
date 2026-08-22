#!/usr/bin/env python3
"""Cursor agent CLI helpers — model slug + bracket overrides for `agent --model`."""
import re

HCOM_TOOL = "cursor-agent"
CLI_BIN = "agent"
INSTALL_HINT = "https://cursor.com/docs/agent/cli"

EFFORT = {
    "none": "none", "off": "none", "min": "none", "zero": "none",
    "low": "low",
    "medium": "medium", "med": "medium",
    "high": "high",
    "xhigh": "xhigh", "extra-high": "xhigh", "extrahigh": "xhigh", "extra_high": "xhigh",
    "max": "max",
}

CONTEXT = {
    "272k": "272k", "272K": "272k",
    "1m": "1m", "1M": "1m",
}


def normalize_context(value):
    if not value:
        return None
    v = value.strip()
    return CONTEXT.get(v, v.lower())


def normalize_effort(value):
    if not value:
        return None
    key = value.strip().lower().replace("_", "-")
    return EFFORT.get(key, key)


def parse_overrides(model):
    """Split 'slug[k=v,...]' -> (slug, {k: v})."""
    m = re.match(r"^([^[\]]+)(?:\[(.*)\])?$", (model or "").strip())
    if not m:
        return (model or "").strip(), {}
    slug = m.group(1).strip()
    params = {}
    if m.group(2):
        for part in m.group(2).split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                params[k.strip()] = v.strip()
    return slug, params


def build_model(base=None, context=None, effort=None, fast=None):
    """Build the full `agent --model` string with bracket overrides.

    Matches Cursor's UI: Context (272K / 1M), Reasoning (none→max), Fast toggle.
    Note: the CLI param is `reasoning=` (not effort=) — tess --effort maps to it.
    Example: build_model('gpt-5.6-sol', context='1m', effort='max', fast=False)
             -> 'gpt-5.6-sol[context=1m,reasoning=max,fast=false]'
    """
    slug, params = parse_overrides(base or "auto")
    if context is not None:
        params["context"] = normalize_context(context)
    if effort is not None:
        params["reasoning"] = normalize_effort(effort)
    if fast is not None:
        params["fast"] = "true" if fast else "false"
    if params:
        inner = ",".join(f"{k}={v}" for k, v in params.items())
        return f"{slug}[{inner}]"
    return slug or None
