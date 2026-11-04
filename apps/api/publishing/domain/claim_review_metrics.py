"""Agreement with recorded human feedback, not scientific accuracy or expert sign-off."""


def summarize(reviews):
    result = {
        "reviewed_claims": len(reviews),
        "comparable": 0,
        "agreement": 0,
        "model_adopted_human_unsupported": 0,
        "model_withheld_human_supported": 0,
        "human_uncertain": 0,
        "model_unchecked": 0,
        "agreement_rate": None,
        "scope": "latest recorded human feedback; not a scientific accuracy estimate",
    }
    for review in reviews:
        support = review.claim_json.get("support", {})
        if review.verdict == "uncertain":
            result["human_uncertain"] += 1
            continue
        if support.get("method") != "ai_context_check" or support.get("status") not in {
            "supported",
            "insufficient",
            "contradicted",
        }:
            result["model_unchecked"] += 1
            continue
        result["comparable"] += 1
        adopted = support["status"] == "supported"
        human_support = review.verdict == "supported"
        if adopted == human_support:
            result["agreement"] += 1
        elif adopted:
            result["model_adopted_human_unsupported"] += 1
        else:
            result["model_withheld_human_supported"] += 1
    if result["comparable"]:
        result["agreement_rate"] = result["agreement"] / result["comparable"]
    return result
