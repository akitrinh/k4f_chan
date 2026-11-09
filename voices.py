"""Channel voices and conservative, source-aligned Vietnamese pronoun edits."""

import math
import re
from collections.abc import Sequence


Span = tuple[int, int]
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
_QUOTATION = re.compile(r'''"[^"]*"|“[^”]*”|‘[^’]*’|(?<!\w)'[^'\r\n]*'(?!\w)''')
_REPORTING = re.compile(
    r"\b(?:said|says|say|told|tell|tells|asked|asks|ask|replied|replies|"
    r"whispered|shouted|wrote|writes|answered|explained|remarked|quoted)\b",
    re.IGNORECASE,
)
_FAMILY_VOCATIVE = re.compile(
    r"(?:^|[,;.!?\r\n])\s*(?:(?:dear|hey|hello|hi|oh)\s+)?"
    r"(?:mom|mum|mother|mama|mommy|dad|father|papa|daddy|grandma|grandpa|"
    r"grandmother|grandfather|sis|brother|sister|aunt|uncle|son|daughter)"
    r"\s*(?:[,!:]|[.!?]?\s*$)",
    re.IGNORECASE,
)
_PLURAL_YOU = re.compile(
    r"\b(?:all|both|each|any|some|none|one|two|three|four|five|six|seven|eight|nine|ten)\s+of\s+you\b"
    r"|\byou\s+(?:all|both|two|three|four|five|six|seven|eight|nine|ten|"
    r"guys|girls|boys|ladies|gentlemen|people|folks|soldiers|nikke|nikkes)\b"
    r"|\byou(?:['’](?:re|ve|ll|d)|\s+(?:are|were|have|had|can|could|will|would|"
    r"shall|should|must|may|might|do|did))\s+(?:not\s+)?(?:all|both|each)\b"
    r"|\by['’]all\b|\byourselves\b",
    re.IGNORECASE,
)
_SINGULAR = frozenset({
    'tôi', 'ta', 'tao', 'tớ', 'mình', 'bạn', 'anh', 'chị', 'em', 'cô',
    'chú', 'bác', 'cậu', 'ngài', 'ông', 'bà', 'mày', 'mi', 'ngươi',
    'bố', 'cha', 'mẹ', 'con', 'ba', 'má',
})
_KINSHIP_ADDRESS = frozenset({'bố', 'cha', 'mẹ', 'con', 'ba', 'má'})
_ENGLISH_PERSON = frozenset({
    'i', 'me', 'my', 'mine', 'you', 'your', 'yours', 'he', 'him', 'his',
    'she', 'her', 'hers', 'they', 'them', 'their', 'theirs', 'we', 'us',
    'our', 'ours', 'it', 'its', 'myself', 'yourself', 'himself', 'herself',
    'themselves', 'ourselves', 'yourselves', 'itself',
})
_OBJECT_PREPOSITION = frozenset({
    'to', 'with', 'for', 'at', 'in', 'on', 'of', 'from', 'by', 'about',
    'against', 'beside', 'behind', 'between', 'toward', 'towards', 'without',
    'around', 'before', 'after',
})
_PLURAL_PREFIX = frozenset({'chúng', 'tụi', 'bọn', 'các', 'những', 'mấy', 'mọi'})
_THIRD_PERSON_SUFFIX = frozenset({'ấy', 'ta', 'đó', 'kia', 'này', 'đấy'})
_NOUN_COMPLEMENTS = {
    'anh': {'trai', 'em', 'hùng'}, 'chị': {'gái'},
    'em': {'trai', 'gái', 'bé'}, 'cô': {'gái', 'giáo'},
    'cậu': {'bé', 'chủ'}, 'bác': {'sĩ'}, 'chú': {'hề'},
    'ông': {'chủ', 'nội', 'ngoại', 'lão'},
    'bà': {'chủ', 'nội', 'ngoại', 'lão'},
    'bạn': {'bè', 'đời', 'trai', 'gái', 'học', 'thân'},
    'bố': {'mẹ', 'dượng'}, 'cha': {'mẹ', 'dượng'},
    'mẹ': {'cha', 'kế'}, 'con': {'trai', 'gái'},
    'ba': {'má'}, 'má': {'ba'},
}


