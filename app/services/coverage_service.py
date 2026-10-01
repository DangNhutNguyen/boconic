"""
Coverage service for partial materials and authorized collection page ranges.
Strict mathematical interval union and overlap calculation.
Policy: Different editions or pagination bases CANNOT be merged.
"""
from typing import Any, Dict, List, Optional, Tuple


class CoverageService:
    @staticmethod
    def normalize_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        Validate and sort 1-indexed page ranges.
        Each range must satisfy 1 <= start <= end.
        """
        valid = []
        for r in ranges:
            if not isinstance(r, (list, tuple)) or len(r) != 2:
                continue
            start, end = int(r[0]), int(r[1])
            if start < 1 or end < start:
                continue
            valid.append((start, end))
        return sorted(valid, key=lambda x: (x[0], x[1]))

    @classmethod
    def calculate_union(cls, ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        Calculate mathematical union of sorted intervals.
        Example: [(1, 10), (8, 17)] -> [(1, 17)]
        Example: [(1, 10), (11, 20)] -> [(1, 20)]
        """
        cleaned = cls.normalize_ranges(ranges)
        if not cleaned:
            return []

        merged: List[Tuple[int, int]] = []
        cur_start, cur_end = cleaned[0]

        for start, end in cleaned[1:]:
            if start <= cur_end + 1:  # contiguous or overlapping
                cur_end = max(cur_end, end)
            else:
                merged.append((cur_start, cur_end))
                cur_start, cur_end = start, end
        merged.append((cur_start, cur_end))
        return merged

    @classmethod
    def calculate_unique_pages(cls, ranges: List[Tuple[int, int]]) -> int:
        """
        Returns total unique pages across all ranges by summing lengths of union intervals.
        """
        union_intervals = cls.calculate_union(ranges)
        return sum((end - start + 1) for start, end in union_intervals)

    @classmethod
    def calculate_overlap(cls, ranges: List[Tuple[int, int]]) -> Tuple[int, List[Tuple[int, int]]]:
        """
        Calculate overlapping pages and overlap segments across multiple sources.
        Example: [(1, 10), (8, 17)] -> 3 overlapping pages (pages 8, 9, 10), segments: [(8, 10)].
        """
        cleaned = cls.normalize_ranges(ranges)
        if len(cleaned) < 2:
            return 0, []

        page_counts: Dict[int, int] = {}
        for start, end in cleaned:
            for p in range(start, end + 1):
                page_counts[p] = page_counts.get(p, 0) + 1

        overlap_pages = sorted([p for p, count in page_counts.items() if count > 1])
        if not overlap_pages:
            return 0, []

        overlap_intervals: List[Tuple[int, int]] = []
        cur_start = overlap_pages[0]
        cur_end = cur_start

        for p in overlap_pages[1:]:
            if p == cur_end + 1:
                cur_end = p
            else:
                overlap_intervals.append((cur_start, cur_end))
                cur_start = p
                cur_end = p
        overlap_intervals.append((cur_start, cur_end))

        total_overlap_pages = len(overlap_pages)
        return total_overlap_pages, overlap_intervals

    @classmethod
    def calculate_gaps(
        cls,
        target_start: int,
        target_end: int,
        covered_ranges: List[Tuple[int, int]],
    ) -> List[Tuple[int, int]]:
        """
        Calculate missing page segments between target_start and target_end given covered_ranges.
        """
        if target_start > target_end:
            return []
        union_intervals = cls.calculate_union(covered_ranges)
        gaps: List[Tuple[int, int]] = []
        cur = target_start

        for c_start, c_end in union_intervals:
            if c_end < cur:
                continue
            if c_start > target_end:
                break
            if c_start > cur:
                gaps.append((cur, min(c_start - 1, target_end)))
            cur = max(cur, c_end + 1)
            if cur > target_end:
                break

        if cur <= target_end:
            gaps.append((cur, target_end))
        return gaps

    @classmethod
    def analyze_coverage(
        cls,
        target_ranges: List[Tuple[int, int]],
        source_ranges: List[Tuple[int, int]],
        total_book_pages: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Full analytical report comparing target needed ranges against provided source ranges.
        Never fabricates total_pages or false percentages.
        """
        target_union = cls.calculate_union(target_ranges)
        source_union = cls.calculate_union(source_ranges)
        overlap_count, overlap_segments = cls.calculate_overlap(source_ranges)

        target_pages = sum((end - start + 1) for start, end in target_union) if target_union else None
        source_unique_pages = cls.calculate_unique_pages(source_ranges)

        gaps: List[Tuple[int, int]] = []
        if target_union:
            for t_start, t_end in target_union:
                g = cls.calculate_gaps(t_start, t_end, source_ranges)
                gaps.extend(g)

        pct: Optional[float] = None
        if target_pages and target_pages > 0:
            covered_target_pages = target_pages - sum((end - start + 1) for start, end in gaps)
            pct = round((covered_target_pages / target_pages) * 100.0, 1)
        elif total_book_pages and total_book_pages > 0:
            pct = round(min(100.0, (source_unique_pages / total_book_pages) * 100.0), 1)

        return {
            "target_union": target_union,
            "source_union": source_union,
            "target_pages": target_pages,
            "source_unique_pages": source_unique_pages,
            "overlap_pages": overlap_count,
            "overlap_segments": overlap_segments,
            "gaps": gaps,
            "coverage_percentage": pct,
        }
