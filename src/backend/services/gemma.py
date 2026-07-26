from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from google import genai
from google.genai import types

from src.backend.config import get_settings, load_agents
from src.backend.schemas import AgentDefinition, GenerateSvgResponse

logger = logging.getLogger("v2v.gemma")


class AgentNotFoundError(ValueError):
    pass


class GenerationTimeoutError(TimeoutError):
    pass


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "quota" in text or "rate limit" in text or "429" in text


SVG_PATTERN = re.compile(r"<svg\b[\s\S]*?</svg>", re.IGNORECASE)
JSON_BLOCK_PATTERN = re.compile(r"\{[\s\S]*\}")
SVG_FENCE_PATTERN = re.compile(r"```(?:xml|svg)?\s*([\s\S]*?)```", re.IGNORECASE)
TEXT_BLOCK_PATTERN = re.compile(r"<text\b[\s\S]*?</text>", re.IGNORECASE)
CACHE_PATH = Path(__file__).resolve().parents[1] / "svg_cache.json"
SECTOR_PROMPT_SEED = (
    "Draw a 500x300 light-mode sector diagram. White bg (#ffffff) with dark border (#1e293b). "
    "Title 'Arc Length' at Y=35. Label 'Arc = ? cm' in purple (#7c3aed) at Y=70. Draw wedge at "
    "vertex C (250, 200) with cyan (#0284c7) radius lines 'r = 10.5 cm', gold (#d97706) arc '118\u00b0', "
    "and purple (#8b5cf6) outer arc. Pill box at Y=250 with text 'Formula: (118/360) \u00d7 \u03c0 \u00d7 21'."
)
SECTOR_SVG_SEED = (
    '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="500" height="300" fill="#ffffff" stroke="#1e293b" stroke-width="4" rx="12"/>'
    '<text x="250" y="35" fill="#0f172a" stroke="#000000" stroke-width="0.5" font-family="sans-serif" font-size="20" font-weight="bold" text-anchor="middle">Arc Length</text>'
    '<text x="250" y="70" fill="#7c3aed" stroke="#000000" stroke-width="0.5" font-family="sans-serif" font-size="16" font-weight="bold" text-anchor="middle">Arc = ? cm</text>'
    '<path d="M 150,130 A 122,122 0 0,1 350,130" stroke="#8b5cf6" stroke-width="6" fill="none" stroke-linecap="round"/>'
    '<path d="M 250,200 L 150,130 M 250,200 L 350,130" stroke="#0284c7" stroke-width="4" fill="none"/>'
    '<text x="185" y="180" fill="#0284c7" stroke="#000000" stroke-width="0.5" font-family="sans-serif" font-size="14" font-weight="bold" text-anchor="middle">r = 10.5 cm</text>'
    '<path d="M 220,179 A 36.6,36.6 0 0,1 280,179" stroke="#d97706" stroke-width="3" fill="none"/>'
    '<text x="250" y="165" fill="#d97706" stroke="#000000" stroke-width="0.5" font-family="sans-serif" font-size="16" font-weight="bold" text-anchor="middle">118&#176;</text>'
    '<circle cx="250" cy="200" r="4" fill="#0f172a"/>'
    '<text x="250" y="218" fill="#0f172a" font-family="sans-serif" font-size="15" font-weight="bold" text-anchor="middle">C</text>'
    '<rect x="80" y="245" width="340" height="38" fill="#f1f5f9" stroke="#0f172a" stroke-width="2" rx="8"/>'
    '<text x="250" y="270" fill="#0f172a" font-family="sans-serif" font-size="15" font-weight="bold" text-anchor="middle">Formula: (118/360) &#215; &#960; &#215; 21</text>'
    '</svg>'
)


@lru_cache(maxsize=1)
def _load_svg_cache() -> dict[str, str]:
    if not CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(k): str(v) for k, v in payload.items()}


def _save_svg_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=True), encoding="utf-8")


def _is_valid_svg_candidate(svg: str) -> bool:
    candidate = svg.strip()
    lowered = candidate.lower()
    if not lowered.startswith("<svg"):
        return False
    if "</svg>" not in lowered:
        return False
    try:
        root = ET.fromstring(candidate)
    except ET.ParseError:
        return False
    tag = root.tag.lower()
    return tag.endswith("svg")


