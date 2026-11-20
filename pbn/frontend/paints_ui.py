"""'Paint recipes' section of the Generate tab."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from pbn.backend.paints import STANDARD_SET, Paint, hex_to_rgb, rgb_to_hex
from pbn.backend.recipes import Recipe, build_recipes, mix_preview_image, preview_error, usage_summary
from pbn.backend.result import Result

QUALITY_COLOUR = {"excellent": "#3fb950", "good": "#d4a72c", "approximate": "#f0883e"}
STYLES = {"Simplest": 1.0, "Balanced": 0.5, "Accurate": 0.25, "Most accurate": 0.1}  # penalty per extra tube (dE units)

HOW_IT_WORKS = """
Each numbered colour is matched independently by a small **discrete optimisation**.

**Variables.** For each enabled tube *i* an integer number of parts *pᵢ* from the ladder
0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48 (0 = tube not used). At most *m* tubes may be non-zero, where
*m* is "Max tubes per mix". The mixing fractions are *wᵢ = pᵢ / Σp*.

**Prediction model (Kubelka–Munk).** Each tube has a masstone colour and a scattering power *Sᵢ*. Per RGB
channel (linear light) its absorption is *Kᵢ = Sᵢ · (1−R)² / 2R*. A mix has
*K/S = Σ wᵢKᵢ / Σ wᵢSᵢ* and reflectance *R = 1 + K/S − √((K/S)² + 2K/S)*, which is converted to sRGB and
then CIELAB.

**Objective** (minimised for each colour):

`J(p) = ΔE2000(target, mix(p)) + λ · (k − 1) + 0.3 · log₂(Σp)`

where *k* is the number of tubes used and λ is set by "Recipe style" (Simplest 1.0, Balanced 0.5,
Accurate 0.25, Most accurate 0.1). The first term is how far the mix is from the target colour; the others
make a simple recipe beat a fiddly one that is only slightly closer.

**Method.**
- *Up to 4 tubes:* exhaustive. Every recipe in reduced integer ratios (about 600k for 12 tubes) is
  predicted once; for a target the 128 nearest predicted colours are shortlisted with a k-d tree in CIELAB
  and re-ranked by *J*.
- *5–6 tubes:* too many to enumerate, so a local search (steepest descent) starts from the 6 best library
  recipes and repeatedly takes the best single move: change one tube's parts by one ladder step, add a tube,
  drop a tube, or swap one tube for another. It stops at a local optimum and keeps the best of the starts, so
  it is never worse than the 4-tube result on the same objective.

