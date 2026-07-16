from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from typing import Any, Callable, Iterable


def safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def confusion(labels: list[int], scores: list[float], threshold: float) -> dict[str, int]:
    counts = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    for label, score in zip(labels, scores, strict=True):
        predicted = int(score >= threshold)
        if label and predicted:
            counts["tp"] += 1
        elif label:
            counts["fn"] += 1
        elif predicted:
            counts["fp"] += 1
        else:
            counts["tn"] += 1
    return counts


def threshold_metrics(labels: list[int], scores: list[float], threshold: float) -> dict[str, Any]:
    row = confusion(labels, scores, threshold)
    tp, tn, fp, fn = row["tp"], row["tn"], row["fp"], row["fn"]
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    return {
        "threshold": threshold,
        **row,
        "accuracy": safe_div(tp + tn, len(labels)),
        "precision": precision,
        "recall": recall,
        "f1": safe_div(2 * precision * recall, precision + recall) if precision is not None and recall is not None else None,
        "fpr": safe_div(fp, fp + tn),
        "fnr": safe_div(fn, fn + tp),
    }


def auroc(labels: list[int], scores: list[float]) -> float | None:
    positives = [score for label, score in zip(labels, scores, strict=True) if label == 1]
    negatives = [score for label, score in zip(labels, scores, strict=True) if label == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return wins / (len(positives) * len(negatives))


def auprc(labels: list[int], scores: list[float]) -> float | None:
    positive_count = sum(labels)
    if not positive_count:
        return None
    ranked = sorted(zip(scores, labels, strict=True), key=lambda item: -item[0])
    true_positives = 0
    false_positives = 0
    area = 0.0
    index = 0
    while index < len(ranked):
        score = ranked[index][0]
        group_labels: list[int] = []
        while index < len(ranked) and ranked[index][0] == score:
            group_labels.append(ranked[index][1])
            index += 1
        new_positives = sum(group_labels)
        true_positives += new_positives
        false_positives += len(group_labels) - new_positives
        if new_positives:
            area += (new_positives / positive_count) * (true_positives / (true_positives + false_positives))
    return area


def brier(targets: list[float], scores: list[float]) -> float | None:
    return sum((score - target) ** 2 for target, score in zip(targets, scores, strict=True)) / len(scores) if scores else None


def ece(targets: list[float], scores: list[float], bins: int = 10) -> float | None:
    if not scores:
        return None
    total = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        members = [
            (target, score)
            for target, score in zip(targets, scores, strict=True)
            if lower <= score < upper or (index == bins - 1 and score == 1.0)
        ]
        if members:
            observed = sum(item[0] for item in members) / len(members)
            predicted = sum(item[1] for item in members) / len(members)
            total += len(members) / len(scores) * abs(observed - predicted)
    return total


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap_ci(
    rows: list[Any], metric: Callable[[list[Any]], float | None], *, seed: int, iterations: int
) -> dict[str, float | int | None]:
    observed = metric(rows)
    if not rows or iterations <= 0:
        return {"estimate": observed, "low": None, "high": None, "validReplicates": 0}
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(iterations):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        value = metric(sample)
        if value is not None and math.isfinite(value):
            estimates.append(value)
    return {
        "estimate": observed,
        "low": percentile(estimates, 0.025),
        "high": percentile(estimates, 0.975),
        "validReplicates": len(estimates),
    }


def merge_ranges(ranges: Iterable[tuple[int, int]], text_length: int) -> list[tuple[int, int]]:
    normalized = sorted((max(0, start), min(text_length, end)) for start, end in ranges if end > start)
    merged: list[list[int]] = []
    for start, end in normalized:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def overlap_length(left: list[tuple[int, int]], right: list[tuple[int, int]]) -> int:
    total = 0
    i = j = 0
    while i < len(left) and j < len(right):
        total += max(0, min(left[i][1], right[j][1]) - max(left[i][0], right[j][0]))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return total


def sentence_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for match in re.finditer(r"[^.!?]+(?:[.!?]+(?=\s|$)|$)", text, re.MULTILINE):
        start, end = match.span()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            ranges.append((start, end))
    return ranges


def span_metrics(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    char_tp = char_fp = char_fn = 0
    sentence_tp = sentence_tn = sentence_fp = sentence_fn = 0
    for row in rows:
        text = row["text"]
        length = len(text)
        gold = merge_ranges(((span["start"], span["end"]) for span in row["goldSpans"]), length)
        predicted = merge_ranges(
            ((span["start"], span["end"]) for span in row["predictedSpans"] if span["score"] >= threshold),
            length,
        )
        intersection = overlap_length(gold, predicted)
        gold_size = sum(end - start for start, end in gold)
        predicted_size = sum(end - start for start, end in predicted)
        char_tp += intersection
        char_fp += predicted_size - intersection
        char_fn += gold_size - intersection
        for start, end in sentence_ranges(text):
            sentence = [(start, end)]
            gold_positive = overlap_length(gold, sentence) / (end - start) >= 0.5
            pred_positive = overlap_length(predicted, sentence) / (end - start) >= 0.5
            if gold_positive and pred_positive:
                sentence_tp += 1
            elif gold_positive:
                sentence_fn += 1
            elif pred_positive:
                sentence_fp += 1
            else:
                sentence_tn += 1
    sentence_precision = safe_div(sentence_tp, sentence_tp + sentence_fp)
    sentence_recall = safe_div(sentence_tp, sentence_tp + sentence_fn)
    union = char_tp + char_fp + char_fn
    return {
        "sentence": {
            "tp": sentence_tp, "tn": sentence_tn, "fp": sentence_fp, "fn": sentence_fn,
            "precision": sentence_precision,
            "recall": sentence_recall,
            "f1": safe_div(2 * sentence_precision * sentence_recall, sentence_precision + sentence_recall)
            if sentence_precision is not None and sentence_recall is not None else None,
        },
        "rangeOverlap": {
            "intersectionCharacters": char_tp,
            "predictedCharacters": char_tp + char_fp,
            "goldCharacters": char_tp + char_fn,
            "iou": safe_div(char_tp, union),
            "dice": safe_div(2 * char_tp, 2 * char_tp + char_fp + char_fn),
        },
    }


def provider_agreement(predictions: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    by_provider: dict[str, dict[str, float]] = defaultdict(dict)
    versions: dict[str, set[str]] = defaultdict(set)
    for row in predictions:
        if row["status"] == "success" and row["score"] is not None:
            by_provider[row["provider"]][row["sampleId"]] = row["score"]
            versions[row["provider"]].add(row["providerVersion"])
    providers = sorted(by_provider)
    output: list[dict[str, Any]] = []
    for left_index, left in enumerate(providers):
        for right in providers[left_index + 1 :]:
            common = sorted(set(by_provider[left]) & set(by_provider[right]))
            matrix = {"bothNegative": 0, "leftPositiveRightNegative": 0, "leftNegativeRightPositive": 0, "bothPositive": 0}
            score_deltas: list[float] = []
            for sample_id in common:
                left_positive = by_provider[left][sample_id] >= threshold
                right_positive = by_provider[right][sample_id] >= threshold
                key = (
                    "bothPositive" if left_positive and right_positive else
                    "leftPositiveRightNegative" if left_positive else
                    "leftNegativeRightPositive" if right_positive else "bothNegative"
                )
                matrix[key] += 1
                score_deltas.append(abs(by_provider[left][sample_id] - by_provider[right][sample_id]))
            agreements = matrix["bothNegative"] + matrix["bothPositive"]
            output.append({
                "left": left, "right": right, "n": len(common), "threshold": threshold,
                "agreementRate": safe_div(agreements, len(common)), "matrix": matrix,
                "meanAbsoluteScoreDifference": safe_div(sum(score_deltas), len(score_deltas)),
                "leftVersions": sorted(versions[left]), "rightVersions": sorted(versions[right]),
            })
    return output


def drift_report(previous: list[dict[str, Any]], current: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    def index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
        return {
            (row["provider"], row["sampleId"]): row
            for row in rows if row["status"] == "success" and row["score"] is not None
        }

    before, after = index(previous), index(current)
    keys = sorted(set(before) & set(after))
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for key in keys:
        grouped[key[0]].append((before[key], after[key]))
    providers = []
    for provider, pairs in sorted(grouped.items()):
        deltas = [new["score"] - old["score"] for old, new in pairs]
        flips = sum((old["score"] >= threshold) != (new["score"] >= threshold) for old, new in pairs)
        old_versions = sorted({old["providerVersion"] for old, _ in pairs})
        new_versions = sorted({new["providerVersion"] for _, new in pairs})
        mean_abs = sum(abs(delta) for delta in deltas) / len(deltas)
        flip_rate = flips / len(pairs)
        providers.append({
            "provider": provider, "n": len(pairs), "previousVersions": old_versions, "currentVersions": new_versions,
            "meanScoreShift": sum(deltas) / len(deltas), "meanAbsoluteScoreShift": mean_abs,
            "maxAbsoluteScoreShift": max(abs(delta) for delta in deltas), "classificationFlipRate": flip_rate,
            "versionChanged": old_versions != new_versions,
            "alert": mean_abs >= 0.10 or flip_rate >= 0.10 or old_versions != new_versions,
        })
    return {"threshold": threshold, "matchedPredictions": len(keys), "providers": providers}