def _normalize_svg_candidate(raw: str) -> str:
    candidate = raw.strip()

    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:xml|svg)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)

    fence_match = SVG_FENCE_PATTERN.search(candidate)
    if fence_match:
        candidate = fence_match.group(1).strip()

    # Gemini sometimes drops the leading "<svg" token while keeping attributes.
    if not candidate.lower().startswith("<svg"):
        lowered = candidate.lower()
        if lowered.startswith('xmlns="http://www.w3.org/2000/svg"'):
            candidate = f"<svg {candidate}"
        elif lowered.startswith('http://www.w3.org/2000/svg"'):
            candidate = f'<svg xmlns="{candidate}'
        elif 'viewbox=' in lowered and 'http://www.w3.org/2000/svg' in lowered:
            candidate = f"<svg {candidate}"

    svg_match = SVG_PATTERN.search(candidate)
    if svg_match:
        candidate = svg_match.group(0).strip()

    if not candidate.lower().startswith("<svg"):
        return ""

    if "xmlns=" not in candidate:
        candidate = candidate.replace(
            "<svg",
            '<svg xmlns="http://www.w3.org/2000/svg"',
            1,
        )

    return candidate


def _extract_svg_from_text(raw_text: str) -> str:
    normalized = _normalize_svg_candidate(raw_text)
    if normalized and _is_valid_svg_candidate(normalized):
        return normalized

    repaired = _repair_svg_markup(raw_text)
    if repaired and _is_valid_svg_candidate(repaired):
        return repaired

    return ""


def _extract_svg_from_json_text(raw_text: str) -> str:
    candidate_text = raw_text.strip()
    if not candidate_text:
        return ""

    try:
        payload = json.loads(candidate_text)
    except json.JSONDecodeError:
        match = JSON_BLOCK_PATTERN.search(candidate_text)
        if not match:
            return ""
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return ""

    if not isinstance(payload, dict):
        return ""

    svg = _extract_svg_from_text(str(payload.get("svg") or ""))
    if svg:
        return svg

    repaired = _repair_svg_markup(str(payload.get("svg") or ""))
    return repaired if repaired and _is_valid_svg_candidate(repaired) else ""


def _repair_svg_markup(raw_svg: str) -> str:
    candidate = _normalize_svg_candidate(raw_svg)
    if not candidate:
        candidate = raw_svg.strip()

    if not candidate.lower().startswith("<svg"):
        return ""
    if "</svg>" not in candidate.lower():
        return ""

    candidate = candidate.replace('font-family="Arial, sans-serif"', 'font-family="sans-serif"')
    candidate = candidate.replace('font-family="Arial, center-serif"', 'font-family="sans-serif"')
    candidate = re.sub(r'font-weight="[^"]*"', 'font-weight="700"', candidate, flags=re.IGNORECASE)
    candidate = re.sub(r'font-size="[^"]*"', 'font-size="14"', candidate, flags=re.IGNORECASE)
    candidate = re.sub(r'font-family="[^"]*"', 'font-family="sans-serif"', candidate, flags=re.IGNORECASE)

    def _rewrite_text_tag(match: re.Match[str]) -> str:
        block = match.group(0)
        inner_match = re.search(r">([\s\S]*?)</text>$", block, flags=re.IGNORECASE)
        inner = inner_match.group(1) if inner_match else ""

        def _first_attr(name: str) -> str:
            pattern = re.compile(rf'{name}\s*=\s*"([^"]*)"', re.IGNORECASE)
            found = pattern.search(block)
            return found.group(1) if found else ""

        x_value = _first_attr("x") or "250"
        y_value = _first_attr("y") or "150"
        fill_value = _first_attr("fill") or "#1f2937"
        text_anchor_value = _first_attr("text-anchor") or "middle"

        cleaned_attrs = [
            f'x="{_escape_text(x_value)}"',
            f'y="{_escape_text(y_value)}"',
            f'fill="{_escape_text(fill_value)}"',
            'font-family="sans-serif"',
            'font-size="14"',
            'font-weight="700"',
            f'text-anchor="{_escape_text(text_anchor_value)}"',
        ]

        return f'<text {" ".join(cleaned_attrs)}>{inner}</text>'

    candidate = TEXT_BLOCK_PATTERN.sub(_rewrite_text_tag, candidate)
    return candidate


def _escape_text(value: str) -> str:
    return html.escape(value, quote=True)


def _wrap_text_lines(text: str, max_chars: int = 44, max_lines: int = 2) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break

    if len(lines) < max_lines:
        lines.append(current)

    consumed_words = " ".join(lines).split()
    if len(consumed_words) < len(words):
        lines[-1] = lines[-1].rstrip(".") + "..."

    return lines[:max_lines]


def _svg_title_block(
    text: str,
    *,
    y: int = 38,
    font_size: int = 16,
    max_chars: int = 44,
    max_lines: int = 2,
) -> str:
    lines = _wrap_text_lines(text, max_chars=max_chars, max_lines=max_lines)
    tspans: list[str] = []
    for index, line in enumerate(lines):
        dy = "0" if index == 0 else "1.22em"
        tspans.append(f'<tspan x="250" dy="{dy}">{_escape_text(line)}</tspan>')

    return (
        f'<text x="250" y="{y}" fill="#ffffff" font-family="sans-serif" '
        f'font-size="{font_size}" font-weight="700" text-anchor="middle">'
        + "".join(tspans)
        + "</text>"
    )


