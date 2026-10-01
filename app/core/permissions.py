from typing import List, Set

class Permissions:
    USERS_READ = "users.read"
    USERS_PII_READ = "users.pii.read"
    USERS_WRITE = "users.write"
    USERS_SUSPEND = "users.suspend"
    USERS_BAN = "users.ban"

    BOOKS_READ = "books.read"
    BOOKS_WRITE = "books.write"
    COPIES_WRITE = "copies.write"

    LOANS_READ = "loans.read"
    LOANS_MANAGE = "loans.manage"
    LOANS_RESOLVE_DISPUTE = "loans.resolve_dispute"

    REPORTS_READ = "reports.read"
    REPORTS_RESOLVE = "reports.resolve"

    RESOURCES_REVIEW = "resources.review"
    ORGANIZATIONS_MANAGE = "organizations.manage"
    ANALYTICS_READ = "analytics.read"

    IMPORTS_CREATE = "imports.create"
    EXPORTS_CREATE = "exports.create"
    EXPORTS_PII = "exports.pii"

    CUSTOM_FIELDS_MANAGE = "custom_fields.manage"
    AUDIT_READ = "audit.read"

    BACKUPS_CREATE = "backups.create"
    BACKUPS_DOWNLOAD = "backups.download"
    BACKUPS_RESTORE = "backups.restore"

    SYSTEM_SETTINGS = "system.settings"
    ROLES_MANAGE = "roles.manage"

    ALL: Set[str] = {
        USERS_READ, USERS_PII_READ, USERS_WRITE, USERS_SUSPEND, USERS_BAN,
        BOOKS_READ, BOOKS_WRITE, COPIES_WRITE,
        LOANS_READ, LOANS_MANAGE, LOANS_RESOLVE_DISPUTE,
        REPORTS_READ, REPORTS_RESOLVE,
        RESOURCES_REVIEW, ORGANIZATIONS_MANAGE, ANALYTICS_READ,
        IMPORTS_CREATE, EXPORTS_CREATE, EXPORTS_PII,
        CUSTOM_FIELDS_MANAGE, AUDIT_READ,
        BACKUPS_CREATE, BACKUPS_DOWNLOAD, BACKUPS_RESTORE,
        SYSTEM_SETTINGS, ROLES_MANAGE
    }

ROLE_PERMISSIONS_MAP = {
    "Super Admin": Permissions.ALL,
    "Admin": {
        Permissions.USERS_READ, Permissions.USERS_PII_READ, Permissions.USERS_WRITE,
        Permissions.USERS_SUSPEND,
        Permissions.BOOKS_READ, Permissions.BOOKS_WRITE, Permissions.COPIES_WRITE,
        Permissions.LOANS_READ, Permissions.LOANS_MANAGE, Permissions.LOANS_RESOLVE_DISPUTE,
        Permissions.REPORTS_READ, Permissions.REPORTS_RESOLVE,
        Permissions.RESOURCES_REVIEW, Permissions.ORGANIZATIONS_MANAGE, Permissions.ANALYTICS_READ,
        Permissions.IMPORTS_CREATE, Permissions.EXPORTS_CREATE, Permissions.EXPORTS_PII,
        Permissions.CUSTOM_FIELDS_MANAGE, Permissions.AUDIT_READ,
        Permissions.BACKUPS_CREATE, Permissions.BACKUPS_DOWNLOAD,
        Permissions.SYSTEM_SETTINGS
    },
    "Moderator": {
        Permissions.USERS_READ, Permissions.USERS_SUSPEND,
        Permissions.REPORTS_READ, Permissions.REPORTS_RESOLVE,
        Permissions.LOANS_READ, Permissions.LOANS_RESOLVE_DISPUTE,
        Permissions.AUDIT_READ
    },
    "Content Manager": {
        Permissions.BOOKS_READ, Permissions.BOOKS_WRITE, Permissions.COPIES_WRITE,
        Permissions.RESOURCES_REVIEW, Permissions.CUSTOM_FIELDS_MANAGE,
        Permissions.IMPORTS_CREATE, Permissions.EXPORTS_CREATE
    },
    "Library Manager": {
        Permissions.BOOKS_READ, Permissions.BOOKS_WRITE, Permissions.COPIES_WRITE,
        Permissions.LOANS_READ, Permissions.LOANS_MANAGE,
        Permissions.ORGANIZATIONS_MANAGE
    },
    "Analytics Viewer": {
        Permissions.BOOKS_READ, Permissions.LOANS_READ,
        Permissions.ANALYTICS_READ, Permissions.EXPORTS_CREATE
    }
}
