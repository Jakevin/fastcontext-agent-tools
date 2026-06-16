from __future__ import annotations

from html import escape
from typing import TypedDict


class WrapperCheck(TypedDict):
    status: str


class WrapperSummary(TypedDict):
    generated_at: str
    checks: list[WrapperCheck]


def render_svg(summary: WrapperSummary) -> str:
    checks = summary["checks"]
    passed = sum(1 for check in checks if check["status"] == "pass")
    failed = len(checks) - passed
    wrapper_status = f"{passed}/{len(checks)} checks pass"
    if failed:
        wrapper_status = f"{passed}/{len(checks)} checks pass, {failed} fail"

    generated = summary["generated_at"].replace("T", " ").replace("+00:00", " UTC")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="640" viewBox="0 0 960 640" role="img" aria-labelledby="title desc">
  <title id="title">FastContext evidence split by source</title>
  <desc id="desc">Official Microsoft benchmark data is separated from this repository's local token smoke tests and integration QA checks.</desc>
  <style>
    .title {{ font: 700 28px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #17202a; }}
    .subtitle {{ font: 400 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #52616b; }}
    .card-title {{ font: 700 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #17202a; }}
    .label {{ font: 600 15px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #1f2933; }}
    .body {{ font: 400 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #334e68; }}
    .metric {{ font: 700 26px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #0b7285; }}
    .metric-label {{ font: 600 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #334e68; }}
    .pill {{ font: 700 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #ffffff; }}
    .fine {{ font: 400 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #52616b; }}
    .note {{ font: 400 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #52616b; }}
  </style>
  <rect width="960" height="640" fill="#f8faf9"/>
  <rect x="24" y="24" width="912" height="592" rx="12" fill="#ffffff" stroke="#d6dde2"/>

  <text x="48" y="68" class="title">FastContext Evidence: Official vs Local</text>
  <text x="48" y="94" class="subtitle">Generated {generated} - official claims, local token smoke test, and QA are separated.</text>

  <rect x="48" y="122" width="864" height="98" rx="10" fill="#f8fafc" stroke="#cbd5e1"/>
  <text x="72" y="154" class="card-title">Conceptual workflow contract</text>
  <text x="72" y="184" class="body">Direct exploration: solver reads and searches repository context itself.</text>
  <text x="72" y="204" class="fine">Delegated exploration: FastContext returns candidate file-line citations.</text>
  <rect x="452" y="166" width="44" height="28" rx="14" fill="#334e68"/>
  <text x="462" y="185" class="pill">not</text>
  <text x="520" y="184" class="body">Local smoke benchmarks: two tasks run.</text>
  <text x="520" y="204" class="fine">Current local results did not show token wins.</text>

  <rect x="48" y="250" width="410" height="300" rx="10" fill="#ecfdf5" stroke="#a7f3d0"/>
  <text x="72" y="288" class="card-title">Official Microsoft benchmark data</text>
  <text x="72" y="316" class="fine">Source: Microsoft FastContext repo, model card, and paper.</text>

  <text x="72" y="358" class="metric">+5.5</text>
  <text x="152" y="358" class="metric-label">up to end-to-end score improvement</text>
  <text x="72" y="408" class="metric">60.3%</text>
  <text x="174" y="408" class="metric-label">up to fewer main-agent tokens</text>
  <text x="72" y="448" class="fine">Meaning: model-quality / end-to-end benchmark result.</text>
  <text x="72" y="474" class="fine">Not re-run by this repository.</text>
  <text x="72" y="500" class="fine">Use for upstream FastContext impact claims only.</text>

  <rect x="502" y="250" width="410" height="300" rx="10" fill="#eff6ff" stroke="#bfdbfe"/>
  <text x="526" y="288" class="card-title">Local token smoke tests</text>
  <text x="526" y="316" class="fine">Same question before/after, main-agent context only.</text>

  <text x="526" y="354" class="metric">MICE</text>
  <text x="612" y="354" class="metric-label">7,039 direct -> 10,910 corrected (+55.0%)</text>
  <text x="526" y="390" class="fine">FastContext raw: 198 tokens, missed the endpoint.</text>
  <text x="526" y="432" class="metric">FanPlan</text>
  <text x="640" y="432" class="metric-label">2,279 direct -> 2,360 corrected (+3.6%)</text>
  <text x="526" y="468" class="fine">FastContext raw: 81 tokens, cited nonexistent paths.</text>
  <text x="526" y="494" class="fine">MICE matrix: 3 query styles x 2 repeats, 0/6 ground-truth hits.</text>
  <text x="526" y="520" class="fine">Official preflight: not ready; endpoint, SGLang, CUDA blockers.</text>
  <text x="526" y="536" class="fine">Benchmark gate: upstream built; credentials/serving blockers remain.</text>
  <text x="526" y="552" class="fine">Wrapper QA remains separate: {escape(wrapper_status)}.</text>

  <text x="48" y="594" class="note">Local smoke tests are small and task-specific. Official task-impact claims remain attributed to Microsoft.</text>
</svg>
"""