def _response_text(response: object) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    chunks: list[str] = []
    thought_chunks: list[str] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                cleaned = part_text.strip()
                if getattr(part, "thought", False):
                    thought_chunks.append(cleaned)
                else:
                    chunks.append(cleaned)

    if chunks:
        return chunks[0]
    return thought_chunks[0] if thought_chunks else ""


def _extract_plan(text: str, prompt: str) -> dict:
    if not text:
        return {"question": prompt}

    candidate_text = text.strip()
    if candidate_text.startswith("{") and candidate_text.endswith("}"):
        try:
            plan = json.loads(candidate_text)
            if isinstance(plan, dict):
                plan.setdefault("question", prompt)
                return plan
        except json.JSONDecodeError:
            pass

    match = JSON_BLOCK_PATTERN.search(candidate_text)
    if match:
        try:
            plan = json.loads(match.group(0))
            if isinstance(plan, dict):
                plan.setdefault("question", prompt)
                return plan
        except json.JSONDecodeError:
            pass

    return {"question": prompt}


def _infer_diagram_type(prompt: str) -> str:
    lowered = prompt.lower()
    if "on the left" in lowered and "on the right" in lowered:
        return "described"

    keyword_groups = {
        "probability": ("probability", "token", "bag", "chance", "random", "select"),
        "geometry": ("angle", "triangle", "circle", "quadrilateral", "area", "perimeter", "geometry"),
        "algebra": ("solve", "equation", "unknown", "simplify", "factor", "expression"),
        "graph": ("graph", "chart", "plot", "coordinate", "axis", "axes", "gradient", "line"),
        "data": ("data", "table", "bar", "pie", "frequency", "mean", "median", "mode"),
    }

    for diagram_type, keywords in keyword_groups.items():
        if any(keyword in lowered for keyword in keywords):
            return diagram_type
    return "generic"


def _parse_probability_tokens(prompt: str) -> list[dict[str, int | str]]:
    token_matches = re.findall(r"(\d+)\s+([a-zA-Z]+)\s+tokens?", prompt, flags=re.IGNORECASE)
    tokens: list[dict[str, int | str]] = []
    for count_str, colour in token_matches:
        tokens.append({"c": colour.lower(), "n": int(count_str)})

    if not tokens:
        compact_match = re.findall(r"(\d+)\s+([a-zA-Z]+)", prompt)
        for count_str, colour in compact_match[:3]:
            tokens.append({"c": colour.lower(), "n": int(count_str)})

    if not tokens:
        tokens = [{"c": "red", "n": 1}, {"c": "blue", "n": 2}]

    return tokens


def _render_probability_svg(question: str, bag_color: str, tokens: list[dict[str, int | str]]) -> str:
    bag_fill = {
        "brown": "#8B4513",
        "tan": "#B08968",
        "grey": "#64748B",
        "gray": "#64748B",
    }.get(bag_color.lower(), bag_color if bag_color.startswith("#") else "#8B4513")

    positions = [
        (250, 180), (205, 210), (295, 210),
        (220, 155), (280, 155), (250, 230),
        (180, 185), (320, 185),
    ]

    svg_parts = [
        '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">',
        '<rect width="500" height="300" fill="#1e293b" />',
        _svg_title_block(question, y=30, font_size=14, max_chars=52, max_lines=2),
        f'<path d="M 150 250 C 105 250, 95 115, 250 105 C 405 115, 395 250, 350 250 Z" fill="{bag_fill}" opacity="0.92" />',
        f'<path d="M 205 108 L 225 68 L 275 68 L 295 108 Z" fill="{bag_fill}" />',
        '<circle cx="250" cy="153" r="6" fill="#ffffff" opacity="0.7" />',
    ]

    pos_index = 0
    for token in tokens:
        colour = str(token.get("c", "white"))
        count = int(token.get("n", 1))
        for _ in range(count):
            if pos_index >= len(positions):
                break
            x, y = positions[pos_index]
            svg_parts.append(
                f'<circle cx="{x}" cy="{y}" r="20" fill="{colour}" stroke="#ffffff" stroke-width="2" />'
            )
            pos_index += 1

    if pos_index == 0:
        svg_parts.extend(
            [
                '<circle cx="220" cy="190" r="18" fill="#ef4444" stroke="#ffffff" stroke-width="2" />',
                '<circle cx="280" cy="190" r="18" fill="#3b82f6" stroke="#ffffff" stroke-width="2" />',
            ]
        )

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def _render_geometry_svg(question: str) -> str:
    return "\n".join(
        [
            '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">',
            '<rect width="500" height="300" fill="#1e293b" />',
            _svg_title_block(question, y=30, font_size=14, max_chars=52, max_lines=2),
            '<polygon points="250,70 140,230 360,230" fill="none" stroke="#38bdf8" stroke-width="4" />',
            '<path d="M 250 70 A 22 22 0 0 1 266 86" fill="none" stroke="#facc15" stroke-width="3" />',
            '<text x="238" y="58" fill="#facc15" font-family="sans-serif" font-size="14">A</text>',
            '<text x="128" y="244" fill="#facc15" font-family="sans-serif" font-size="14">B</text>',
            '<text x="362" y="244" fill="#facc15" font-family="sans-serif" font-size="14">C</text>',
            '<text x="250" y="145" fill="#ffffff" font-family="sans-serif" font-size="14" text-anchor="middle">vague helpful sketch</text>',
            '</svg>',
        ]
    )


