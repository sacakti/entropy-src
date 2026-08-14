# Hello Plugin — Release Notes

## Overview

The `builtin.hello` plugin allows workflows to print hello on the system where Entropy is running.

---

## Basic Usage

```json
{
    "name": "HelloPlugin Workflow",
    "version": "1.0.0",
    "description": "Example workflow for custom.hello.",

    "variables": {

    },

    "steps": [
        {
            "name": "Execute HelloPlugin",
            "plugin": "custom.hello",
            "enabled": true,
            "on_failure": false,
            "tags": [
                "hello"
            ],
            "arguments": {

            }
        }
    ]
}
```
