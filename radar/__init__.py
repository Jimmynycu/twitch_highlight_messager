"""Highlight Radar — surface the chat messages worth reacting to on stream.

Pipeline: source (Twitch/mock) -> scorer (the swappable brain) -> sink (web panel via SSE).
"""
__version__ = "0.1.0"
