# Reverse engineering MCP

This optional server requires an explicitly configured SSH target.
The generic lab no longer provides a reverse workstation or a `reverse` Compose profile.
The example target is disabled, so the server cannot connect to a nonexistent default workstation.

Supply your own authorized target and configure its host, port, user, key, and container identity before enabling it.
The server continues to use the shared SSH validation and connection owner.
No lab data or existing Docker volume is removed by retiring the old Compose declarations.
