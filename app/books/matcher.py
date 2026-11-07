import re
from difflib import SequenceMatcher
from typing import Dict, Any, List
from app.books.parser import normalize_text, extract_edition, extract_year

def token_similarity(a: str, b: str) -> float:
    """Calculate balanced token overlap, Jaccard similarity, and sequence ratio."""
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0

    # Intersection ratio (how much of requested title is in candidate)
    intersection = tokens_a.intersection(tokens_b)
    overlap_ratio = len(intersection) / len(tokens_a)

    # Jaccard ratio (penalizes candidate if it contains many extra unrelated words)
    union = tokens_a.union(tokens_b)
    jaccard_ratio = len(intersection) / len(union) if union else 0.0

    # Sequence ratio
    seq_ratio = SequenceMatcher(None, a, b).ratio()

    # Balanced blend: prevents short queries from getting 100% on long unrelated book titles
    return (overlap_ratio * 0.45) + (jaccard_ratio * 0.35) + (seq_ratio * 0.20)

def score_candidate(
    candidate: Dict[str, Any],
    requested_title: str,
    requested_author: str = "",
    requested_edition: str = "",
    weights: Dict[str, float] = None
) -> float:
    """
    Calculate confidence score (0.0 to 100.0) based on title, author, edition, and relevance.
    Default weights:
      - Title: 60%
      - Author: 25%
      - Edition: 10%
      - Relevance: 5%
    """
    if weights is None:
        weights = {
            "title": 60.0,
            "author": 25.0,
            "edition": 10.0,
            "relevance": 5.0
        }

    w_title = weights.get("title", 60.0)
    w_author = weights.get("author", 25.0)
    w_edition = weights.get("edition", 10.0)
    w_relevance = weights.get("relevance", 5.0)

    filename = candidate.get("filename", "")
    caption = candidate.get("caption", "")
    combined_target = normalize_text(f"{filename} {caption}")
    norm_title = normalize_text(requested_title)
    norm_author = normalize_text(requested_author)

    # 1. Title Similarity (0.0 to 1.0)
    norm_fn = normalize_text(filename)
    sim = token_similarity(norm_title, norm_fn)
    if norm_title == norm_fn:
        title_score = 1.0
    elif norm_title in norm_fn or norm_title in combined_target:
        len_ratio = len(norm_title) / max(len(norm_fn), len(norm_title))
        title_score = max(sim, min(1.0, 0.90 + (len_ratio * 0.10)))
    else:
        title_score = sim

    # Fiction / Unrelated Penalty:
    # If the user did not request fiction/novel, but candidate explicitly contains fiction tags
    fiction_markers = {"ልብወለድ", "ልቦለድ", "fiction", "novel", "ታሪካዊ ልብወለድ"}
    is_requested_fiction = any(m in norm_title for m in fiction_markers)
    has_candidate_fiction = any(m in norm_fn or m in normalize_text(caption) for m in fiction_markers)
    if not is_requested_fiction and has_candidate_fiction:
        title_score = max(0.05, title_score - 0.45)

    # 2. Author Similarity (0.0 to 1.0)
    if requested_author:
        if norm_author in combined_target:
            author_score = 1.0
        else:
            # Check individual author tokens (e.g. Silberschatz)
            author_tokens = norm_author.split()
            matched_tokens = [t for t in author_tokens if t in combined_target]
            author_score = len(matched_tokens) / len(author_tokens) if author_tokens else 0.0
    else:
        # If no author was requested, we redistribute the author weight to title
        w_title += w_author
        author_score = 0.0
        w_author = 0.0

    # 3. Edition / Year Similarity (0.0 to 1.0)
    req_edition = requested_edition or extract_edition(requested_title)
    cand_edition = extract_edition(filename) or extract_edition(caption)
    
    if req_edition:
        if cand_edition and req_edition.lower() == cand_edition.lower():
            edition_score = 1.0
        elif cand_edition:
            edition_score = 0.5  # Different edition found
        else:
            edition_score = 0.2  # Edition requested but not stated in filename
    else:
        # If no edition requested, existence of any edition is a slight bonus
        edition_score = 1.0 if cand_edition else 0.8

    # 4. Relevance / Extension / Structure (0.0 to 1.0)
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    relevance_score = 1.0 if ext in ("pdf", "epub", "mobi", "djvu") else 0.5

    # Calculate weighted total
    total_weight = w_title + w_author + w_edition + w_relevance
    raw_score = (
        (title_score * w_title) +
        (author_score * w_author) +
        (edition_score * w_edition) +
        (relevance_score * w_relevance)
    )

    final_score = (raw_score / total_weight) * 100.0 if total_weight > 0 else 0.0
    return round(min(100.0, max(0.0, final_score)), 1)

def rank_candidates(
    candidates: List[Dict[str, Any]],
    requested_title: str,
    author: str = "",
    edition: str = "",
    weights: Dict[str, float] = None
) -> List[Dict[str, Any]]:
    """Rank list of candidate files by confidence score in descending order."""
    scored = []
    for cand in candidates:
        cand_copy = dict(cand)
        cand_copy["confidence"] = score_candidate(cand, requested_title, author, edition, weights)
        scored.append(cand_copy)

    # Sort highest confidence first
    scored.sort(key=lambda x: x["confidence"], reverse=True)
    return scored
