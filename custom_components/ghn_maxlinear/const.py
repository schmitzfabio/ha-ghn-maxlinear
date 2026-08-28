"""Konstanten für die G.hn-MaxLinear-Integration."""

DOMAIN = "ghn_maxlinear"

# G.hn-Link-Raten ändern sich langsam – 60 s reicht und schont den Adapter.
DEFAULT_SCAN_INTERVAL = 60
# Untergrenze, damit ein zu knappes Intervall die schwache Adapter-CPU nicht
# dauerbelastet (ein Poll sind zwei HTTP-Requests gegen eine CGI-GUI).
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 3600

# Die MaxLinear-Web-GUI kappt das Passwort hart auf 20 Zeichen (maxlength=20).
PASSWORD_MAXLEN = 20