This finds a good recipe for the model, not a guaranteed global optimum and not a guarantee about your real
paints; test-swatch the important colours.
"""


def _reset_paints():
    for i, p in enumerate(STANDARD_SET):
        st.session_state[f"paint_on_{i}"] = True
        st.session_state[f"paint_rgb_{i}"] = rgb_to_hex(p.rgb)


def paint_set_editor() -> tuple[Paint, ...]:
    """Tube list with an on/off switch and an editable colour for each. Returns the enabled paints."""
    paints = []
    with st.expander("Paint set — adjust to match your actual tubes", expanded=False):
        st.caption(
            "Standard 12-tube acrylic set. The colours are approximate on-screen versions of each tube straight "
            "from the tube (masstone); brands differ. For better recipes, paint a swatch of each tube and set its "
            "colour here. Untick tubes you don't have.")
        st.button("Reset to defaults", on_click=_reset_paints, key="paint_reset")
        for row in range(0, len(STANDARD_SET), 2):
            cols = st.columns([3, 1, 3, 1])
            for slot, i in enumerate((row, row + 1)):
                if i >= len(STANDARD_SET):
                    continue
                p = STANDARD_SET[i]
                on = cols[2 * slot].checkbox(p.name, value=True, key=f"paint_on_{i}")
                hexv = cols[2 * slot + 1].color_picker(
                    p.name, value=rgb_to_hex(p.rgb), key=f"paint_rgb_{i}", label_visibility="collapsed")
                if on:
                    paints.append(Paint(p.name, hex_to_rgb(hexv), p.scatter))
    return tuple(paints)


def _swatch(rgb) -> str:
    return (f"<span style='display:inline-block;width:34px;height:20px;border-radius:3px;"
            f"border:1px solid #888;background:{rgb_to_hex(rgb)}'></span>")


def _recipe_table(recipes: list[Recipe]) -> str:
    rows = []
    for r in recipes:
        qc = QUALITY_COLOUR[r.quality]
        amounts = ", ".join(f"{ml:.1f} ml {html.escape(name)}" for name, ml in r.ml)
        rows.append(
            f"<tr><td style='padding:4px 8px'><b>{r.number}</b></td>"
            f"<td style='padding:4px 4px'>{_swatch(r.target_rgb)} {_swatch(r.mix_rgb)}</td>"
            f"<td style='padding:4px 8px'>{html.escape(r.text)}<br>"
            f"<span style='opacity:.65;font-size:.85em'>~{r.total_ml:.1f} ml total: {amounts}</span></td>"
            f"<td style='padding:4px 8px;white-space:nowrap;color:{qc}'>ΔE {r.delta_e:.1f} · {r.quality}</td></tr>")
    return ("<table style='width:100%;border-collapse:collapse'>"
            "<tr style='opacity:.65;text-align:left'><th style='padding:4px 8px'>#</th><th>target | mix</th>"
            "<th style='padding:4px 8px'>Recipe (parts by volume)</th><th style='padding:4px 8px'>Match</th></tr>"
            + "".join(rows) + "</table>")


def mix_comparison(view, recipes: list[Recipe]):
    """Original photo | template as the algorithm coloured it | template as it will look in your mixed paints."""
    result = view.result
    original, algo = result.original_rgb, view.preview
    mixed = mix_preview_image(result, recipes)
    st.subheader("Photo vs template vs your paints")
    st.caption(
        "The right-hand image repaints every region with the colour its recipe is predicted to mix to, so you can "
        "see how your paints will differ from the photo. Differences come from reducing the photo to a few colours "
        "(middle) and from the tubes not mixing exactly to each template colour (right).")
    items = [
        ("Original photo", original, "reference"),
        ("Template colours (algorithm)", algo, f"mean colour difference from photo: ΔE {preview_error(original, algo):.1f}"),
        ("Mixed paint colours", mixed, f"mean colour difference from photo: ΔE {preview_error(original, mixed):.1f}"),
    ]
    for col, (title, img, caption) in zip(st.columns(3, gap="medium"), items):
        col.markdown(f"**{title}**")
        col.image(img, width="stretch")
        col.caption(caption)
    st.caption("Hover over an image and use the fullscreen icon to enlarge it.")


def paints_section(result: Result) -> list[Recipe] | None:
    """Render the section and return the recipes (None if fewer than two tubes are enabled)."""
    st.subheader("Paint recipes")
    st.caption(
        "For each numbered colour: the closest mix from your tubes, in simple volume ratios, plus how much paint "
        "to make. Left swatch = the colour on the template, right = what the mix should look like. "
        "Pigment mixing is only roughly modelled, so test-swatch the important colours first.")
    paints = paint_set_editor()

    c = st.columns(5)
    width = c[0].number_input("Canvas width (cm)", 5.0, 300.0, 40.0, 1.0, key="canvas_w")
    height = c[1].number_input("Canvas height (cm)", 5.0, 300.0, 50.0, 1.0, key="canvas_h")
    ml_rate = c[2].number_input(
        "Paint per 100 cm² per coat (ml)", 0.2, 6.0, 1.5, 0.1, key="ml_rate",
        help="Rough coverage of medium-body acrylic. Raise it for thick application, lower it for thin washes.")
    coats = c[3].number_input("Coats", 1, 4, 2, 1, key="coats")
    max_paints = c[4].select_slider(
        "Max tubes per mix", [2, 3, 4, 5, 6], 3, key="max_paints",
        help="Fewer tubes = simpler, more repeatable mixes. 3 is plenty for most colours; 5-6 only gets used "
             "for hard colours where an extra tube clearly improves the match.")

    style = st.select_slider(
        "Recipe style", list(STYLES), "Simplest", key="recipe_style",
        help="How much accuracy you want in exchange for extra tubes. Simplest keeps mixes to 2-3 tubes; "
             "Accurate / Most accurate allow more tubes (up to the max above) when each one clearly helps.")

    if len(paints) < 2:
        st.warning("Enable at least two tubes in the paint set above.")
        return None
    with st.spinner("Matching colours to mixes…"):
        recipes = build_recipes(result, paints, max_paints, (width, height), ml_rate, int(coats),
                                tube_penalty=STYLES[style])

    approx = sum(r.quality == "approximate" for r in recipes)
    st.markdown(_recipe_table(recipes), unsafe_allow_html=True)
    if approx:
        st.caption(f"{approx} colour(s) are marked approximate (ΔE ≥ 5): they are outside what these tubes mix well "
                   "(very bright or saturated colours). Consider adding a tube such as a brighter yellow, a magenta "
                   "or a cyan-leaning blue, or accept the closest match.")

    st.markdown("**Total paint needed**")
    usage = usage_summary(recipes)
    st.dataframe(pd.DataFrame({"Paint": list(usage), "ml": [round(v, 1) for v in usage.values()]}),
                 hide_index=True, width="stretch")
    st.caption("Includes a 25% margin. Quantities are rough estimates.")
    with st.expander("How are the recipes found?"):
        st.markdown(HOW_IT_WORKS)
    return recipes
