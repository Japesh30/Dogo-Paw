"""Part B — Adopter Segmentation (unsupervised learning).

Groups adopters into personas with k-means, using no labels at all — only the
profile each adopter submitted to the matcher.

    python -m ml.segmentation      # run against the live database and print

Naming the clusters
-------------------
k-means returns "cluster 0, 1, 2", which means nothing to anyone reading the
dashboard. Rather than hardcoding a cluster-number -> name mapping (which would
silently become wrong the moment the data shifts and the clusters renumber),
`label_centroid` derives each name from the centroid itself: it compares that
centroid against the average of all of them and describes whichever traits
deviate most. Re-run it on different data and the names follow the data.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from ml.features import ADOPTER_FEATURES, adopter_vector

RANDOM_STATE = 42
CANDIDATE_K = (3, 4)

# How a feature reads when it is unusually high or unusually low for a cluster.
TRAIT_WORDS = {
    "adopter_activity": ("High-Energy", "Low-Key"),
    "adopter_space": ("Large-Home", "Apartment"),
    "adopter_experience": ("Experienced", "First-Time"),
    "adopter_has_kids": ("Family", "Child-Free"),
    "adopter_has_other_pets": ("Multi-Pet", "Pet-Free"),
}

TRAIT_SENTENCES = {
    "adopter_activity": (
        "active households that can give a dog plenty of exercise",
        "quieter households suited to calmer dogs",
    ),
    "adopter_space": (
        "homes with generous indoor and outdoor space",
        "smaller homes and apartments",
    ),
    "adopter_experience": (
        "adopters who have handled dogs before",
        "first-time adopters who need more support",
    ),
    "adopter_has_kids": (
        "homes with children",
        "homes without children",
    ),
    "adopter_has_other_pets": (
        "homes that already have other pets",
        "homes where the dog would be the only pet",
    ),
}

# Below this, a deviation is not worth putting in a name.
MIN_DEVIATION = 0.12


def _describe(centroid: np.ndarray, mean: np.ndarray, max_traits: int) -> tuple[list[str], list[str]]:
    """The traits that make this centroid different, strongest first."""
    deviations = centroid - mean
    order = np.argsort(-np.abs(deviations))

    words, sentences = [], []
    for i in order[:max_traits]:
        if abs(deviations[i]) < MIN_DEVIATION:
            continue
        feature = ADOPTER_FEATURES[i]
        high = deviations[i] > 0
        words.append(TRAIT_WORDS[feature][0 if high else 1])
        sentences.append(TRAIT_SENTENCES[feature][0 if high else 1])
    return words, sentences


def label_centroid(
    centroid: np.ndarray, mean: np.ndarray, taken: set[str]
) -> tuple[str, str]:
    """Turn one centroid into a human-readable name + description.

    Widens to more traits if the shorter name is already used by another
    cluster, so two segments never share a label.
    """
    for n_traits in (2, 3, 4, 5):
        words, sentences = _describe(centroid, mean, n_traits)
        if not words:
            break
        name = f"{' '.join(words)} Households"
        if name not in taken:
            description = "Mostly " + ", and ".join(sentences) + "."
            return name, description

    # Everything about this cluster sits near the average.
    fallback = "Balanced Households"
    suffix = 2
    name = fallback
    while name in taken:
        name = f"{fallback} ({suffix})"
        suffix += 1
    return name, "Adopters whose profiles sit close to the overall average."


def segment(adopters: list[dict], k: int | None = None) -> dict:
    """Cluster the given adopters and describe each group."""
    if len(adopters) < 3:
        return {
            "available": False,
            "reason": "Need at least 3 adopter profiles to find segments.",
            "n_adopters": len(adopters),
            "segments": [],
        }

    X = np.vstack([adopter_vector(a) for a in adopters])

    # Never ask for more clusters than there are distinct profiles.
    distinct = len({tuple(row) for row in X.tolist()})
    candidates = [c for c in (CANDIDATE_K if k is None else (k,)) if c <= distinct]
    if not candidates:
        candidates = [max(2, min(distinct, 2))]

    # Pick k by silhouette rather than by assertion.
    best = None
    scores = {}
    for candidate in candidates:
        km = KMeans(n_clusters=candidate, n_init=10, random_state=RANDOM_STATE)
        labels = km.fit_predict(X)
        score = (
            float(silhouette_score(X, labels))
            if len(set(labels)) > 1
            else float("-inf")
        )
        scores[candidate] = round(score, 4)
        if best is None or score > best[0]:
            best = (score, candidate, km, labels)

    score, chosen_k, km, labels = best
    overall_mean = km.cluster_centers_.mean(axis=0)

    segments, taken = [], set()
    # Largest cluster first, so the dashboard leads with the common case.
    for cluster_id in np.argsort(-np.bincount(labels, minlength=chosen_k)):
        centroid = km.cluster_centers_[cluster_id]
        name, description = label_centroid(centroid, overall_mean, taken)
        taken.add(name)

        members = int((labels == cluster_id).sum())
        segments.append(
            {
                "cluster_id": int(cluster_id),
                "label": name,
                "description": description,
                "count": members,
                "share": round(members / len(adopters) * 100, 1),
                "centroid": {
                    feature: round(float(value), 3)
                    for feature, value in zip(ADOPTER_FEATURES, centroid)
                },
            }
        )

    return {
        "available": True,
        "n_adopters": len(adopters),
        "k": int(chosen_k),
        "silhouette": round(score, 4),
        "silhouette_by_k": scores,
        "algorithm": "KMeans",
        "features": ADOPTER_FEATURES,
        "segments": segments,
    }


if __name__ == "__main__":
    import json

    from app import create_app
    from models import Adopter

    with create_app().app_context():
        rows = [a.to_dict() for a in Adopter.query.all()]

    result = segment(rows)
    print(json.dumps({k: v for k, v in result.items() if k != "segments"}, indent=2))
    print()
    for s in result["segments"]:
        print(f"  {s['label']}  —  {s['count']} adopters ({s['share']}%)")
        print(f"     {s['description']}")
        print(f"     centroid: {s['centroid']}")
        print()
