# Entropy -- User & Authentication Roadmap

## Context

The current user subsystem is functionally complete for the initial
framework:

-   User CRUD
-   Authentication
-   Session management
-   Password hashing and validation
-   Password change
-   Administrator password change API
-   Password reset API
-   System user protection
-   Centralized exception handling
-   Command/UI separation
-   Business logic isolated in `UserManager`

The remaining work should be implemented **after the framework is
stabilized**. The items below are intentionally deferred to avoid
introducing RBAC and policy complexity before the core platform is
complete.

------------------------------------------------------------------------

# Phase 1 -- User Groups

## Goal

Introduce groups as the foundation for RBAC.

Current model already contains:

``` text
group_id
```

Implement a dedicated Group entity.

### Model

``` text
Group
-----
id
name
description
system
```

### Commands

``` bash
ent group create
ent group list
ent group delete
```

Initially implement CRUD only.

No permissions or authorization yet.

------------------------------------------------------------------------

# Phase 2 -- Password Expiration

## Goal

Support password aging.

### User fields

``` text
password_changed_at
password_expires_at
```

Authentication flow becomes:

``` text
authenticate()
        │
        ▼
password expired?
        │
        ▼
PasswordExpiredError
```

User changes password using:

``` bash
ent user password --change
```

------------------------------------------------------------------------

# Phase 3 -- Account Locking

Implement temporary lockout after repeated failures.

### User fields

``` text
failed_attempts
locked_until
```

Flow

``` text
5 failed logins
        │
        ▼
Lock account for 15 minutes
```

Command:

``` bash
ent user unlock <username>
```

------------------------------------------------------------------------

# Phase 4 -- Login Metadata

Track login history.

### User fields

``` text
last_login_at
last_login_ip
```

Useful for administration and auditing.

------------------------------------------------------------------------

# Phase 5 -- Password History

Prevent password reuse.

Suggested table:

``` text
user_password_history
```

Store the previous 5 password hashes.

Flow

``` text
abc123
   │
xyz789
   │
abc123  ❌
```

------------------------------------------------------------------------

# Phase 6 -- Forced Password Change

When an administrator resets a password:

``` text
must_change_password = true
```

Next authentication:

``` text
PasswordChangeRequiredError
```

The user must execute:

``` bash
ent user password --change
```

before continuing.

------------------------------------------------------------------------

# Phase 7 -- Audit Events

Introduce security audit events independent of application logs.

Record events such as:

-   User created
-   User deleted
-   User enabled/disabled
-   Password changed
-   Password reset
-   Group changed

These belong in an audit subsystem rather than standard application
logging.

------------------------------------------------------------------------

# Phase 8 -- RBAC

Replace the current `system=True` approach with role-based access
control.

Architecture:

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

Example groups:

-   Administrator
-   Operator
-   Developer
-   Viewer
-   Helpdesk

Authorization checks should occur before invoking privileged operations
such as:

-   Password reset
-   Administrative password changes
-   User creation/deletion
-   Group management

------------------------------------------------------------------------

# Recommended Implementation Order

1.  Groups
2.  Password Expiration
3.  Account Locking
4.  Login Metadata
5.  Password History
6.  Forced Password Change
7.  Audit Events
8.  RBAC

This sequence minimizes refactoring and provides a stable foundation for
future authorization and enterprise security features.
