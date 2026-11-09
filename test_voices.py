"""Pure linguistic boundary tests: no model, Qt, API, or network required."""

import unittest

from voices import adjust_aligned_pronouns


def span(text, needle, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(needle, start + 1)
    return start, start + len(needle)


def personalize(source, target, links, role='nikke', confidence=0.9):
    """Supply transparent character-span alignments, independent of tokenizers.

    Each link is (target phrase, source phrase) or includes occurrence indexes
    as (target phrase, source phrase, target occurrence, source occurrence).
    Unlinked characters attend only to a zero-length language-prefix column.
    """
    source_spans = [(0, 0), *[(i, i + 1) for i in range(len(source))], (len(source), len(source))]
    target_spans = [(i, i + 1) for i in range(len(target))]
    attention = [[1.0, *([0.0] * (len(source) + 1))] for _ in target]
    for link in links:
        target_word, source_word, *occurrences = link
        target_occurrence, source_occurrence = occurrences or (0, 0)
        target_start, target_end = span(target, target_word, target_occurrence)
        source_start, source_end = span(source, source_word, source_occurrence)
        letters = [i for i in range(source_start, source_end) if source[i].isalpha()]
        for i in range(target_start, target_end):
            attention[i] = [0.0] * len(source_spans)
            attention[i][0] = 1.0 - confidence
            for letter in letters:
                attention[i][letter + 1] = confidence / len(letters)
    return adjust_aligned_pronouns(source, target, source_spans, target_spans, attention, role)


class ChannelVoiceTests(unittest.TestCase):
    def test_unknown_roles_are_rejected_before_adjusting_text(self):
        for role in ('', 'NIKKE', 'player', None):
            with self.subTest(role=role), self.assertRaises(ValueError):
                personalize('I trust you.', 'Tôi tin bạn.', [], role)

    def test_singular_subject_and_addressee_use_opposite_channel_voices(self):
        source, target = 'I trust you.', 'Tôi tin bạn.'
        links = [('Tôi', 'I'), ('bạn', 'you')]
        self.assertEqual(personalize(source, target, links), 'Em tin anh.')
        self.assertEqual(personalize(source, target, links, 'commander'), 'Anh tin em.')

    def test_neutral_normalizes_self_without_changing_contextual_addressees(self):
        for speaker, addressee in (
            ('Em', 'cậu'), ('Anh', 'cô'), ('Tớ', 'anh'), ('Mình', 'chị'),
            ('Ta', 'bạn'), ('TÔI', 'NGÀI'),
        ):
            source, target = 'I trust you, Marian.', f'{speaker} tin {addressee}, Marian.'
            expected_self = 'TÔI' if speaker.isupper() else 'Tôi'
            with self.subTest(speaker=speaker, addressee=addressee):
                self.assertEqual(
                    personalize(source, target, [(speaker, 'I'), (addressee, 'you')], 'neutral'),
                    f'{expected_self} tin {addressee}, Marian.',
                )

    def test_neutral_objects_and_possessives_keep_the_addressee(self):
        cases = (
            ('You can count on me.', 'Cô có thể tin em.',
             [('Cô', 'You'), ('em', 'me')], 'Cô có thể tin tôi.'),
            ('My life is in your hands.', 'Mạng sống của em nằm trong tay cậu.',
             [('em', 'My'), ('cậu', 'your')], 'Mạng sống của tôi nằm trong tay cậu.'),
            ('That is yours, not mine.', 'Đó là của anh, không phải của tớ.',
             [('anh', 'yours'), ('tớ', 'mine')], 'Đó là của anh, không phải của tôi.'),
        )
        for source, target, links, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(personalize(source, target, links, 'neutral'), expected)

    def test_neutral_second_person_without_self_stays_contextual(self):
        self.assertEqual(
            personalize('You should take care of yourself.', 'Cậu nên tự lo cho mình.',
                        [('Cậu', 'You'), ('mình', 'yourself')], 'neutral'),
            'Cậu nên tự lo cho mình.',
        )

    def test_switching_roles_repeatedly_does_not_retain_previous_voice(self):
        source, target = 'I trust you.', 'Tôi tin bạn.'
        links = [('Tôi', 'I'), ('bạn', 'you')]
        for role, expected in (
            ('neutral', 'Tôi tin bạn.'),
            ('nikke', 'Em tin anh.'),
            ('commander', 'Anh tin em.'),
            ('neutral', 'Tôi tin bạn.'),
            ('commander', 'Anh tin em.'),
            ('nikke', 'Em tin anh.'),
            ('neutral', 'Tôi tin bạn.'),
        ):
            with self.subTest(role=role):
                self.assertEqual(personalize(source, target, links, role), expected)

    def test_neutral_keeps_other_people_plural_and_reported_speech(self):
        cases = (
            ('I gave her your letter.', 'Em đưa thư của cậu cho cô ấy.',
             [('Em', 'I'), ('cậu', 'your'), ('cô', 'her')],
             'Tôi đưa thư của cậu cho cô ấy.'),
            ('We trust you.', 'Chúng em tin anh.',
             [('em', 'We'), ('anh', 'you')], 'Chúng em tin anh.'),
            ('I trust all of you.', 'Em tin các cậu.',
             [('Em', 'I'), ('cậu', 'you')], 'Tôi tin các cậu.'),
            ('I told her, "You can count on me."', 'Em nói với cô ấy, "Cậu có thể tin em."',
             [('Em', 'I'), ('cô', 'her'), ('Cậu', 'You'), ('em', 'me')],
             'Tôi nói với cô ấy, "Cậu có thể tin em."'),
        )
        for source, target, links, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(personalize(source, target, links, 'neutral'), expected)

    def test_neutral_keeps_uncertain_self_alignment(self):
        self.assertEqual(
            personalize('I trust you.', 'Em tin cậu.', [('Em', 'I'), ('cậu', 'you')],
                        'neutral', confidence=0.4),
            'Em tin cậu.',
        )

    def test_object_pronouns_and_formal_address_are_aligned_not_global(self):
        source, target = 'You can count on me.', 'Ngài có thể tin tôi.'
        links = [('Ngài', 'You'), ('tôi', 'me')]
        self.assertEqual(personalize(source, target, links), 'Anh có thể tin em.')
        self.assertEqual(personalize(source, target, links, 'commander'), 'Em có thể tin anh.')

    def test_possessives_preserve_head_nouns_and_vietnamese_word_order(self):
        source, target = 'My life is in your hands.', 'Mạng sống của tôi nằm trong tay bạn.'
        links = [('tôi', 'My'), ('bạn', 'your')]
        self.assertEqual(personalize(source, target, links), 'Mạng sống của em nằm trong tay anh.')
        self.assertEqual(personalize(source, target, links, 'commander'), 'Mạng sống của anh nằm trong tay em.')

    def test_possessive_pronouns_mine_and_yours(self):
        source, target = 'That is yours, not mine.', 'Đó là của bạn, không phải của tôi.'
        links = [('bạn', 'yours'), ('tôi', 'mine')]
        self.assertEqual(personalize(source, target, links), 'Đó là của anh, không phải của em.')

    def test_contractions_and_curly_apostrophes_keep_person(self):
        for source in ("I'm glad you're here.", 'I’m glad you’re here.', "I'll stay because you've asked."):
            first = source.split()[0]
            second = next(word.rstrip('.') for word in source.split() if word.startswith(('you', 'you’')))
            with self.subTest(source=source):
                self.assertEqual(
                    personalize(source, 'Tôi mừng vì bạn ở đây.', [('Tôi', first), ('bạn', second)]),
                    'Em mừng vì anh ở đây.',
                )

    def test_third_person_narration_and_commander_title_are_unchanged(self):
        cases = [
            ("The Commander rests his hand on Marian's hand.", 'Chỉ huy đặt tay lên tay Marian.'),
            ('She said she would return.', 'Cô ấy nói sẽ trở lại.'),
            ('He is talking to her.', 'Anh ấy đang nói chuyện với cô ta.'),
        ]
        for source, target in cases:
            for role in ('neutral', 'nikke', 'commander'):
                with self.subTest(source=source, role=role):
                    self.assertEqual(personalize(source, target, [], role), target)

    def test_third_person_is_kept_beside_actual_first_and_second_person(self):
        source, target = 'I gave her your letter.', 'Tôi đưa thư của bạn cho cô ấy.'
        links = [('Tôi', 'I'), ('bạn', 'your'), ('cô', 'her')]
        self.assertEqual(personalize(source, target, links), 'Em đưa thư của anh cho cô ấy.')
        self.assertEqual(personalize(source, target, links, 'commander'), 'Anh đưa thư của em cho cô ấy.')

    def test_third_person_suffix_blocks_even_misleading_attention(self):
        for target in ('Anh ấy ở đây.', 'Cô ta ở đây.', 'Bạn đó ở đây.'):
            first = target.split()[0]
            links = [(first, 'you')]
            with self.subTest(target=target):
                self.assertEqual(personalize('I see you.', target, links, 'commander'), target)

    def test_first_person_plural_stays_plural(self):
        source, target = 'We trust you.', 'Chúng tôi tin bạn.'
        links = [('tôi', 'We'), ('bạn', 'you')]
        self.assertEqual(personalize(source, target, links), 'Chúng tôi tin anh.')
        self.assertEqual(personalize(source, target, links, 'commander'), 'Chúng tôi tin em.')
        self.assertEqual(
            personalize('We will return together.', 'Chúng ta sẽ trở lại cùng nhau.', [('ta', 'We')]),
            'Chúng ta sẽ trở lại cùng nhau.',
        )

    def test_explicit_plural_address_and_its_possessive_are_not_singularized(self):
        for source, addressed in (
            ('All of you, take your weapons.', 'you'),
            ('Both of you, take your weapons.', 'you'),
            ('You two, take your weapons.', 'You'),
            ('You guys, take your weapons.', 'You'),
            ('You should all take your weapons.', 'You'),
            ("You'll both take your weapons.", "You'll"),
        ):
            target = 'Các bạn, lấy vũ khí của bạn.'
            links = [('bạn', addressed), ('bạn', 'your', 1, 0)]
            for role in ('neutral', 'nikke', 'commander'):
                with self.subTest(source=source, role=role):
                    self.assertEqual(personalize(source, target, links, role), target)

    def test_target_group_prefix_is_protected_from_spurious_singular_alignment(self):
        source, target = 'I see you.', 'Chúng tôi chào các anh em.'
        links = [('tôi', 'I'), ('anh', 'you'), ('em', 'you')]
        self.assertEqual(personalize(source, target, links), target)

    def test_reflexive_minh_is_not_blindly_replaced(self):
        source, target = 'You should take care of yourself.', 'Anh nên tự lo cho mình.'
        links = [('Anh', 'You'), ('mình', 'yourself')]
        self.assertEqual(personalize(source, target, links, 'commander'), 'Em nên tự lo cho mình.')
        self.assertEqual(
            personalize('I talk to myself.', 'Tôi nói với chính mình.', [('Tôi', 'I'), ('mình', 'myself')]),
            'Em nói với chính mình.',
        )
        self.assertEqual(personalize('I trust you.', 'Mình tin bạn.', [('Mình', 'I'), ('bạn', 'you')]), 'Em tin anh.')

    def test_friend_noun_is_distinct_from_second_person_ban(self):
        source = 'You are my friend, not my Commander.'
        target = 'Bạn là bạn tôi, không phải Chỉ huy của tôi.'
        links = [('Bạn', 'You'), ('bạn', 'friend'), ('tôi', 'my'), ('tôi', 'my', 1, 1)]
        self.assertEqual(personalize(source, target, links), 'Anh là bạn em, không phải Chỉ huy của em.')
        self.assertEqual(personalize(source, target, links, 'commander'), 'Em là bạn anh, không phải Chỉ huy của anh.')

    def test_friend_possessive_head_stays_a_noun_despite_attention_leak(self):
        source, target = 'Your friends are my friends.', 'Bạn của bạn là bạn của tôi.'
        links = [('Bạn', 'Your'), ('bạn', 'Your'), ('bạn', 'my', 1, 0), ('tôi', 'my')]
        self.assertEqual(personalize(source, target, links), 'Bạn của anh là bạn của em.')
        self.assertEqual(personalize(source, target, links, 'commander'), 'Bạn của em là bạn của anh.')

    def test_friend_compounds_and_kinship_nouns_are_not_pronouns(self):
        for target, head in (('Bạn bè ở đây.', 'Bạn'), ('Anh trai ở đây.', 'Anh'), ('Cô gái ở đây.', 'Cô'), ('Bác sĩ ở đây.', 'Bác')):
            with self.subTest(target=target):
                self.assertEqual(personalize('I trust you.', target, [(head, 'I')]), target)

    def test_reported_quotation_keeps_its_other_participants(self):
        for source, target in (
            ('She said, "I trust you."', 'Cô ấy nói, "Tôi tin bạn."'),
            ('Marian told Rapi, “I trust you.”', 'Marian nói với Rapi, “Tôi tin bạn.”'),
            ('“I trust you,” she said.', '“Tôi tin bạn,” cô ấy nói.'),
        ):
            links = [('Tôi', 'I'), ('bạn', 'you')]
            for role in ('neutral', 'nikke', 'commander'):
                with self.subTest(source=source, role=role):
                    self.assertEqual(personalize(source, target, links, role), target)

    def test_reported_quote_does_not_disable_the_actual_speaker_outside_it(self):
        source, target = 'I told her, "You can count on me."', 'Tôi nói với cô ấy, "Bạn có thể tin tôi."'
        links = [('Tôi', 'I'), ('Bạn', 'You'), ('tôi', 'me')]
        self.assertEqual(personalize(source, target, links), 'Em nói với cô ấy, "Bạn có thể tin tôi."')

    def test_unattributed_quotation_is_still_normal_channel_dialogue(self):
        self.assertEqual(
            personalize('"I trust you."', '"Tôi tin bạn."', [('Tôi', 'I'), ('bạn', 'you')]),
            '"Em tin anh."',
        )

    def test_unicode_character_offsets_and_split_pieces_preserve_other_content(self):
        source, target = 'É 🧡 I trust you.', '🧡 Tôi tin bạn, Marian.'
        links = [('Tôi', 'I'), ('bạn', 'you')]
        self.assertEqual(personalize(source, target, links), '🧡 Em tin anh, Marian.')
        self.assertEqual(personalize('I trust you.', 'TÔI tin BẠN.', [('TÔI', 'I'), ('BẠN', 'you')]), 'EM tin ANH.')

    def test_preposition_object_attention_is_attached_only_with_direct_evidence(self):
        source, target = 'I have faith in you.', 'Em tin em.'
        source_spans = [span(source, word) for word in ('I', 'have', 'faith', 'in', 'you')]
        target_spans = [(0, 2), (3, 6), (7, 9), (9, 10)]
        attention = [[0.9, 0.03, 0.03, 0.01, 0.03], [0.02, 0.65, 0.3, 0.02, 0.01],
                     [0.03, 0.04, 0.22, 0.36, 0.33], [0, 0, 0, 0, 0]]
        self.assertEqual(adjust_aligned_pronouns(source, target, source_spans, target_spans, attention, 'nikke'), 'Em tin anh.')
        self.assertEqual(adjust_aligned_pronouns(source, target, source_spans, target_spans, attention, 'commander'), 'Anh tin em.')
        attention[2] = [0.03, 0.02, 0.05, 0.8, 0.1]
        self.assertEqual(adjust_aligned_pronouns(source, target, source_spans, target_spans, attention, 'nikke'), target)

    def test_preposition_does_not_resolve_competing_people_by_guessing(self):
        source = 'I spoke to her about you.'
        source_spans = [span(source, word) for word in ('I', 'her', 'about', 'you')]
        self.assertEqual(
            adjust_aligned_pronouns(source, 'bạn', source_spans, [(0, 3)], [[0.04, 0.31, 0.35, 0.3]], 'nikke'),
            'bạn',
        )

    def test_model_invented_familial_and_archaic_pronouns_follow_source_person(self):
        source, target = "I'm proud of you.", 'Bố tự hào về con.'
        links = [('Bố', "I'm"), ('con', 'you')]
        self.assertEqual(personalize(source, target, links), 'Em tự hào về anh.')
        self.assertEqual(personalize(source, target, links, 'commander'), 'Anh tự hào về em.')
        self.assertEqual(
            personalize('Your life belongs to me.', 'Mạng sống của ngươi thuộc về ta.', [('ngươi', 'Your'), ('ta', 'me')]),
            'Mạng sống của anh thuộc về em.',
        )

    def test_actual_kinship_nouns_are_not_changed_with_possessive_attention(self):
        source, target = 'My father is waiting for you.', 'Bố tôi đang chờ bạn.'
        links = [('Bố', 'My'), ('tôi', 'My'), ('bạn', 'you')]
        self.assertEqual(personalize(source, target, links), 'Bố em đang chờ anh.')
        source, target = 'I told my mother about you.', 'Tôi nói với mẹ tôi về bạn.'
        links = [('Tôi', 'I'), ('mẹ', 'my'), ('tôi', 'my'), ('bạn', 'you')]
        self.assertEqual(personalize(source, target, links), 'Em nói với mẹ em về anh.')

    def test_winning_possessive_is_not_vetoed_by_unanchored_preposition_mass(self):
        source = 'My mother heard about you.'
        source_spans = [span(source, word) for word in ('My', 'mother', 'about', 'you')]
        self.assertEqual(
            adjust_aligned_pronouns(source, 'Mẹ tôi', source_spans, [(0, 2), (3, 6)],
                                    [[0.04, 0.94, 0.01, 0.01], [0.48, 0.04, 0.4, 0.08]], 'nikke'),
            'Mẹ em',
        )

    def test_explicit_parent_child_vocative_keeps_the_other_relationship(self):
        for source in ('Mom, I miss you.', 'I miss you, Mom.', 'Hey Mom, I miss you.'):
            target = 'Mẹ ơi, con nhớ mẹ.'
            for role in ('neutral', 'nikke', 'commander'):
                with self.subTest(source=source, role=role):
                    self.assertEqual(personalize(source, target, [('con', 'I'), ('mẹ', 'you')], role), target)

    def test_weak_or_competing_alignment_keeps_model_content(self):
        self.assertEqual(personalize('I trust you.', 'Tôi tin bạn.', [('Tôi', 'I'), ('bạn', 'you')], confidence=0.4), 'Tôi tin bạn.')
        self.assertEqual(
            adjust_aligned_pronouns('I see you', 'Tôi', [(0, 1), (6, 9)], [(0, 3)], [[0.5, 0.5]], 'nikke'),
            'Tôi',
        )

    def test_malformed_or_nonfinite_alignment_is_preserved(self):
        for attention, spans in (([], [(0, 3)]), ([[1.0, 0.0]], [(0, 3)]), ([[float('nan')]], [(0, 3)]), ([[1.0]], [(0, 4)])):
            with self.subTest(attention=attention, spans=spans):
                self.assertEqual(adjust_aligned_pronouns('I', 'Tôi', [(0, 1)], spans, attention, 'nikke'), 'Tôi')

    def test_omitted_possessive_is_not_invented(self):
        self.assertEqual(
            personalize('I gave her your letter.', 'Tôi đưa thư cho cô ấy.', [('Tôi', 'I'), ('cô', 'her')]),
            'Em đưa thư cho cô ấy.',
        )

    def test_vocative_and_third_person_titles_are_not_rewritten_as_pronouns(self):
        self.assertEqual(personalize('Yes, Commander.', 'Vâng, Chỉ huy.', []), 'Vâng, Chỉ huy.')
        self.assertEqual(personalize('Yes, sir.', 'Vâng, thưa ngài.', [('ngài', 'sir')]), 'Vâng, thưa ngài.')


if __name__ == '__main__':
    unittest.main()
