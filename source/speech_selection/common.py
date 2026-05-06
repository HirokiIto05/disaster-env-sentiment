def match_tokens(tokens, query_terms):
    """
    Determine if a set of tokens matches a set of query terms.
    """
    tokens = [t.lower() for t in tokens]

    overlap = set(tokens).intersection(query_terms["exact_unigrams"])
    if overlap:
        return True

    bigrams = [tokens[i - 1] + " " + tokens[i] for i in range(1, len(tokens))]
    overlap = set(bigrams).intersection(query_terms["exact_bigrams"])
    if overlap:
        return True

    prefixes = {t[:11] for t in tokens}
    if prefixes.intersection(query_terms["p11"]):
        return True
    prefixes = {t[:10] for t in prefixes}
    if prefixes.intersection(query_terms["p10"]):
        return True
    prefixes = {t[:9] for t in prefixes}
    if prefixes.intersection(query_terms["p9"]):
        return True
    prefixes = {t[:8] for t in prefixes}
    if prefixes.intersection(query_terms["p8"]):
        return True
    prefixes = {t[:7] for t in prefixes} - query_terms["seven_letter_exclude"]
    if prefixes.intersection(query_terms["p7"]):
        return True
    prefixes = {t[:6] for t in prefixes}
    if prefixes.intersection(query_terms["p6"]):
        return True
    prefixes = {t[:5] for t in prefixes}
    if prefixes.intersection(query_terms["p5"]):
        return True
    prefixes = {t[:4] for t in prefixes}
    if prefixes.intersection(query_terms["p4"]):
        return True
    prefixes = {t[:3] for t in prefixes}
    if prefixes.intersection(query_terms["p3"]):
        return True
    prefixes = {t[:2] for t in prefixes}
    if prefixes.intersection(query_terms["p2"]):
        return True

    return False
