"""Konstanten für die G.hn-MaxLinear-Integration."""

DOMAIN = "ghn_maxlinear"

# G.hn-Link-Raten ändern sich langsam – 60 s reicht und schont den Adapter.
DEFAULT_SCAN_INTERVAL = 60

# Die MaxLinear-Web-GUI kappt das Passwort hart auf 20 Zeichen (maxlength=20).
PASSWORD_MAXLEN = 20