def pronouns_for(role: str) -> tuple[str, str | None]:
    """Return the self-pronoun and optional fixed addressee for a speaker role."""
    if role == 'neutral':
        return 'tôi', None
    if role == 'nikke':
        return 'em', 'anh'
    if role == 'commander':
        return 'anh', 'em'
    raise ValueError(f'Unsupported speaker role: {role!r}')


def _overlap(left: Span, right: Span) -> int:
    return max(0, min(left[1], right[1]) - max(left[0], right[0]))


def _source_roles(text: str, words: list[re.Match]) -> list[int | None]:
    # Quoted dialogue with a reporting frame can have a different speaker AND
    # addressee. Keep that model translation rather than guessing their identity.
    quotes = list(_QUOTATION.finditer(text))
    frame = _QUOTATION.sub('', text)
    # Explicit kinship vocatives identify an addressee outside the fixed pair.
    # Retain that relationship rather than imposing anh/em on a parent/child.
    if _FAMILY_VOCATIVE.search(frame):
        return [None] * len(words)
    reported = [quote.span() for quote in quotes] if _REPORTING.search(frame) else []
    # An explicit group address licenses plural you/your throughout that sentence.
    group_sentences = [
        sentence.span()
        for sentence in re.finditer(r'[^.!?\r\n]+', text)
        if _PLURAL_YOU.search(sentence.group())
    ]
    roles = []
    for word in words:
        value = word.group().casefold().replace('’', "'")
        if any(_overlap(word.span(), quote) for quote in reported):
            roles.append(None)
        elif value in {'i', 'me', 'my', 'mine'} or re.fullmatch(r"i'(?:m|ll|d|ve)", value):
            roles.append(0)
        elif value in {'you', 'your', 'yours'} or re.fullmatch(r"you'(?:re|ll|d|ve)", value):
            roles.append(None if any(_overlap(word.span(), span) for span in group_sentences) else 1)
        else:
            # We/us/our, third person, and reflexive myself/yourself are not
            # singular channel pronouns. In particular keep Vietnamese mình.
            roles.append(None)
    return roles


def needs_pronoun_alignment(text: str, speaker_role: str) -> bool:
    """Whether source dialogue contains a pronoun this role can safely adjust."""
    pronouns = pronouns_for(speaker_role)
    words = list(_WORD.finditer(text))
    return any(
        role is not None and pronouns[role] is not None
        for role in _source_roles(text, words)
    )


def _protected_target(text: str, words: list[re.Match], index: int) -> bool:
    word = words[index]
    value = word.group().casefold()
    before = []
    cursor = word.start()
    for previous in reversed(words[max(0, index - 2):index]):
        if not text[previous.end():cursor].isspace():
            break
        before.append(previous.group().casefold())
        cursor = previous.start()
    following = None
    if index + 1 < len(words):
        next_word = words[index + 1]
        if text[word.end():next_word.start()].isspace():
            following = next_word.group().casefold()
    if before and before[0] in _PLURAL_PREFIX:
        return True
    if len(before) == 2 and before[1] in _PLURAL_PREFIX and (before[0] in _SINGULAR or before[0] == 'người'):
        return True
    if following in _THIRD_PERSON_SUFFIX or (value == 'ta' and before and before[0] in _SINGULAR):
        return True
    # A possessive head (bạn của anh) and lexical compounds (anh trai, bác
    # sĩ...) are nouns even when attention leaks onto the English possessive.
    if following == 'của' or following in _NOUN_COMPLEMENTS.get(value, ()):
        return True
    if (value == 'bạn' or value in _KINSHIP_ADDRESS) and following in _SINGULAR:
        return True
    return value == 'em' and bool(before) and before[0] == 'anh'


def _valid_spans(spans: Sequence[Span], text_length: int) -> bool:
    return all(0 <= begin <= end <= text_length for begin, end in spans)


