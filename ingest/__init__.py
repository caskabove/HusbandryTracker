"""Ingest — the core process that drains the Inbox, exports each Plugin's Registry, and evaluates
Alert Conditions. See CONTEXT.md: Ingest, Plugin, Inbox, Registry, Plugin Event; ADR 0013.
Contains no vendor-specific code; adding a Plugin never touches this package.
"""