def _parse_sector_details(prompt: str) -> dict[str, str]:
    details = {
        "radius_label": "r = 10.5 cm",
        "angle_label": "118°",
        "arc_label": "Arc Length = ? cm",
        "formula": "Arc Length = (118/360) x pi x 21",
    }

    radius_match = re.search(r"radius line\s+['\"]([^'\"]+)['\"]", prompt, flags=re.IGNORECASE)
    if radius_match:
        details["radius_label"] = radius_match.group(1).strip()

    angle_label_match = re.search(r"angle arc[^\n]*?labeled\s+['\"]([^'\"]+)['\"]", prompt, flags=re.IGNORECASE)
    if angle_label_match:
        details["angle_label"] = angle_label_match.group(1).strip()
    else:
        angle_numeric = re.search(r"angle\s+of\s+([0-9]+(?:\.[0-9]+)?)", prompt, flags=re.IGNORECASE)
        if angle_numeric:
            details["angle_label"] = f"{angle_numeric.group(1)}°"

    arc_match = re.search(r"outer curved arc[^\n]*?['\"]([^'\"]+)['\"]", prompt, flags=re.IGNORECASE)
    if arc_match:
        details["arc_label"] = arc_match.group(1).strip()

    formula_match = re.search(r"formula(?:\s+guide)?\s+box[^\n]*?reads\s+['\"]([^'\"]+)['\"]", prompt, flags=re.IGNORECASE)
    if formula_match:
        details["formula"] = formula_match.group(1).strip()

    return details