def adjust_aligned_pronouns(
    source_text: str,
    target_text: str,
    source_spans: Sequence[Span],
    target_spans: Sequence[Span],
    attention: Sequence[Sequence[float]],
    speaker_role: str,
) -> str:
    """Edit only singular VN pronouns confidently aligned to a configured role.

    Spans use Python character offsets. Source spans include zero-length entries
    for the language prefix and EOS; attention is [target piece][source piece].
    Target spans must describe the *decoded hypothesis*, not a retokenization.
    Neutral changes only self-pronouns and retains contextual model addressees.
    Weak, malformed, reflexive, plural, and reported-speech alignments are kept.
    No omitted subjects or possessives are inserted and no nouns are rewritten.
    """
    pronouns = pronouns_for(speaker_role)
    if (
        len(attention) != len(target_spans)
        or not _valid_spans(source_spans, len(source_text))
        or not _valid_spans(target_spans, len(target_text))
        or any(len(row) != len(source_spans) for row in attention)
    ):
        return target_text
    source_words = list(_WORD.finditer(source_text))
    roles = _source_roles(source_text, source_words)
    if not any(role is not None and pronouns[role] is not None for role in roles):
        return target_text
    source_values = [word.group().casefold().replace('’', "'") for word in source_words]
    person_indices = [
        index for index, value in enumerate(source_values)
        if value.split("'", 1)[0] in _ENGLISH_PERSON
    ]
    # Distribute a token's mass over the lexical words its character span
    # actually covers. Whitespace, the language prefix and EOS are not words.
    source_links = []
    for span in source_spans:
        overlaps = [(index, _overlap(span, word.span())) for index, word in enumerate(source_words)]
        total = sum(length for _, length in overlaps)
        source_links.append([(index, length / total) for index, length in overlaps if length] if total else [])
    target_words = list(_WORD.finditer(target_text))
    replacements = []
    for index, word in enumerate(target_words):
        if word.group().casefold() not in _SINGULAR or _protected_target(target_text, target_words, index):
            continue
        rows = [(row, _overlap(word.span(), span)) for row, span in zip(attention, target_spans)]
        rows = [(row, length) for row, length in rows if length]
        total_length = sum(length for _, length in rows)
        if not total_length:
            continue
        weights = [0.0] * len(source_words)
        invalid = False
        for row, length in rows:
            for token_weight, links in zip(row, source_links):
                if not math.isfinite(token_weight) or token_weight < 0:
                    invalid = True
                    break
                for source_index, share in links:
                    weights[source_index] += token_weight * share * length / total_length
            if invalid:
                break
        if invalid or not weights:
            continue
        # Phrase attention can sit on an English preposition instead of its
        # object ("in you" -> anh). Attach only an immediately adjacent me/you
        # with substantial direct evidence and no competing person reference.
        person = max(person_indices, key=weights.__getitem__)
        if (
            roles[person] is not None
            and source_values[person] in {'me', 'you'}
            and weights[person] >= 0.25
            and weights[person] >= 2 * max(
                (weights[i] for i in person_indices if i != person), default=0.0,
            )
            and person > 0
            and source_values[person - 1] in _OBJECT_PREPOSITION
            and source_text[source_words[person - 1].end():source_words[person].start()].isspace()
        ):
            weights[person] += weights[person - 1]
            weights[person - 1] = 0.0
        best = max(range(len(weights)), key=weights.__getitem__)
        role = roles[best]
        minimum = 0.7 if word.group().casefold() in _KINSHIP_ADDRESS else 0.45
        if role is None or pronouns[role] is None or weights[best] < minimum:
            continue
        # Once the pronoun itself wins, a preposition is not a competing person
        # or content noun. Keep the margin against actual lexical alternatives.
        runner_up = max(
            (weight for i, weight in enumerate(weights)
             if i != best and source_values[i] not in _OBJECT_PREPOSITION),
            default=0.0,
        )
        if weights[best] < runner_up * 1.35:
            continue
        replacement = pronouns[role]
        if word.group().isupper():
            replacement = replacement.upper()
        elif word.group()[0].isupper():
            replacement = replacement.capitalize()
        replacements.append((word.start(), word.end(), replacement))
    for start, end, replacement in reversed(replacements):
        target_text = target_text[:start] + replacement + target_text[end:]
    return target_text
