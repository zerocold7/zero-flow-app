"""Text handling: language checks (language) and spoken commands (macros)."""
import re

# A web address, which is neither said nor read aloud: dropped from the clipboard text
# the AI gets as context, and from text the reader speaks.
URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')