def _extract_sector_plan_from_text(raw_text: str) -> dict[str, str]:
    candidate_text = raw_text.strip()
    if not candidate_text:
        return {}

    try:
        payload = json.loads(candidate_text)
    except json.JSONDecodeError:
        match = JSON_BLOCK_PATTERN.search(candidate_text)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    if not isinstance(payload, dict):
        return {}

    plan: dict[str, str] = {}
    for key in ("title", "label", "radius_label", "angle_label", "formula"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            plan[key] = value.strip()

    return plan


def _render_sector_svg(question: str, prompt: str, plan: dict[str, str] | None = None) -> str:
    details = _parse_sector_details(prompt)
    if plan:
        details.update({key: value for key, value in plan.items() if value})

    cx, cy = 250.0, 170.0
    radius = 92.0
    start_deg = 210.0
    end_deg = 328.0
    start_rad = math.radians(start_deg)
    end_rad = math.radians(end_deg)

    x1 = cx + radius * math.cos(start_rad)
    y1 = cy + radius * math.sin(start_rad)
    x2 = cx + radius * math.cos(end_rad)
    y2 = cy + radius * math.sin(end_rad)

    angle_arc_r = 34.0
    ax1 = cx + angle_arc_r * math.cos(start_rad)
    ay1 = cy + angle_arc_r * math.sin(start_rad)
    ax2 = cx + angle_arc_r * math.cos(end_rad)
    ay2 = cy + angle_arc_r * math.sin(end_rad)

    mid_rad = math.radians((start_deg + end_deg) / 2)
    lx = cx + (radius + 18.0) * math.cos(mid_rad)
    ly = cy + (radius + 18.0) * math.sin(mid_rad)

    radius_lx = cx + (radius * 0.58) * math.cos(start_rad)
    radius_ly = cy + (radius * 0.58) * math.sin(start_rad)

    angle_lx = cx + (angle_arc_r + 16.0) * math.cos(math.radians((start_deg + end_deg) / 2))
    angle_ly = cy + (angle_arc_r + 16.0) * math.sin(math.radians((start_deg + end_deg) / 2))

    return "\n".join(
        [
            '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">',
            '<rect width="500" height="300" fill="#1e293b" />',
            _svg_title_block(question, y=16, font_size=10, max_chars=76, max_lines=3),
            _svg_title_block('Circle sector helper diagram', y=64, font_size=16, max_chars=36, max_lines=1),
            f'<path d="M {cx:.1f} {cy:.1f} L {x1:.1f} {y1:.1f} A {radius:.1f} {radius:.1f} 0 0 1 {x2:.1f} {y2:.1f} Z" fill="#1f2937" stroke="#334155" stroke-width="2" />',
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#22d3ee" stroke-width="4" />',
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#22d3ee" stroke-width="4" />',
            f'<path d="M {x1:.1f} {y1:.1f} A {radius:.1f} {radius:.1f} 0 0 1 {x2:.1f} {y2:.1f}" fill="none" stroke="#a855f7" stroke-width="5" />',
            f'<path d="M {ax1:.1f} {ay1:.1f} A {angle_arc_r:.1f} {angle_arc_r:.1f} 0 0 1 {ax2:.1f} {ay2:.1f}" fill="none" stroke="#facc15" stroke-width="3" />',
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#f8fafc" />',
            f'<text x="{cx + 6:.1f}" y="{cy + 16:.1f}" fill="#f8fafc" font-family="sans-serif" font-size="14">C</text>',
            f'<text x="{radius_lx:.1f}" y="{radius_ly:.1f}" fill="#22d3ee" font-family="sans-serif" font-size="13">{_escape_text(details["radius_label"])}</text>',
            f'<text x="{angle_lx:.1f}" y="{angle_ly:.1f}" fill="#facc15" font-family="sans-serif" font-size="13">{_escape_text(details["angle_label"])}</text>',
            f'<text x="{lx:.1f}" y="{ly:.1f}" fill="#e9d5ff" font-family="sans-serif" font-size="13">{_escape_text(details["arc_label"])}</text>',
            '<rect x="58" y="244" width="384" height="42" rx="10" fill="#0b1220" stroke="#64748b" stroke-width="2" />',
            f'<text x="250" y="270" fill="#f8fafc" font-family="sans-serif" font-size="14" text-anchor="middle">{_escape_text(details["formula"])[:66]}</text>',
            '</svg>',
        ]
    )


def _render_algebra_svg(question: str) -> str:
    return "\n".join(
        [
            '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">',
            '<rect width="500" height="300" fill="#1e293b" />',
            _svg_title_block(question, y=30, font_size=14, max_chars=52, max_lines=2),
            '<line x1="110" y1="210" x2="390" y2="210" stroke="#ffffff" stroke-width="4" />',
            '<line x1="250" y1="210" x2="250" y2="115" stroke="#ffffff" stroke-width="4" />',
            '<line x1="155" y1="120" x2="345" y2="120" stroke="#facc15" stroke-width="5" />',
            '<circle cx="155" cy="120" r="40" fill="#0f766e" opacity="0.85" />',
            '<circle cx="345" cy="120" r="40" fill="#0f766e" opacity="0.85" />',
            '<rect x="140" y="102" width="30" height="18" rx="4" fill="#f43f5e" />',
            '<rect x="330" y="102" width="30" height="18" rx="4" fill="#f43f5e" />',
            '<text x="155" y="140" fill="#ffffff" font-family="sans-serif" font-size="16" text-anchor="middle">x</text>',
            '<text x="345" y="140" fill="#ffffff" font-family="sans-serif" font-size="16" text-anchor="middle">x</text>',
            '<text x="250" y="255" fill="#ffffff" font-family="sans-serif" font-size="13" text-anchor="middle">balance scale for unknowns</text>',
            '</svg>',
        ]
    )


def _render_graph_svg(question: str) -> str:
    return "\n".join(
        [
            '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">',
            '<rect width="500" height="300" fill="#1e293b" />',
            _svg_title_block(question, y=30, font_size=14, max_chars=52, max_lines=2),
            '<line x1="90" y1="240" x2="410" y2="240" stroke="#ffffff" stroke-width="3" />',
            '<line x1="90" y1="240" x2="90" y2="80" stroke="#ffffff" stroke-width="3" />',
            '<path d="M 120 210 L 180 180 L 240 165 L 300 120 L 360 95" fill="none" stroke="#38bdf8" stroke-width="4" />',
            '<circle cx="120" cy="210" r="5" fill="#facc15" />',
            '<circle cx="180" cy="180" r="5" fill="#facc15" />',
            '<circle cx="240" cy="165" r="5" fill="#facc15" />',
            '<circle cx="300" cy="120" r="5" fill="#facc15" />',
            '<circle cx="360" cy="95" r="5" fill="#facc15" />',
            '</svg>',
        ]
    )


def _render_data_svg(question: str) -> str:
    bars = [70, 130, 90, 165]
    colours = ["#38bdf8", "#f43f5e", "#facc15", "#0f766e"]
    svg_parts = [
        '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">',
        '<rect width="500" height="300" fill="#1e293b" />',
        _svg_title_block(question, y=30, font_size=14, max_chars=52, max_lines=2),
        '<line x1="90" y1="240" x2="410" y2="240" stroke="#ffffff" stroke-width="3" />',
        '<line x1="90" y1="240" x2="90" y2="70" stroke="#ffffff" stroke-width="3" />',
    ]
    x = 130
    for bar_height, colour in zip(bars, colours, strict=False):
        svg_parts.append(f'<rect x="{x}" y="{240 - bar_height}" width="45" height="{bar_height}" rx="6" fill="{colour}" />')
        x += 70
    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def _render_generic_svg(question: str) -> str:
    return "\n".join(
        [
            '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">',
            '<rect width="500" height="300" fill="#1e293b" />',
            _svg_title_block(question, y=30, font_size=14, max_chars=52, max_lines=2),
            '<rect x="120" y="80" width="260" height="150" rx="18" fill="none" stroke="#38bdf8" stroke-width="4" stroke-dasharray="10 10" />',
            '<circle cx="200" cy="155" r="34" fill="#f43f5e" opacity="0.9" />',
            '<circle cx="300" cy="155" r="34" fill="#facc15" opacity="0.9" />',
            '<text x="250" y="255" fill="#ffffff" font-family="sans-serif" font-size="13" text-anchor="middle">generic Nat 5 helper diagram</text>',
            '</svg>',
        ]
    )


def _parse_described_layout(prompt: str) -> dict[str, str]:
    layout: dict[str, str] = {
        "title": "Helper diagram",
        "left_label": "Left value",
        "right_label": "Right value",
        "arrow_label": "change",
        "bottom_text": "working shown",
        "left_color": "#2563eb",
        "right_color": "#eab308",
    }

    title_match = re.search(r"showing\s+([^\.]+)", prompt, flags=re.IGNORECASE)
    if title_match:
        layout["title"] = title_match.group(1).strip().strip("\"'")

    left_match = re.search(r"on\s+the\s+left[^\n]*?labeled\s+['\"]([^'\"]+)['\"]", prompt, flags=re.IGNORECASE)
    if left_match:
        layout["left_label"] = left_match.group(1).strip()

    right_match = re.search(r"on\s+the\s+right[^\n]*?labeled\s+['\"]([^'\"]+)['\"]", prompt, flags=re.IGNORECASE)
    if right_match:
        layout["right_label"] = right_match.group(1).strip()

    arrow_match = re.search(
        r"(?:connect|arrow|curve|arc)[^\n]*?labeled\s+['\"]([^'\"]+)['\"]",
        prompt,
        flags=re.IGNORECASE,
    )
    if arrow_match:
        layout["arrow_label"] = (arrow_match.group(1) or "change").strip()

    bottom_match = re.search(r"(?:at\s+the\s+bottom|include\s+a\s+formula\s+box)[^\n]*?(?:reads?|reading|that\s+reads?)\s+['\"]([^'\"]+)['\"]", prompt, flags=re.IGNORECASE)
    if bottom_match:
        layout["bottom_text"] = bottom_match.group(1).strip()

    left_color_match = re.search(r"on\s+the\s+left[^\n]*?place\s+a\s+([a-zA-Z]+)\s+block", prompt, flags=re.IGNORECASE)
    if left_color_match:
        colour = left_color_match.group(1).lower()
        layout["left_color"] = {
            "blue": "#2563eb",
            "gold": "#eab308",
            "green": "#16a34a",
            "red": "#dc2626",
            "purple": "#7c3aed",
        }.get(colour, layout["left_color"])

    right_color_match = re.search(r"on\s+the\s+right[^\n]*?place\s+a\s+([a-zA-Z]+)\s+block", prompt, flags=re.IGNORECASE)
    if right_color_match:
        colour = right_color_match.group(1).lower()
        layout["right_color"] = {
            "blue": "#2563eb",
            "gold": "#eab308",
            "green": "#16a34a",
            "red": "#dc2626",
            "purple": "#7c3aed",
        }.get(colour, layout["right_color"])

    return layout


def _render_described_svg(question: str, prompt: str) -> str:
    layout = _parse_described_layout(prompt)
    title = _escape_text(layout["title"])
    left_label = _escape_text(layout["left_label"])
    right_label = _escape_text(layout["right_label"])
    arrow_label = _escape_text(layout["arrow_label"])
    bottom_text = _escape_text(layout["bottom_text"])
    left_color = layout["left_color"]
    right_color = layout["right_color"]

    return "\n".join(
        [
            '<svg viewBox="0 0 500 300" width="500" height="300" xmlns="http://www.w3.org/2000/svg">',
            '<rect width="500" height="300" fill="#1e293b" />',
            _svg_title_block(question, y=20, font_size=11, max_chars=78, max_lines=1),
            _svg_title_block(title, y=52, font_size=18, max_chars=34, max_lines=1),
            f'<rect x="60" y="105" width="150" height="70" rx="12" fill="{left_color}" />',
            f'<rect x="290" y="105" width="150" height="70" rx="12" fill="{right_color}" />',
            f'<text x="135" y="145" fill="#ffffff" font-family="sans-serif" font-size="14" text-anchor="middle">{left_label[:24]}</text>',
            f'<text x="365" y="145" fill="#111827" font-family="sans-serif" font-size="14" text-anchor="middle">{right_label[:24]}</text>',
            '<path d="M 215 140 C 245 120, 255 120, 285 140" stroke="#93c5fd" stroke-width="5" fill="none" />',
            '<polygon points="283,132 296,140 283,148" fill="#93c5fd" />',
            f'<text x="250" y="117" fill="#93c5fd" font-family="sans-serif" font-size="12" text-anchor="middle">{arrow_label[:32]}</text>',
            '<rect x="70" y="215" width="360" height="52" rx="10" fill="#0b1220" stroke="#64748b" stroke-width="2" />',
            f'<text x="250" y="246" fill="#f8fafc" font-family="sans-serif" font-size="15" text-anchor="middle">{bottom_text[:54]}</text>',
            '</svg>',
        ]
    )


def _render_nat5_svg(plan: dict, prompt: str) -> str:
    question = str(plan.get("question") or prompt)
    diagram_type = str(plan.get("diagram_type") or _infer_diagram_type(prompt)).lower()

    # Prompt-level explicit layout instructions should override model topic guesses.
    lowered_prompt = prompt.lower()
    if "on the left" in lowered_prompt and "on the right" in lowered_prompt:
        diagram_type = "described"

    if diagram_type == "described":
        return _render_described_svg(question, prompt)

    if diagram_type == "probability":
        bag_color = str(plan.get("bag_color") or "brown")
        tokens = plan.get("tokens")
        if not isinstance(tokens, list) or not tokens:
            tokens = _parse_probability_tokens(prompt)
        return _render_probability_svg(question, bag_color, tokens)

    if diagram_type == "geometry":
        lowered = prompt.lower()
        if "sector" in lowered or "arc length" in lowered or "radius" in lowered:
            return _render_sector_svg(question, prompt)
        return _render_geometry_svg(question)

    if diagram_type == "algebra":
        return _render_algebra_svg(question)

    if diagram_type == "graph":
        return _render_graph_svg(question)

    if diagram_type == "data":
        return _render_data_svg(question)

    return _render_generic_svg(question)


def _log_full_model_response(response: object) -> None:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        logger.info("[Gemma] Full response.text start\n%s\n[Gemma] Full response.text end", text)
    else:
        logger.info("[Gemma] response.text is not a string: %s", type(text).__name__)

    candidates = getattr(response, "candidates", None) or []
    logger.info("[Gemma] candidates=%d", len(candidates))
    for c_idx, candidate in enumerate(candidates):
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        logger.info("[Gemma] candidate[%d].parts=%d", c_idx, len(parts))
        for p_idx, part in enumerate(parts):
            is_thought = bool(getattr(part, "thought", False))
            logger.info("[Gemma] candidate[%d].part[%d].thought=%s", c_idx, p_idx, is_thought)
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str):
                logger.info(
                    "[Gemma] Full candidate[%d].part[%d].text start\n%s\n[Gemma] Full candidate[%d].part[%d].text end",
                    c_idx,
                    p_idx,
                    part_text,
                    c_idx,
                    p_idx,
                )
            else:
                logger.info(
                    "[Gemma] candidate[%d].part[%d].text is %s",
                    c_idx,
                    p_idx,
                    type(part_text).__name__,
                )


