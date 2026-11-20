"""App-wide CSS that Streamlit's theme config can't express (tab sizing).

Selectors use ARIA roles rather than Streamlit's generated class names, so they survive upgrades.
"""

GLOBAL_CSS = (
    '[role="tablist"]{gap:.25rem}'
    '[role="tab"]{padding:.8rem 1.4rem}'
    # same serif and weight as the headings, so the tabs read as part of the title typography
    '[role="tab"] p{font-family:"Source Serif",serif;font-size:1.4rem;font-weight:500;letter-spacing:.005em}'
)
