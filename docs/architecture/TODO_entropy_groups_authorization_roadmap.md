# Entropy -- Groups & Authorization Roadmap

## Context

The current framework supports user management, authentication,
sessions, and password management. Authorization is still implemented
through command-level checks. This is acceptable for the bootstrap phase
but is not scalable.

This feature is intentionally deferred because it requires database
schema changes and should be introduced through migrations.

------------------------------------------------------------------------

## Objectives

### 1. Introduce Groups

Create a new table:

``` text
groups
------
id
name
description
system
created_at
updated_at
```

Bootstrap group:

``` text
Administrators
```

------------------------------------------------------------------------

### 2. Associate Users

Extend the users table:

``` text
users
-----
...
group_id
```

Assign the existing administrator to the Administrators group.

------------------------------------------------------------------------

### 3. Group Manager

Responsibilities:

-   Create groups
-   Delete groups
-   Rename groups
-   List groups
-   Assign users to groups

------------------------------------------------------------------------

### 4. CLI Commands

``` bash
ent group create
ent group list
ent group delete
ent group assign
```

Only CRUD and assignment in this phase.

------------------------------------------------------------------------

### 5. Authorization Helper

Introduce a centralized helper, for example:

``` python
authorization.is_administrator(user)
```

Commands should depend on this helper instead of hardcoded checks.

------------------------------------------------------------------------

### 6. Replace Existing Checks

After groups exist, replace command-level permission checks for:

-   Delete user
-   Enable user
-   Disable user
-   Change another user's password
-   Reset another user's password

------------------------------------------------------------------------

## Future RBAC

Long-term architecture:

``` text
Permission
    │
    ▼
Role
    │
    ▼
Group
    │
    ▼
User
```

Commands should never evaluate permissions directly.

------------------------------------------------------------------------

## Migration Plan

1.  Create `groups` table.
2.  Add `group_id` to `users`.
3.  Create bootstrap Administrators group.
4.  Assign the existing admin user.
5.  Create Group repository.
6.  Create Group manager.
7.  Implement `ent group` commands.
8.  Introduce authorization helper.
9.  Replace hardcoded permission checks.
10. Implement full RBAC in a later phase.

------------------------------------------------------------------------

## Notes

This work is intentionally scheduled for the next phase. Because it
modifies the database schema, all changes should be delivered through
Entropy migrations to maintain upgrade compatibility.