@lru_cache(maxsize=1)
def _build_client() -> genai.Client:
    settings = get_settings()
    if settings.gemini_api_key:
        return genai.Client(api_key=settings.gemini_api_key)
    return genai.Client()


def get_agent(agent_name: str) -> AgentDefinition:
    agent = load_agents().get(agent_name)
    if not agent:
        raise AgentNotFoundError(agent_name)
    return agent


async def generate_svg(prompt: str, agent_name: str) -> GenerateSvgResponse:
    agent = get_agent(agent_name)
    settings = get_settings()
    cache_key = f"{agent.name}::{prompt.strip()}"
    svg_cache = _load_svg_cache()
    if cache_key not in svg_cache and prompt.strip() == SECTOR_PROMPT_SEED:
        svg_cache[cache_key] = SECTOR_SVG_SEED
        _save_svg_cache(svg_cache)
    logger.info(
        "[Gemma] generate_svg called agent=%s model=%s prompt=%r",
        agent.name,
        agent.model,
        prompt,
    )

    client = _build_client()
    generation_prompt = (
        "Produce exactly one raw SVG element. The first non-whitespace character must be <. "
        "Use a 500x300 light-mode canvas with a white background and dark border. "
        "Do not output markdown, bullets, prose, code fences, XML comments, JSON, templates, or helper captions. "
        "Only include labels and annotations explicitly requested by the user. "
        "Keep the SVG minimal, self-contained, valid XML, and as close to one line as practical so it fits in one response. "
        "Use only the essential shapes and text needed for the diagram.\n\n"
        f"User request:\n{prompt}"
    )

    async def _request_svg(
        model_name: str,
        contents: str,
        config: types.GenerateContentConfig,
        *,
        label: str,
        as_json: bool,
    ) -> str:
        logger.info(
            "[Gemma] attempt=%s model=%s timeout=%.1fs max_output_tokens=%s temperature=%s",
            label,
            model_name,
            settings.generation_timeout_seconds,
            agent.config.max_output_tokens,
            agent.config.temperature,
        )
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            ),
            timeout=settings.generation_timeout_seconds,
        )
        _log_full_model_response(response)
        raw_text = _response_text(response)
        return _extract_svg_from_json_text(raw_text) if as_json else _extract_svg_from_text(raw_text)

    base_plain_config = types.GenerateContentConfig(
        system_instruction=agent.system_instruction,
        temperature=agent.config.temperature,
        top_p=agent.config.top_p,
        top_k=agent.config.top_k,
        max_output_tokens=agent.config.max_output_tokens,
        response_mime_type="text/plain",
    )

    strict_plain_prompt = (
        "Return exactly one raw SVG element only. The first non-whitespace character must be <. "
        "No bullets, no markdown, no explanation, no JSON wrapper, no templates, and no helper captions. "
        "Use exactly a 500x300 light-mode canvas and keep the SVG minimal and compact with only essential shapes and text. "
        "Follow this prompt exactly:\n\n"
        f"{prompt}"
    )

    json_follow_up_prompt = (
        "Return JSON only with one key named svg. "
        "The svg value must be one complete valid raw SVG element with opening <svg ...> and closing </svg>. "
        "No markdown, prose, or extra keys. "
        "Use a 500x300 light-mode canvas. Follow this prompt exactly:\n\n"
        f"{prompt}"
    )
    json_follow_up_config = types.GenerateContentConfig(
        system_instruction=agent.system_instruction,
        temperature=agent.config.temperature,
        top_p=agent.config.top_p,
        top_k=agent.config.top_k,
        max_output_tokens=agent.config.max_output_tokens,
        response_mime_type="application/json",
        response_json_schema={
            "type": "object",
            "properties": {
                "svg": {"type": "string"},
            },
            "required": ["svg"],
            "additionalProperties": False,
        },
    )

    candidate_models: list[str] = []
    for model_name in [agent.model, "models/gemini-3.5-flash", "models/gemini-2.0-flash"]:
        if model_name not in candidate_models:
            candidate_models.append(model_name)

    svg = ""
    selected_model = agent.model
    try:
        last_error: Exception | None = None
        for model_name in candidate_models:
            try:
                svg = await _request_svg(model_name, generation_prompt, base_plain_config, label="plain-primary", as_json=False)
                if not svg:
                    svg = await _request_svg(model_name, strict_plain_prompt, base_plain_config, label="plain-strict", as_json=False)
                if not svg:
                    svg = await _request_svg(model_name, json_follow_up_prompt, json_follow_up_config, label="json-fallback", as_json=True)
                if not svg:
                    # One final strict plain retry helps recover transient formatting drifts.
                    svg = await _request_svg(model_name, strict_plain_prompt, base_plain_config, label="plain-final", as_json=False)
                if svg:
                    selected_model = model_name
                    break
            except Exception as exc:  # pragma: no cover - API/network dependent
                last_error = exc
                if _is_quota_error(exc):
                    logger.warning("[Gemma] model %s quota-limited, trying fallback model", model_name)
                    continue
                raise

        if not svg and last_error and _is_quota_error(last_error):
            cached_svg = svg_cache.get(cache_key, "")
            if cached_svg and _is_valid_svg_candidate(cached_svg):
                logger.warning("[Gemma] using cached SVG due to quota exhaustion")
                return GenerateSvgResponse(
                    agent_name=agent.name,
                    model=f"cache:{agent.model}",
                    svg=cached_svg,
                )
            raise last_error
    except asyncio.TimeoutError as exc:
        logger.warning("[Gemma] request timed out after %.1fs", settings.generation_timeout_seconds)
        raise GenerationTimeoutError(
            f"Model request timed out after {settings.generation_timeout_seconds:.1f}s"
        ) from exc
    except Exception:
        logger.exception("[Gemma] generate_content failed")
        raise

    if not svg:
        logger.warning("[Gemma] no valid SVG found in model response")
        raise ValueError("Model response did not contain a valid SVG")

    logger.info("[Gemma] extracted SVG length=%d", len(svg))

    svg_cache[cache_key] = svg
    _save_svg_cache(svg_cache)

    return GenerateSvgResponse(
        agent_name=agent.name,
        model=selected_model,
        svg=svg,
    )