from __future__ import annotations

import re


class PathMatcher:
    _TEMPLATE_VAR_RE = re.compile(r"\$\{(\w+)\}")
    _PATH_PARAM_RE = re.compile(r"\{(\w+)\}")
    _API_PREFIX_RE = re.compile(r"^/api/v\d+")
    _MULTI_SLASH_RE = re.compile(r"/+")

    @classmethod
    def normalize_path(cls, path: str) -> str:
        path = cls._API_PREFIX_RE.sub("", path)
        path = cls._MULTI_SLASH_RE.sub("/", path)
        path = path.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return path

    @classmethod
    def template_var_to_param(cls, template_var: str) -> str:
        result = re.sub(r"([A-Z])", r"_\1", template_var).lower()
        if result.startswith("_"):
            result = result[1:]
        return result

    @classmethod
    def _normalize_for_matching(cls, path: str) -> str:
        path = cls.normalize_path(path)
        path = cls._TEMPLATE_VAR_RE.sub(lambda m: "{" + cls.template_var_to_param(m.group(1)) + "}", path)
        path = cls._PATH_PARAM_RE.sub("{param}", path)
        return path

    @classmethod
    def match(cls, pattern: str, candidates: list[str]) -> list[tuple[str, float]]:
        norm_pattern = cls._normalize_for_matching(pattern)
        results: list[tuple[str, float]] = []
        for candidate in candidates:
            norm_candidate = cls._normalize_for_matching(candidate)
            if norm_pattern == norm_candidate:
                results.append((candidate, 1.0))
            elif norm_pattern in norm_candidate or norm_candidate in norm_pattern:
                pattern_parts = [p for p in norm_pattern.split("/") if p]
                candidate_parts = [p for p in norm_candidate.split("/") if p]
                common = sum(
                    1 for p, c in zip(pattern_parts, candidate_parts) if p == c
                )
                max_parts = max(len(pattern_parts), len(candidate_parts))
                score = common / max_parts if max_parts > 0 else 0.0
                if score >= 0.5:
                    results.append((candidate, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    @classmethod
    def is_match(cls, path_a: str, path_b: str, threshold: float = 0.8) -> bool:
        results = cls.match(path_a, [path_b])
        return len(results) > 0 and results[0][1] >= threshold
